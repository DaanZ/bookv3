"""A reader's saved settings come off the wire, so only known keys in known shapes are kept."""
import unittest

from api.profiles import PREF_DEFAULTS, clean_prefs


class ShelfView(unittest.TestCase):
    def test_a_known_order_is_kept(self):
        for sort in ("shuffled", "added", "spiral-low", "spiral-high"):
            self.assertEqual(clean_prefs({"shelfSort": sort}), {"shelfSort": sort})

    def test_an_unknown_order_is_dropped(self):
        self.assertEqual(clean_prefs({"shelfSort": "title"}), {})

    def test_bands_are_kept_per_filter(self):
        self.assertEqual(clean_prefs({"spiralBands": {"new": [5.6, 6.5], "read": None}}),
                         {"spiralBands": {"new": [5.6, 6.5], "read": None}})

    def test_a_band_is_rounded_and_held_to_the_spiral(self):
        bands = clean_prefs({"spiralBands": {"new": [2.0, 9.94], "read": [5.04, "6.66"]}})["spiralBands"]
        self.assertEqual(bands, {"new": [3.0, 8.0], "read": [5.0, 6.7]})

    def test_a_malformed_band_shows_every_book(self):
        for band in ["5-6", [6.5, 5.6], [5.6], {"low": 5}, ["a", "b"], 7]:
            self.assertEqual(clean_prefs({"spiralBands": {"new": band}})["spiralBands"]["new"], None, band)

    def test_other_keys_and_filters_are_dropped(self):
        cleaned = clean_prefs({"spiralBands": {"reading": [5, 6], "new": [5, 6]}, "admin": True})
        self.assertEqual(cleaned, {"spiralBands": {"new": [5.0, 6.0], "read": None}})

    def test_defaults_are_the_shelf_as_it_was(self):
        self.assertEqual(PREF_DEFAULTS["shelfSort"], "shuffled")
        self.assertEqual(PREF_DEFAULTS["spiralBands"], {"new": None, "read": None})


if __name__ == "__main__":
    unittest.main()
