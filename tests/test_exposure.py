"""Independent public-API regressions for assistance across session boundaries.

Every learner and clock in this file is synthetic. No SQL fixture manufactures
progress or alters scheduling state.
"""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from coach.engine import Coach


ROOT = Path(__file__).resolve().parents[1]
START = datetime(2030, 1, 1, tzinfo=timezone.utc)
REFERENCE = 'La maison est petite.'


class ExposureTests(unittest.TestCase):
    def setUp(self):
        (ROOT / '.test-runs').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='exposure-', dir=ROOT / '.test-runs')
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / 'learner'
        coach = self.at()
        coach.init()
        packet = coach.start('vocab', 1)
        coach.answer(packet['item_id'], REFERENCE)
        coach.advance(packet['item_id'])

    def at(self, days=0, minutes=0):
        return Coach(self.state, START + timedelta(days=days, minutes=minutes))

    def restart_card(self, coach, packet):
        coach.stop(packet['session_id'])
        restarted = coach.start('vocab', 1)
        self.assertEqual(restarted['card_id'], packet['card_id'])
        self.assertNotEqual(restarted['item_id'], packet['item_id'])
        return restarted

    def assert_assisted_not_successful(self, coach, packet):
        answer = coach.answer(packet['item_id'], REFERENCE)
        self.assertTrue(answer['assisted'])
        self.assertEqual(answer['verdict'], 'correct')
        latest = coach.export()['tables']['attempts'][-1]
        self.assertEqual(latest['delayed'], 1)
        self.assertEqual(latest['assisted'], 1)
        evidence = coach.status()['modules']['vocab']['evidence']
        self.assertEqual(evidence['tested'], 1)
        self.assertEqual(evidence['successful'], 0)

    def test_hint_stop_start_cannot_become_independent_delayed_recall(self):
        coach = self.at(days=1)
        packet = coach.start('vocab', 1)
        coach.hint(packet['item_id'])
        self.assert_assisted_not_successful(coach, self.restart_card(coach, packet))

    def test_pending_answer_stop_start_retains_reference_exposure(self):
        coach = self.at(days=1)
        packet = coach.start('vocab', 1)
        pending = coach.answer(packet['item_id'], 'I do not know.')
        self.assertEqual(pending['phase'], 'awaiting_assessment')
        self.assertIn(REFERENCE, pending['reference_answers'])
        self.assert_assisted_not_successful(coach, self.restart_card(coach, packet))

    def test_pending_answer_skip_advance_start_retains_reference_exposure(self):
        coach = self.at(days=1)
        packet = coach.start('vocab', 1)
        coach.answer(packet['item_id'], 'I do not know.')
        coach.skip(packet['item_id'], 'Learner chooses to leave this answer unscored.')
        coach.advance(packet['item_id'])
        restarted = coach.start('vocab', 1)
        self.assertEqual(restarted['card_id'], packet['card_id'])
        self.assert_assisted_not_successful(coach, restarted)

    def test_reopening_pending_feedback_refreshes_reference_exposure(self):
        coach = self.at(days=1)
        packet = coach.start('vocab', 1)
        coach.answer(packet['item_id'], 'I do not know.')
        later = self.at(days=3)
        resumed = later.next(packet['session_id'])
        self.assertIn(REFERENCE, resumed['reference_answers'])
        self.assert_assisted_not_successful(later, self.restart_card(later, packet))

    def test_delayed_coached_correction_excludes_immediate_retest_credit(self):
        coach = self.at(days=1)
        packet = coach.start('vocab', 1)
        coach.answer(packet['item_id'], 'Le maison est petite.')
        coach.assess(packet['item_id'], 'incorrect', 'Maison is feminine and requires la.')
        later = self.at(days=3)
        later.retry(packet['item_id'], REFERENCE)
        later.advance(packet['item_id'])
        restarted = later.start('vocab', 1)
        self.assertEqual(restarted['card_id'], packet['card_id'])
        self.assert_assisted_not_successful(later, restarted)

    def test_same_item_hint_stays_assisted_after_a_long_pause(self):
        coach = self.at(days=1)
        packet = coach.start('vocab', 1)
        coach.hint(packet['item_id'])
        later = self.at(days=3)
        self.assert_assisted_not_successful(later, later.next(packet['session_id']))

    def test_new_session_after_a_day_without_help_can_be_independent(self):
        coach = self.at(days=1)
        packet = coach.start('vocab', 1)
        coach.hint(packet['item_id'])
        coach.stop(packet['session_id'])
        later = self.at(days=2)
        restarted = later.start('vocab', 1)
        answer = later.answer(restarted['item_id'], REFERENCE)
        self.assertFalse(answer['assisted'])
        self.assertEqual(later.status()['modules']['vocab']['evidence']['successful'], 1)

    def test_own_answer_feedback_does_not_retroactively_mark_it_assisted(self):
        coach = self.at(days=1)
        packet = coach.start('vocab', 1)
        answer = coach.answer(packet['item_id'], REFERENCE)
        self.assertFalse(answer['assisted'])
        self.assertEqual(coach.status()['modules']['vocab']['evidence']['successful'], 1)


if __name__ == '__main__':
    unittest.main()
