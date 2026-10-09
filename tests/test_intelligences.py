"""The nine intelligences: what the shelf sends for a graded book, and what it refuses."""
import os
import tempfile
import unittest
from unittest import mock

from api import intelligences
from api.profiles import clean_prefs


class Badge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(intelligences, "STORE", os.path.join(self.tmp.name, "intelligences.json"))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_ungraded_is_no_badge(self):
        self.assertIsNone(intelligences.badge("anything"))

    def test_a_graded_book_names_its_primary(self):
        intelligences.save("coaching", {"fits": {"interpersonal": 3, "linguistic": 2, "musical": 0},
                                        "primary": "interpersonal", "reason": "Ask, then listen."})
        badge = intelligences.badge("coaching")
        self.assertEqual((badge["primary"], badge["name"]), ("interpersonal", "Interpersonal"))
        self.assertEqual(badge["fits"], {"interpersonal": 3, "linguistic": 2, "musical": 0})

    def test_unknown_primaries_and_bad_fits_are_refused(self):
        intelligences.save("odd", {"fits": {}, "primary": "telepathic"})
        intelligences.save("loose", {"fits": {"logical": 5, "spatial": "2", "musical": True, "bodily": 1},
                                     "primary": "bodily"})
        self.assertIsNone(intelligences.badge("odd"))
        self.assertEqual(intelligences.badge("loose")["fits"], {"bodily": 1})


class SavedChoice(unittest.TestCase):
    def test_a_known_intelligence_or_none_is_kept(self):
        self.assertEqual(clean_prefs({"shelfIntelligence": "musical"}), {"shelfIntelligence": "musical"})
        self.assertEqual(clean_prefs({"shelfIntelligence": None}), {"shelfIntelligence": None})

    def test_anything_else_is_dropped(self):
        self.assertEqual(clean_prefs({"shelfIntelligence": "telepathic"}), {})


if __name__ == "__main__":
    unittest.main()
