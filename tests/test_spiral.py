"""Spiral Dynamics grades: what the shelf sends, and what it refuses to."""
import os
import tempfile
import unittest
from unittest import mock

from api import spiral


class SpiralStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(spiral, "STORE", os.path.join(self.tmp.name, "data", "spiral.json"))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_nothing_graded_is_no_badge(self):
        self.assertIsNone(spiral.badge("anything"))

    def test_a_grade_comes_back_with_its_name(self):
        spiral.save("deep_work", {"level": 5, "reason": "Results through focus.", "model": "m", "gradedAt": "t"})
        self.assertEqual(spiral.badge("deep_work"),
                         {"score": 5.0, "band": [5, 5], "label": "StriveDrive", "dot": 5,
                          "name": "Orange", "theme": "achievement", "reason": "Results through focus."})

    def test_a_transition_names_both_levels(self):
        spiral.save("leaning", {"level": 5.6, "reason": ""})
        badge = spiral.badge("leaning")
        self.assertEqual(badge["label"], "StriveDrive → HumanBond")
        self.assertEqual((badge["band"], badge["dot"], badge["name"]), ([5, 6], 6, "Orange to Green"))
        self.assertEqual(badge["score"], 5.6)

    def test_cores_sit_around_a_level_and_transitions_between(self):
        # Daan's split: 4.8 to 5.2 is Orange, 5.3 to 5.7 is Orange to Green.
        for score, band in [(4.8, (5, 5)), (5.0, (5, 5)), (5.2, (5, 5)), (5.3, (5, 6)), (5.7, (5, 6)),
                            (5.8, (6, 6)), (4.7, (4, 5)), (5.199999999999999, (5, 5)),
                            (5.300000000000001, (5, 6)), (3.0, (3, 3)), (7.7, (7, 8)), (8.0, (8, 8))]:
            self.assertEqual(spiral.band_of(score), band, score)

    def test_a_level_outside_three_to_eight_is_not_shown(self):
        spiral.save("odd", {"level": 2.9, "reason": ""})
        spiral.save("text", {"level": "5", "reason": ""})
        self.assertIsNone(spiral.badge("odd"))
        self.assertIsNone(spiral.badge("text"))

    def test_saving_one_keeps_the_others(self):
        spiral.save("a", {"level": 4, "reason": ""})
        spiral.save("b", {"level": 6, "reason": ""})
        self.assertEqual(set(spiral.load()), {"a", "b"})


class Combine(unittest.TestCase):
    """Three runs into one grade (spiral.py). Imported here, not at the top: the script
    module is at the repo root and needs no API key to import."""

    def setUp(self):
        import spiral as script
        self.combine = script.combine

    def test_close_runs_are_averaged(self):
        self.assertEqual(self.combine([5.4, 5.4, 5.6]), 5.5)
        self.assertEqual(self.combine([5.4, 5.6, 5.3]), 5.4)

    def test_a_high_outlier_is_left_out(self):
        self.assertEqual(self.combine([4.6, 4.6, 5.5]), 4.6)
        self.assertEqual(self.combine([5.6, 6.4, 5.6]), 5.6)

    def test_a_low_outlier_is_left_out(self):
        self.assertEqual(self.combine([5.6, 5.6, 4.6]), 5.6)

    def test_an_even_spread_has_no_outlier(self):
        self.assertEqual(self.combine([5.0, 5.6, 6.2]), 5.6)


class GradeAndSave(unittest.TestCase):
    """What ingest calls for a new book: three runs, combined, saved. The model is mocked,
    so this spends nothing and needs no API key."""

    def setUp(self):
        import spiral as script
        self.script = script
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(spiral, "STORE", os.path.join(self.tmp.name, "spiral.json"))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def answers(self, *levels):
        # None is what llm_strict returns when the model gave no answer.
        replies = iter(None if level is None else mock.Mock(level=level, reason=f"reason {level}")
                       for level in levels)
        return mock.patch.object(self.script, "grade", lambda book, model: next(replies))

    def test_three_runs_are_combined_and_saved(self):
        with self.answers(5.4, 5.6, 6.6):
            saved = self.script.grade_and_save("new_book", {"meta": {}, "parts": []})
        self.assertEqual(saved["runs"], [5.4, 5.6, 6.6])
        self.assertEqual(saved["level"], 5.5)  # 6.6 is the outlier
        self.assertEqual(spiral.badge("new_book")["label"], "StriveDrive → HumanBond")

    def test_a_missing_answer_saves_nothing(self):
        with self.answers(5.4, None, 5.6):
            with self.assertRaises(self.script.NoGrade):
                self.script.grade_and_save("new_book", {"meta": {}, "parts": []})
        self.assertIsNone(spiral.badge("new_book"))


if __name__ == "__main__":
    unittest.main()
