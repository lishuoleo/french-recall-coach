"""Curriculum contracts and independent French-language regression examples."""
from __future__ import annotations

import json
import unittest
from collections import Counter
from pathlib import Path

from coach.content import cardinal, curriculum, normalise, number_cards, ordinal

ROOT = Path(__file__).resolve().parents[1]


class ContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vocab = json.loads((ROOT / 'data/vocab.json').read_text(encoding='utf-8'))
        cls.verbs = json.loads((ROOT / 'data/verbs.json').read_text(encoding='utf-8'))
        cls.numbers = json.loads((ROOT / 'data/numbers.json').read_text(encoding='utf-8'))

    def test_vocab_has_four_full_distinct_weeks(self):
        self.assertEqual(len(self.vocab), 200)
        self.assertEqual(Counter(card['week'] for card in self.vocab), {1: 50, 2: 50, 3: 50, 4: 50})
        self.assertEqual([card['id'] for card in self.vocab], [f'v{i:03}' for i in range(1, 201)])
        self.assertEqual(len({card['target'] for card in self.vocab}), 200)
        self.assertEqual(len({card['prompt'] for card in self.vocab}), 200)

    def test_workshop_example_tests_gender_without_changing_correct_adjective(self):
        card = self.vocab[0]
        self.assertEqual(card['target'], 'la maison')
        self.assertEqual(card['prompt'], 'Translate into French: The house is small.')
        self.assertEqual(card['answers'], ['La maison est petite.'])
        self.assertNotIn(normalise('Le maison est petite.'), {normalise(a) for a in card['answers']})
        self.assertNotIn(normalise('La maison est petit.'), {normalise(a) for a in card['answers']})
        self.assertIn('feminine', card['explanation'])

    def test_noun_genders_and_elisions_include_non_obvious_examples(self):
        by_target = {card['target']: card for card in self.vocab}
        for target in ['la main', 'le garage', 'le fromage', "l'eau", "l'hôtel", "l'âge", 'les toilettes', 'les pâtes']:
            with self.subTest(target=target):
                self.assertIn(target, by_target)
                self.assertIn(target, by_target[target]['answers'])
        self.assertIn('feminine', by_target["l'eau"]['explanation'])
        self.assertIn('masculine', by_target["l'hôtel"]['explanation'])
        self.assertIn('plural', by_target['les toilettes']['explanation'])
        self.assertIn('feminine', by_target['la main']['explanation'])

    def test_known_lexical_and_spelling_variants_are_not_marked_wrong(self):
        by_target = {card['target']: card for card in self.vocab}
        for target, variant in [('la clé', 'la clef'), ('la cuillère', 'la cuiller'),
                                ('le réfrigérateur', 'le frigo'), ('le vélo', 'la bicyclette'),
                                ("l'œuf", "l'oeuf"), ('la sœur', 'la soeur'),
                                ("l'oignon", "l'ognon"), ('le dîner', 'le diner')]:
            with self.subTest(target=target):
                self.assertIn(variant, by_target[target]['answers'])

    def test_verb_grid_is_twenty_verbs_six_persons_four_tenses(self):
        self.assertEqual(len(self.verbs), 480)
        self.assertEqual([card['id'] for card in self.verbs], [f'c{i:03}' for i in range(1, 481)])
        self.assertEqual(Counter(card['week'] for card in self.verbs), {1: 120, 2: 120, 3: 120, 4: 120})
        expected_verbs = {'être', 'avoir', 'faire', 'prendre', 'apprendre', 'comprendre', 'mettre', 'dire',
                          'lire', 'écrire', 'voir', 'boire', 'pouvoir', 'vouloir', 'devoir', 'savoir',
                          'connaître', 'recevoir', 'ouvrir', 'dormir'}
        expected_persons = {'je', 'tu', 'il/elle/on', 'nous', 'vous', 'ils/elles'}
        tenses = {1: 'présent', 2: 'passé composé', 3: 'imparfait', 4: 'futur simple'}
        self.assertEqual({card['infinitive'] for card in self.verbs}, expected_verbs)
        for week, tense in tenses.items():
            subset = [card for card in self.verbs if card['week'] == week]
            self.assertEqual({card['tense'] for card in subset}, {tense})
            self.assertEqual({(card['infinitive'], card['person']) for card in subset},
                             {(verb, person) for verb in expected_verbs for person in expected_persons})

    def test_irregular_forms_use_real_stems_and_auxiliaries(self):
        by_key = {(card['infinitive'], card['tense'], card['person']): card for card in self.verbs}
        # Hand-checked fixtures catch common regularisation and stem errors.
        cases = [
            ('être', 'présent', 'vous', 'êtes'),
            ('faire', 'présent', 'vous', 'faites'),
            ('dire', 'présent', 'vous', 'dites'),
            ('prendre', 'présent', 'ils/elles', 'prennent'),
            ('recevoir', 'présent', 'je', 'reçois'),
            ('ouvrir', 'présent', 'tu', 'ouvres'),
            ('être', 'passé composé', 'je', 'ai été'),
            ('avoir', 'passé composé', 'ils/elles', 'ont eu'),
            ('devoir', 'passé composé', 'nous', 'avons dû'),
            ('écrire', 'passé composé', 'vous', 'avez écrit'),
            ('ouvrir', 'passé composé', 'il/elle/on', 'a ouvert'),
            ('être', 'imparfait', 'nous', 'étions'),
            ('voir', 'imparfait', 'nous', 'voyions'),
            ('boire', 'imparfait', 'vous', 'buviez'),
            ('connaître', 'imparfait', 'ils/elles', 'connaissaient'),
            ('faire', 'futur simple', 'je', 'ferai'),
            ('voir', 'futur simple', 'nous', 'verrons'),
            ('pouvoir', 'futur simple', 'vous', 'pourrez'),
            ('vouloir', 'futur simple', 'il/elle/on', 'voudra'),
            ('recevoir', 'futur simple', 'je', 'recevrai'),
            ('savoir', 'futur simple', 'ils/elles', 'sauront'),
            ('dormir', 'futur simple', 'tu', 'dormiras'),
        ]
        for verb, tense, person, expected in cases:
            with self.subTest(verb=verb, tense=tense, person=person):
                self.assertEqual(by_key[verb, tense, person]['answers'][0], expected)
        self.assertIn('puis', by_key['pouvoir', 'présent', 'je']['answers'])
        self.assertIn('connait', by_key['connaître', 'présent', 'il/elle/on']['answers'])
        self.assertIn('connaitrai', by_key['connaître', 'futur simple', 'je']['answers'])

    def test_compound_past_prompt_makes_agreement_and_answer_format_explicit(self):
        past = [card for card in self.verbs if card['tense'] == 'passé composé']
        for card in past:
            with self.subTest(card=card['id']):
                self.assertEqual(card['auxiliary'], 'avoir')
                self.assertIn('no preceding direct object', card['prompt'])
                self.assertIn('without the subject', card['prompt'])
                self.assertEqual(len(card['answers'][0].split()), 2)
        for card in self.verbs:
            if card['person'] == 'je':
                self.assertIn("Do not include je or j'.", card['prompt'])

    def test_all_written_cards_have_usable_unique_answer_options(self):
        for card in self.vocab + self.verbs:
            with self.subTest(card=card['id']):
                for field in ['prompt', 'target', 'explanation']:
                    self.assertIsInstance(card[field], str)
                    self.assertTrue(card[field].strip())
                self.assertTrue(card['tags'])
                self.assertTrue(card['answers'])
                self.assertTrue(all(isinstance(a, str) and a.strip() for a in card['answers']))
                self.assertEqual(len(card['answers']), len(set(card['answers'])))
                self.assertLessEqual(len(card['answers']), 3)

    def test_metropolitan_cardinal_boundary_cases(self):
        expected = {0: 'zéro', 17: 'dix-sept', 21: 'vingt et un', 61: 'soixante et un',
                    70: 'soixante-dix', 71: 'soixante et onze', 79: 'soixante-dix-neuf',
                    80: 'quatre-vingts', 81: 'quatre-vingt-un', 90: 'quatre-vingt-dix',
                    91: 'quatre-vingt-onze', 99: 'quatre-vingt-dix-neuf',
                    100: 'cent', 101: 'cent un', 180: 'cent quatre-vingts',
                    200: 'deux cents', 201: 'deux cent un', 280: 'deux cent quatre-vingts',
                    281: 'deux cent quatre-vingt-un', 999: 'neuf cent quatre-vingt-dix-neuf'}
        for value, answer in expected.items():
            with self.subTest(value=value):
                self.assertEqual(cardinal(value), answer)

    def test_ordinal_spelling_changes(self):
        for value, expected in {1: 'premier', 2: 'deuxième', 4: 'quatrième', 5: 'cinquième',
                                9: 'neuvième', 21: 'vingt et unième', 80: 'quatre-vingtième',
                                81: 'quatre-vingt-unième', 99: 'quatre-vingt-dix-neuvième'}.items():
            with self.subTest(value=value):
                self.assertEqual(ordinal(value), expected)

    def test_number_assessment_has_the_configured_modes_and_sample_sizes(self):
        cards = number_cards()
        self.assertEqual(len(cards), 80)
        self.assertEqual(len({card['id'] for card in cards}), 80)
        for level in self.numbers['levels']:
            stage_cards = [card for card in cards if card['week'] == level['level']]
            self.assertEqual(len(stage_cards), 20)
            self.assertEqual(Counter(card['tags'][0] for card in stage_cards), level['modes'])
            cardinals = [card for card in stage_cards if card['tags'] == ['cardinal']]
            self.assertTrue(all(level['min'] <= card['value'] <= level['max'] for card in cardinals))
            self.assertIn(level['min'], {card['value'] for card in cardinals})
            self.assertIn(level['max'], {card['value'] for card in cardinals})

    def test_dates_and_times_use_french_agreement(self):
        cards = {card['id']: card for card in number_cards()}
        self.assertEqual(cards['n3-d0']['answers'][0], 'le premier janvier')
        self.assertEqual(cards['n3-d1']['answers'][0], 'le quatorze juillet')
        self.assertEqual(cards['n4-t0000']['answers'][0], 'zéro heure')
        self.assertIn('minuit', cards['n4-t0000']['answers'])
        self.assertEqual(cards['n4-t0100']['answers'][0], 'une heure')
        self.assertEqual(cards['n4-t2105']['answers'][0], 'vingt et une heures cinq')
        self.assertIn('midi', cards['n4-t1200']['answers'])
        self.assertEqual(cards['n4-t2359']['answers'][0], 'vingt-trois heures cinquante-neuf')

    def test_typography_variants_do_not_erase_grammatical_accents(self):
        self.assertEqual(normalise('vingt-et-un'), normalise('vingt et un'))
        self.assertEqual(normalise('deux-cent-quatre-vingts'), normalise('deux cent quatre-vingts'))
        self.assertEqual(normalise('L’école.'), normalise("l'école"))
        self.assertNotEqual(normalise('a'), normalise('à'))
        self.assertNotEqual(normalise('du'), normalise('dû'))
        self.assertNotEqual(normalise('le'), normalise('la'))
        self.assertNotEqual(normalise('quatre-vingts'), normalise('quatre-vingt'))

    def test_runtime_loads_all_three_curricula(self):
        self.assertEqual(len(curriculum('vocab')), 200)
        self.assertEqual(len(curriculum('conjugation')), 480)
        self.assertEqual(len(curriculum('numbers')), 80)


if __name__ == '__main__':
    unittest.main()
