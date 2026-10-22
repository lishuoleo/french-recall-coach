"""Learning-state invariants, failure paths and outer-loop policy.

Every test owns a disposable synthetic learner beneath .test-runs. Most tests
exercise the public gateway. Explicit SQL fixtures are confined to policy/state
boundary tests; they are not evidence of a real learner completing the course.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier

from coach.content import MODULES
from coach.engine import BASE_NEW, SCHEMA, Coach, CoachError, decide
from coach.scheduler import review, utc

ROOT = Path(__file__).resolve().parents[1]
START = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)


class LearnerCase(unittest.TestCase):
    def setUp(self):
        (ROOT / '.test-runs').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='engine-', dir=ROOT / '.test-runs')
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / 'learner'
        self.coach = Coach(self.state, START)
        self.coach.init()

    def at(self, delta):
        return Coach(self.state, START + delta)

    def rows(self, table):
        # Read at the current synthetic clock, including after a restarted Coach.
        with sqlite3.connect(self.coach.db) as con:
            latest = con.execute('SELECT MAX(at) FROM events').fetchone()[0]
        return Coach(self.state, latest or START).export()['tables'][table]

    def error(self, code, call, *args, **kwargs):
        with self.assertRaises(CoachError) as caught:
            call(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def correct(self, coach, packet):
        reference = coach.catalogue[packet['module']][packet['card_id']]['answers'][0]
        return coach.answer(packet['item_id'], reference)

    def complete(self, coach, packet):
        while packet['phase'] == 'awaiting_answer':
            self.correct(coach, packet)
            packet = coach.advance(packet['item_id'])
        self.assertEqual(packet['phase'], 'complete')
        return packet

    def seed_evidence(self, module, stage, successful, missing=0, day=6, assisted=0):
        """Explicit state fixture for outer-policy boundaries, not an end-to-end run."""
        cards = [c for c in self.coach.catalogue[module].values() if c['week'] == stage]
        chosen = cards[:len(cards) - missing]
        at = START + timedelta(days=day)
        with sqlite3.connect(self.coach.db) as con:
            for index, card in enumerate(chosen):
                sid = f'fixture-{module}-{stage}-{day}-{index}'
                item = sid + ':0'
                verdict = 'correct' if index < successful else 'incorrect'
                hinted = index < assisted
                state, _ = review(module, card['id'], None, True, False, at - timedelta(days=2))
                state, log = review(module, card['id'], state, verdict == 'correct', hinted, at)
                con.execute('INSERT OR REPLACE INTO cards VALUES(?,?,?,?)',
                            (module, card['id'], json.dumps(state), state['due']))
                con.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,?)',
                            (sid, module, json.dumps([card['id']]), 1, 'complete', at.isoformat(), at.isoformat()))
                con.execute('INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                            (item, sid, module, card['id'], card['answers'][0] if verdict == 'correct' else 'wrong',
                             int(hinted), verdict, 'synthetic_fixture', 'Synthetic boundary fixture', at.isoformat(),
                             0, 1, json.dumps(log), '[]'))


class SessionTests(LearnerCase):
    def test_question_withholds_reference_until_actual_answer_is_saved(self):
        packet = self.coach.start(limit=1)
        self.assertEqual(packet['phase'], 'awaiting_answer')
        self.assertNotIn('reference_answers', packet)
        self.assertNotIn('explanation', packet)
        self.assertEqual(self.rows('attempts'), [])
        answered = self.coach.answer(packet['item_id'], 'Le maison est petite.')
        self.assertEqual(answered['phase'], 'awaiting_assessment')
        self.assertEqual(answered['reference_answers'], ['La maison est petite.'])
        self.assertEqual(self.rows('attempts')[0]['first_answer'], 'Le maison est petite.')

    def test_first_answer_is_immutable_and_duplicate_submission_schedules_once(self):
        packet = self.coach.start(limit=1)
        answered = self.correct(self.coach, packet)
        before = self.coach.export()['tables']
        duplicate = self.coach.answer(packet['item_id'], answered['first_answer'])
        self.assertEqual(duplicate['status'], 'already_saved')
        self.assertEqual(self.coach.export()['tables'], before)
        self.error('immutable_answer', self.coach.answer, packet['item_id'], 'a different answer')
        self.assertEqual(self.coach.export()['tables'], before)

    def test_coached_retry_preserves_failure_and_fsrs_log(self):
        packet = self.coach.start(limit=1)
        self.coach.answer(packet['item_id'], 'Le maison est petite.')
        self.coach.assess(packet['item_id'], 'incorrect', 'Maison is feminine; petite is already correct.')
        before_card = self.rows('cards')
        before_log = self.rows('attempts')[0]['review_log']
        result = self.coach.retry(packet['item_id'], 'La maison est petite.')
        self.assertFalse(result['scheduled_again'])
        attempt = self.rows('attempts')[0]
        self.assertEqual(attempt['first_answer'], 'Le maison est petite.')
        self.assertEqual(attempt['verdict'], 'incorrect')
        self.assertEqual(attempt['review_log'], before_log)
        self.assertEqual(self.rows('cards'), before_card)
        self.assertEqual(json.loads(attempt['review_log'])['rating'], 1)
        self.assertTrue(json.loads(attempt['retries'])[0]['assisted'])

    def test_hint_before_answer_is_retained_across_process_restart(self):
        packet = self.coach.start(limit=1)
        self.coach.hint(packet['item_id'])
        restarted = self.at(timedelta(seconds=30))
        self.assertTrue(restarted.next(packet['session_id'])['assisted'])
        answered = self.correct(restarted, packet)
        self.assertEqual(answered['verdict'], 'correct')
        self.assertTrue(answered['assisted'])
        self.assertEqual(json.loads(self.rows('attempts')[0]['review_log'])['rating'], 1)

    def test_uncertainty_blocks_scheduling_retry_and_advance_until_resolved(self):
        packet = self.coach.start(limit=1)
        self.coach.answer(packet['item_id'], 'Cette maison est petite.')
        result = self.coach.assess(packet['item_id'], 'uncertain', 'The demonstrative changes the intended reference.')
        self.assertEqual(result['phase'], 'needs_clarification')
        self.assertFalse(result['scheduled'])
        self.assertEqual(self.rows('cards'), [])
        self.error('unfinished_item', self.coach.advance, packet['item_id'])
        self.error('not_assessed', self.coach.retry, packet['item_id'], 'La maison est petite.')
        result = self.coach.assess(packet['item_id'], 'incorrect', 'The requested definite article is missing.')
        self.assertTrue(result['scheduled'])
        self.assertEqual(len(self.rows('cards')), 1)

    def test_valid_unlisted_answer_can_receive_reasoned_judgement(self):
        packet = self.coach.start(limit=1)
        self.coach.answer(packet['item_id'], 'La maison est de petite taille.')
        final = self.coach.assess(packet['item_id'], 'correct', 'This is a valid paraphrase of the target meaning.')
        self.assertEqual(final['assessment_source'], 'agent_judgement')
        self.assertEqual(json.loads(self.rows('attempts')[0]['review_log'])['rating'], 3)
        again = self.coach.assess(packet['item_id'], 'correct', 'This is a valid paraphrase of the target meaning.')
        self.assertTrue(again['saved'])
        self.error('already_assessed', self.coach.assess, packet['item_id'], 'incorrect', 'Changed judgement without evidence.')

    def test_skip_is_unscored_and_does_not_create_mastery_evidence(self):
        packet = self.coach.start(limit=1)
        self.coach.skip(packet['item_id'], 'The learner chooses not to answer.')
        completed = self.coach.advance(packet['item_id'])
        self.assertEqual(completed['phase'], 'complete')
        self.assertFalse(completed['programme_complete'])
        self.assertEqual(self.rows('cards'), [])
        self.assertEqual(self.coach.status()['modules']['vocab']['evidence']['tested'], 0)

    def test_retry_budget_and_duplicate_retry_do_not_consume_extra_attempts(self):
        packet = self.coach.start(limit=1)
        self.correct(self.coach, packet)
        self.coach.retry(packet['item_id'], 'Correction one')
        duplicate = self.coach.retry(packet['item_id'], 'Correction one')
        self.assertEqual(duplicate['status'], 'already_saved')
        self.coach.retry(packet['item_id'], 'Correction two')
        self.error('retry_limit', self.coach.retry, packet['item_id'], 'Correction three')
        self.assertEqual(len(json.loads(self.rows('attempts')[0]['retries'])), 2)

    def test_current_item_enforced_and_advance_is_idempotent(self):
        packet = self.coach.start(limit=2)
        future = packet['session_id'] + ':1'
        self.error('stale_item', self.coach.answer, future, 'premature answer')
        self.correct(self.coach, packet)
        second = self.coach.advance(packet['item_id'])
        self.assertEqual(second['completed_items'], 1)
        self.assertEqual(self.coach.advance(packet['item_id']), second)
        self.error('stale_item', self.coach.hint, packet['item_id'])
        self.error('stale_item', self.coach.retry, packet['item_id'], 'a correction after moving on')

    def test_item_position_alias_cannot_create_a_second_first_attempt(self):
        packet = self.coach.start(limit=1)
        self.coach.answer(packet['item_id'], 'Le maison est petite.')
        before = self.coach.export()['tables']
        for position in ('00', '000', '٠', '０'):
            with self.subTest(position=position):
                alias = packet['session_id'] + ':' + position
                self.error('invalid_item', self.coach.answer, alias, 'La maison est petite.')
        self.assertEqual(self.coach.export()['tables'], before)

    def test_stop_and_resume_are_distinct_from_completion(self):
        packet = self.coach.start(limit=2)
        restarted = self.at(timedelta(seconds=1))
        resumed = restarted.start(limit=30)
        self.assertEqual(resumed['session_id'], packet['session_id'])
        self.assertEqual(resumed['total_items'], 2)
        stopped = restarted.stop(packet['session_id'])
        self.assertEqual(stopped['phase'], 'stopped')
        self.assertFalse(stopped['programme_complete'])
        self.error('stale_item', restarted.answer, packet['item_id'], 'too late')
        new = restarted.start(limit=1)
        self.assertNotEqual(new['session_id'], packet['session_id'])

    def test_daily_new_quota_survives_restart_and_multiple_sessions(self):
        first = self.coach.start(limit=4)
        self.complete(self.coach, first)
        restarted = self.at(timedelta(seconds=1))
        second = restarted.start(limit=30)
        self.assertEqual(second['total_items'], 6)
        self.complete(restarted, second)
        waiting = restarted.start(limit=30)
        self.assertEqual(waiting['phase'], 'waiting')
        self.assertFalse(waiting['programme_complete'])
        self.assertEqual(sum(a['is_new'] for a in self.rows('attempts')), 10)

    def test_skipped_new_items_still_use_the_daily_attention_budget(self):
        packet = self.coach.start(limit=30)
        self.assertEqual(packet['total_items'], 10)
        while packet['phase'] == 'awaiting_answer':
            self.coach.skip(packet['item_id'], 'Deliberately skip this synthetic item.')
            packet = self.coach.advance(packet['item_id'])
        self.assertEqual(self.coach.start()['phase'], 'waiting')
        self.assertEqual(len(self.rows('attempts')), 10)
        self.assertEqual(self.rows('cards'), [])

    def test_due_reviews_are_selected_before_new_items(self):
        packet = self.coach.start(limit=3)
        self.complete(self.coach, packet)
        due_coach = self.at(timedelta(days=1))
        result = due_coach.start(limit=2)
        selected = json.loads(next(s for s in due_coach.export()['tables']['sessions'] if s['id'] == result['session_id'])['queue'])
        self.assertEqual(selected, ['v001', 'v002'])
        self.assertNotIn('v004', selected)

    def test_modules_and_preferences_do_not_leak_learning_state(self):
        before = self.coach.status()['modules']
        packet = self.coach.start('vocab', 1)
        self.correct(self.coach, packet)
        self.coach.preference('vocab', 'Use short explanations.', 'The learner asked for brevity.')
        for module in ('conjugation', 'numbers'):
            after = self.coach.status()['modules'][module]
            self.assertEqual(after, before[module])
            other = self.coach.start(module, 1)
            self.assertEqual(other['preferences'], [])
            self.correct(self.coach, other)
        self.assertEqual({(c['module'], c['card_id']) for c in self.rows('cards')},
                         {('vocab', 'v001'), ('conjugation', 'c001'), ('numbers', 'n1-c0')})

    def test_each_module_enforces_its_own_new_item_budget(self):
        for module, expected in [('vocab', 10), ('conjugation', 6), ('numbers', 5)]:
            packet = self.coach.start(module, 30)
            self.assertEqual(packet['total_items'], expected)
            self.complete(self.coach, packet)
            self.assertEqual(self.coach.start(module, 30)['phase'], 'waiting')

    def test_init_is_non_destructive_and_profiles_are_independent(self):
        packet = self.coach.start(limit=1)
        self.correct(self.coach, packet)
        before = self.coach.export()['tables']
        self.assertEqual(self.coach.init()['status'], 'already_initialised')
        self.assertEqual(self.coach.export()['tables'], before)
        other = Coach(Path(self.temp.name) / 'other', START)
        other.init()
        self.assertEqual(other.export()['tables']['attempts'], [])
        self.error('unknown_session', other.next, packet['session_id'])

    def test_all_session_and_answer_limits_reject_without_state_change(self):
        before = self.coach.export()['tables']
        for limit in (0, -1, 31, True, '10'):
            self.error('invalid_limit', self.coach.start, 'vocab', limit)
        self.error('invalid_module', self.coach.start, 'unknown', 1)
        self.assertEqual(before, self.coach.export()['tables'])
        packet = self.coach.start(limit=1)
        for answer in ('', ' ', 'x' * 4001, None):
            self.error('invalid_answer', self.coach.answer, packet['item_id'], answer)
        self.error('no_answer', self.coach.assess, packet['item_id'], 'correct', 'Invented answer is prohibited.')
        self.assertEqual(self.rows('attempts'), [])

    def test_preference_supersession_retains_history_and_scope(self):
        first = self.coach.preference('vocab', 'Explain in English.', 'Learner request.')
        second = self.coach.preference('vocab', 'Explain in simple French.', 'Updated learner request.', first['id'])
        packet = self.coach.start(limit=1)
        self.assertEqual([p['id'] for p in packet['preferences']], [second['id']])
        self.assertEqual([r['status'] for r in self.rows('preferences')], ['superseded', 'active'])
        self.error('invalid_supersession', self.coach.preference, 'numbers', 'Short hints.', 'Learner request.', second['id'])


class EvidenceTests(LearnerCase):
    def test_immediate_success_does_not_count_as_delayed_mastery(self):
        self.complete(self.coach, self.coach.start(limit=1))
        soon = self.at(timedelta(hours=12))
        self.complete(soon, soon.start(limit=1))
        self.assertEqual([a['delayed'] for a in self.rows('attempts')], [0, 0])
        self.assertEqual(soon.status()['modules']['vocab']['evidence']['successful'], 0)

    def test_exactly_one_day_later_is_delayed_but_untested_items_remain_denominator(self):
        self.complete(self.coach, self.coach.start(limit=1))
        later = self.at(timedelta(days=1))
        self.complete(later, later.start(limit=1))
        evidence = later.status()['modules']['vocab']['evidence']
        self.assertEqual(evidence['tested'], 1)
        self.assertEqual(evidence['successful'], 1)
        self.assertEqual(evidence['expected'], 200)
        self.assertEqual(evidence['success_rate'], 1 / 200)
        self.assertFalse(later.status()['programme_complete'])

    def test_hinted_delayed_answer_counts_coverage_but_not_success(self):
        self.complete(self.coach, self.coach.start(limit=1))
        later = self.at(timedelta(days=1))
        packet = later.start(limit=1)
        later.hint(packet['item_id'])
        self.complete(later, packet)
        evidence = later.status()['modules']['vocab']['evidence']
        self.assertEqual(evidence['tested'], 1)
        self.assertEqual(evidence['successful'], 0)
        self.assertEqual(evidence['forgetting_rate'], 1)

    def test_later_failure_replaces_old_success_in_evidence(self):
        self.complete(self.coach, self.coach.start(limit=1))
        later = self.at(timedelta(days=1))
        self.complete(later, later.start(limit=1))
        much_later = self.at(timedelta(days=30))
        packet = much_later.start(limit=1)
        self.assertEqual(packet['card_id'], 'v001')
        much_later.answer(packet['item_id'], 'wrong')
        much_later.assess(packet['item_id'], 'incorrect', 'The response does not express the requested meaning.')
        self.assertEqual(much_later.status()['modules']['vocab']['evidence']['successful'], 0)

    def test_full_stage_is_exercised_through_public_learning_operations(self):
        # Six days of new introductions and due review, then another review day.
        # This is an integration run; it does not insert evidence rows directly.
        latest = self.coach
        for day in range(8):
            latest = self.at(timedelta(days=day))
            for _ in range(20):
                packet = latest.start('vocab', 30)
                if packet['phase'] == 'waiting':
                    break
                self.complete(latest, packet)
            else:
                self.fail('Daily bounded sessions did not reach waiting')
        proposal = latest.evaluate('vocab')
        self.assertEqual(proposal['evidence']['expected'], 50)
        self.assertEqual(proposal['evidence']['tested'], 50)
        self.assertEqual(proposal['evidence']['successful'], 50)
        self.assertEqual(proposal['proposal']['action'], 'advance')
        self.assertEqual(latest.status()['modules']['vocab']['plan']['stage'], 1)
        applied = latest.apply(proposal['evaluation_id'])
        self.assertEqual(applied['plan']['stage'], 2)
        self.assertEqual(latest.status()['modules']['conjugation']['plan']['stage'], 1)
        self.assertFalse(latest.status()['programme_complete'])

    def test_every_module_can_complete_through_public_api_with_weekly_evaluation(self):
        """Perfect synthetic recall exercises liveness, never real learning efficacy.

        All attempts, FSRS transitions, daily quotas, stages and evaluations use
        public operations. No database fixture creates progress in this test.
        """
        attempts = 0
        for day in range(180):
            current = self.at(timedelta(days=day))
            for module in MODULES:
                for _ in range(40):
                    packet = current.start(module, 30)
                    if packet['phase'] == 'waiting':
                        break
                    while packet['phase'] == 'awaiting_answer':
                        self.correct(current, packet)
                        attempts += 1
                        packet = current.advance(packet['item_id'])
                    self.assertEqual(packet['phase'], 'complete')
                else:
                    self.fail('The bounded daily run never reached waiting')
            if day and day % 7 == 0:
                for module in MODULES:
                    evaluation = current.evaluate(module)
                    current.apply(evaluation['evaluation_id'])
            status = current.status()
            if status['programme_complete']:
                break
        else:
            summary = {m: {'stage': x['plan']['stage'], 'introduced': x['introduced'],
                           'coverage': x['evidence']['coverage']} for m, x in status['modules'].items()}
            self.fail(f'Perfect synthetic recall cannot complete within 180 days: {summary}')
        self.assertGreater(attempts, 2 * (200 + 480 + 80))
        for module, expected in [('vocab', 200), ('conjugation', 480), ('numbers', 80)]:
            result = status['modules'][module]
            self.assertEqual(result['plan']['stage'], 5)
            self.assertEqual(result['introduced'], expected)
            self.assertEqual(result['evidence']['tested'], expected)
            self.assertEqual(result['evidence']['successful'], expected)
            self.assertEqual(result['due'], 0)
            self.assertIsNone(result['active_session'])

    def test_weekly_evaluation_rejects_early_and_unfinished_sessions(self):
        self.error('period_open', self.at(timedelta(days=7, microseconds=-1)).evaluate, 'vocab')
        late = self.at(timedelta(days=7))
        packet = late.start(limit=1)
        self.error('active_session', late.evaluate, 'vocab')
        late.stop(packet['session_id'])
        result = late.evaluate('vocab')
        self.assertEqual(result['proposal']['action'], 'hold')
        self.assertEqual(result['evidence']['tested'], 0)

    def test_partial_coverage_cannot_advance_even_if_every_tested_card_passes(self):
        self.seed_evidence('vocab', 1, successful=49, missing=1)
        result = self.at(timedelta(days=7)).evaluate('vocab')
        self.assertEqual(result['evidence']['success_rate'], .98)
        self.assertEqual(result['evidence']['coverage'], .98)
        self.assertEqual(result['proposal']['action'], 'hold')
        self.assertEqual(result['evidence']['missing'], ['v050'])

    def test_review_allocation_changes_the_actual_session_capacity(self):
        self.seed_evidence('vocab', 1, successful=50, day=6)
        later = self.at(timedelta(days=365))
        ordinary = later.start('vocab', 30)
        self.assertEqual(ordinary['total_items'], 20)
        later.stop(ordinary['session_id'])
        # Policy unit fixture: apply the documented increased review allocation.
        with sqlite3.connect(self.coach.db) as con:
            con.execute("UPDATE plans SET review_factor=1.5 WHERE module='vocab'")
        increased = later.start('vocab', 30)
        self.assertEqual(increased['total_items'], 30)

    def test_incomplete_week_preserves_evidence_but_waits_a_week_before_next_review(self):
        self.seed_evidence('vocab', 1, successful=1, missing=49, day=6)
        late = self.at(timedelta(days=7))
        evaluation = late.evaluate('vocab')
        applied = late.apply(evaluation['evaluation_id'])
        self.assertEqual(applied['plan']['period_start'], START.isoformat())
        self.error('period_open', self.at(timedelta(days=8)).evaluate, 'vocab')
        next_week = self.at(timedelta(days=14)).evaluate('vocab')
        self.assertEqual(next_week['evidence']['tested'], 1)
        self.assertEqual(next_week['evidence']['successful'], 1)
        self.assertEqual(next_week['proposal']['action'], 'hold')

    def test_latest_period_excludes_older_evidence(self):
        self.seed_evidence('vocab', 1, successful=50, day=6)
        late = self.at(timedelta(days=7))
        proposal = late.evaluate('vocab')
        late.apply(proposal['evaluation_id'])
        next_period = self.at(timedelta(days=14)).evaluate('vocab')
        self.assertEqual(next_period['evidence']['tested'], 0)
        self.assertEqual(next_period['proposal']['action'], 'hold')

    def test_duplicate_apply_is_no_op_and_sibling_proposal_becomes_stale(self):
        late = self.at(timedelta(days=7))
        first = late.evaluate('vocab')
        second = late.evaluate('vocab')
        applied = late.apply(first['evaluation_id'])
        self.assertEqual(applied['plan']['revision'], 1)
        before = late.export()['tables']
        duplicate = late.apply(first['evaluation_id'])
        self.assertEqual(duplicate['status'], 'already_applied')
        self.assertEqual(late.export()['tables'], before)
        self.error('stale_evaluation', late.apply, second['evaluation_id'])

    def test_new_evidence_invalidates_unapplied_proposal(self):
        self.seed_evidence('vocab', 1, successful=50, day=6)
        late = self.at(timedelta(days=7))
        proposal = late.evaluate('vocab')
        self.seed_evidence('vocab', 1, successful=49, day=7)
        self.error('stale_evidence', late.apply, proposal['evaluation_id'])
        self.assertEqual(late.status()['modules']['vocab']['plan']['revision'], 0)

    def test_programme_completion_requires_every_module_full_coverage_and_above_90_percent(self):
        # Synthetic completed-programme fixture checks the global conjunction.
        for module in MODULES:
            for stage in range(1, 5):
                count = sum(c['week'] == stage for c in self.coach.catalogue[module].values())
                self.seed_evidence(module, stage, successful=count)
        with sqlite3.connect(self.coach.db) as con:
            con.execute('UPDATE plans SET stage=5')
        complete = self.at(timedelta(days=6, seconds=1))
        self.assertTrue(complete.status()['programme_complete'])
        # Completion is an as-of status; overdue maintenance invalidates it.
        self.assertFalse(self.at(timedelta(days=365)).status()['programme_complete'])
        with sqlite3.connect(self.coach.db) as con:
            con.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,?)',
                        ('unfinished-fixture', 'vocab', json.dumps(['v001']), 0, 'active',
                         complete.now.isoformat(), complete.now.isoformat()))
        self.assertFalse(complete.status()['programme_complete'])
        complete.stop('unfinished-fixture')
        self.assertTrue(complete.status()['programme_complete'])
        with sqlite3.connect(self.coach.db) as con:
            con.execute("UPDATE attempts SET verdict='incorrect' WHERE module='vocab' AND card_id IN (SELECT card_id FROM attempts WHERE module='vocab' ORDER BY card_id LIMIT 20)")
        self.assertEqual(complete.status()['modules']['vocab']['evidence']['success_rate'], .9)
        self.assertFalse(complete.status()['programme_complete'])
        with sqlite3.connect(self.coach.db) as con:
            con.execute("UPDATE attempts SET verdict='correct' WHERE module='vocab'")
            con.execute("DELETE FROM attempts WHERE module='numbers' AND card_id='n1-c0'")
        self.assertFalse(complete.status()['programme_complete'])


class PolicyTests(unittest.TestCase):
    def proposal(self, successes, expected=50, tested=None, quota=10, stage=1):
        tested = expected if tested is None else tested
        return decide({'module': 'vocab', 'stage': stage, 'quota': quota, 'review_factor': 1.0},
                      {'expected': expected, 'tested': tested, 'coverage': tested / expected,
                       'success_rate': successes / expected,
                       'forgetting_rate': (tested - successes) / tested if tested else None})

    def test_50_and_80_percent_are_inclusive_review_increase_boundaries(self):
        for successes, action, stage, factor in [(24, 'hold', 1, 1.0), (25, 'advance_with_review', 2, 1.5),
                                               (40, 'advance_with_review', 2, 1.5), (41, 'advance', 2, 1.0)]:
            with self.subTest(successes=successes):
                result = self.proposal(successes)
                self.assertEqual((result['action'], result['stage'], result['review_factor']), (action, stage, factor))

    def test_quota_reduction_is_based_on_original_quota_and_does_not_compound(self):
        self.assertEqual(self.proposal(39)['quota'], 7)
        self.assertEqual(self.proposal(39, quota=7)['quota'], 7)
        self.assertEqual(self.proposal(40, quota=7)['quota'], 10)

    def test_final_stage_advances_to_review_mode_without_claiming_mastery(self):
        self.assertEqual(self.proposal(50, stage=4)['stage'], 5)
        self.assertEqual(self.proposal(50, stage=5)['action'], 'review')
        self.assertEqual(self.proposal(50, stage=5)['stage'], 5)

    def test_incomplete_coverage_preserves_existing_allocation(self):
        result = decide({'module': 'vocab', 'stage': 2, 'quota': 7, 'review_factor': 1.5},
                        {'expected': 50, 'tested': 10, 'coverage': .2, 'success_rate': .2, 'forgetting_rate': 0})
        self.assertEqual((result['stage'], result['quota'], result['review_factor']), (2, 7, 1.5))


class SafetyAndConcurrencyTests(LearnerCase):
    def test_semantically_invalid_plan_is_a_blocking_state_error(self):
        with sqlite3.connect(self.coach.db) as con:
            con.execute("UPDATE plans SET stage=99,quota=-1 WHERE module='vocab'")
        self.error('invalid_state', self.coach.status)

    def test_schedule_index_must_agree_with_the_saved_fsrs_card(self):
        self.complete(self.coach, self.coach.start(limit=1))
        with sqlite3.connect(self.coach.db) as con:
            con.execute("UPDATE cards SET due='2099-01-01T00:00:00+00:00' WHERE module='vocab'")
        self.error('invalid_state', self.coach.status)

    def test_unknown_card_in_session_queue_is_a_blocking_state_error(self):
        packet = self.coach.start(limit=1)
        with sqlite3.connect(self.coach.db) as con:
            con.execute('UPDATE sessions SET queue=? WHERE id=?', (json.dumps(['does-not-exist']), packet['session_id']))
        self.error('invalid_state', self.coach.next, packet['session_id'])

    def test_concurrent_initialisation_is_idempotent(self):
        fresh = Path(self.temp.name) / 'fresh-concurrent-profile'
        barrier = Barrier(4)
        def initialise(_):
            coach = Coach(fresh, START)
            barrier.wait()
            return coach.init()
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(initialise, range(4)))
        self.assertEqual(sum(r['status'] == 'initialised' for r in results), 1)
        self.assertEqual(sum(r['status'] == 'already_initialised' for r in results), 3)
        export = Coach(fresh, START).export()
        self.assertEqual(len(export['tables']['plans']), 3)
        self.assertEqual(sum(e['kind'] == 'initialised' for e in export['tables']['events']), 1)

    def test_clock_reversal_cannot_apply_a_proposal_before_it_was_created(self):
        late = self.at(timedelta(days=7))
        proposal = late.evaluate('vocab')
        before = late.export()['tables']
        self.error('clock_reversed', self.coach.apply, proposal['evaluation_id'])
        self.assertEqual(late.export()['tables'], before)

    def test_sql_transaction_rolls_back_failed_persistence(self):
        packet = self.coach.start(limit=1)
        with sqlite3.connect(self.coach.db) as con:
            con.execute("CREATE TRIGGER synthetic_disk_failure BEFORE INSERT ON cards BEGIN SELECT RAISE(ABORT, 'synthetic write failure'); END")
        with self.assertRaises(sqlite3.DatabaseError):
            self.correct(self.coach, packet)
        self.assertEqual(self.rows('attempts'), [])
        self.assertEqual(self.rows('cards'), [])
        self.assertFalse(any(e['kind'] == 'first_answer_saved' for e in self.rows('events')))

    def test_schema_and_curriculum_drift_fail_closed(self):
        with sqlite3.connect(self.coach.db) as con:
            con.execute("UPDATE meta SET value='999' WHERE key='schema'")
        self.error('schema_mismatch', self.coach.status)
        with sqlite3.connect(self.coach.db) as con:
            con.execute("UPDATE meta SET value=? WHERE key='schema'", (str(SCHEMA),))
            con.execute("UPDATE meta SET value='changed' WHERE key='content_hash'")
        self.error('content_drift', self.coach.init)

    def test_corrupt_database_is_preserved_instead_of_reset(self):
        self.coach.db.write_bytes(b'This is not a SQLite database')
        before = self.coach.db.read_bytes()
        with self.assertRaises(sqlite3.DatabaseError):
            self.coach.init()
        self.assertEqual(self.coach.db.read_bytes(), before)

    def test_state_symlink_and_pre_profile_time_are_rejected(self):
        alias = Path(self.temp.name) / 'alias'
        alias.symlink_to(self.state, target_is_directory=True)
        self.error('unsafe_path', Coach(alias, START).status)
        self.error('clock_reversed', self.at(timedelta(seconds=-1)).status)
        with self.assertRaises(ValueError):
            Coach(self.state, '2026-01-01T09:00:00')

    def test_concurrent_start_returns_one_session(self):
        barrier = Barrier(4)
        def start(_):
            barrier.wait()
            return Coach(self.state, START).start(limit=4)
        with ThreadPoolExecutor(max_workers=4) as pool:
            packets = list(pool.map(start, range(4)))
        self.assertEqual(len({p['session_id'] for p in packets}), 1)
        self.assertEqual(len(self.rows('sessions')), 1)

    def test_concurrent_duplicate_answers_commit_one_attempt_and_schedule(self):
        packet = self.coach.start(limit=1)
        barrier = Barrier(4)
        def submit(_):
            barrier.wait()
            return Coach(self.state, START).answer(packet['item_id'], 'La maison est petite.')
        with ThreadPoolExecutor(max_workers=4) as pool:
            replies = list(pool.map(submit, range(4)))
        self.assertTrue(all(r['saved'] for r in replies))
        self.assertEqual(len(self.rows('attempts')), 1)
        self.assertEqual(len(self.rows('cards')), 1)
        self.assertEqual(sum(e['kind'] == 'attempt_assessed' for e in self.rows('events')), 1)

    def test_concurrent_conflicting_answers_cannot_overwrite_the_winner(self):
        packet = self.coach.start(limit=1)
        barrier = Barrier(2)
        def submit(text):
            barrier.wait()
            try:
                return Coach(self.state, START).answer(packet['item_id'], text)
            except CoachError as exc:
                return {'error': exc.code}
        answers = ['La maison est petite.', 'Le maison est petite.']
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(pool.map(submit, answers))
        self.assertEqual(sum(r.get('error') == 'immutable_answer' for r in replies), 1)
        self.assertEqual(len(self.rows('attempts')), 1)
        self.assertIn(self.rows('attempts')[0]['first_answer'], answers)


if __name__ == '__main__':
    unittest.main()
