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
                         {"score": 5.0, "level": 5, "name": "Orange", "meme": "StriveDrive",
                          "theme": "achievement", "reason": "Results through focus."})

    def test_a_decimal_shows_as_its_whole_level(self):
        spiral.save("leaning", {"level": 5.6, "reason": ""})
        spiral.save("low", {"level": 6.4, "reason": ""})
        self.assertEqual((spiral.badge("leaning")["level"], spiral.badge("leaning")["meme"]), (5, "StriveDrive"))
        self.assertEqual(spiral.badge("leaning")["score"], 5.6)
        self.assertEqual(spiral.badge("low")["level"], 6)

    def test_the_tenths_never_reach_the_next_level(self):
        for score, level in [(5.9, 5), (5.5, 5), (5.0, 5), (6.0, 6), (5.999999999999999, 6),
                             (6.000000000000001, 6), (3.0, 3), (7.9, 7), (8.0, 8)]:
            self.assertEqual(spiral.level_of(score), level, score)

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
        self.assertEqual(spiral.badge("new_book")["meme"], "StriveDrive")

    def test_a_missing_answer_saves_nothing(self):
        with self.answers(5.4, None, 5.6):
            with self.assertRaises(self.script.NoGrade):
                self.script.grade_and_save("new_book", {"meta": {}, "parts": []})
        self.assertIsNone(spiral.badge("new_book"))


if __name__ == "__main__":
    unittest.main()
