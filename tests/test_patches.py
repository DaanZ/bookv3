"""The category → patch mapping.

`meta.category` is free text written by the LLM, so this is the layer that has to cope
with 90-odd spellings of a dozen ideas. Every category string used below is one that
actually appears in books/.

    python3 -m unittest discover -s tests
"""

import unittest

from api.patches import FAMILIES, family_of, patch_for

SHAPES = {"rings", "checks", "bands"}


class FamilyOf(unittest.TestCase):
    def test_maps_the_three_the_design_names(self):
        self.assertEqual(family_of("Spirituality/Poetry"), "spirituality")
        self.assertEqual(family_of("Art & Photography, Cultural Studies"), "textiles")
        self.assertEqual(family_of("Self-help / Personal Development"), "self-help")

    def test_is_case_and_punctuation_insensitive(self):
        for text in ("Self-Help", "self-help", "SELF-HELP", "Self-help/Business"):
            self.assertEqual(family_of(text), "self-help", text)

    def test_longest_match_wins_over_a_later_keyword(self):
        # "self-help / productivity" mentions both; the design says it is self-help.
        self.assertEqual(family_of("Self-help / Productivity"), "self-help")

    def test_books_with_no_category_get_one_name_not_an_error(self):
        for missing in (None, "", "   "):
            self.assertEqual(family_of(missing), "uncategorised", repr(missing))

    def test_an_unmapped_category_keeps_its_own_first_segment(self):
        self.assertEqual(family_of("Basket Weaving, Advanced"), "textiles")  # 'weav'
        self.assertEqual(family_of("Zymurgy"), "zymurgy")

    def test_is_stable_for_the_same_input(self):
        self.assertEqual(family_of("Business & Economics"), family_of("Business & Economics"))


class PatchFor(unittest.TestCase):
    def test_the_three_from_the_handoff_are_verbatim(self):
        self.assertEqual(
            patch_for("Spirituality"),
            {"family": "spirituality", "shape": "rings", "c1": "#0C617C", "c2": "#03B1AB", "c3": "#FFD167"},
        )
        self.assertEqual(
            patch_for("Textiles"),
            {"family": "textiles", "shape": "checks", "c1": "#822E37", "c2": "#FDF6EA", "c3": "#BA5834"},
        )
        self.assertEqual(
            patch_for("Self-Help"),
            {"family": "self-help", "shape": "bands", "c1": "#67482F", "c2": "#E59312", "c3": "#F4B315"},
        )

    def test_every_book_gets_something_drawable(self):
        # A shelf row with no patch is a hole in the design, so there is no input that
        # may come back without one.
        for category in (None, "", "Zymurgy", "???", "Non-Fiction", "Business & Economics"):
            patch = patch_for(category)
            self.assertIn(patch["shape"], SHAPES, category)
            for channel in ("c1", "c2", "c3"):
                self.assertRegex(patch[channel], r"^#[0-9A-Fa-f]{6}$", f"{category} {channel}")

    def test_an_unmapped_family_is_deterministic(self):
        # The fallback is derived from the name, so the same book looks the same tomorrow.
        first = patch_for("Zymurgy")
        self.assertEqual(first, patch_for("Zymurgy"))
        self.assertNotEqual(first["family"], patch_for("Philately")["family"])

    def test_known_families_are_all_well_formed(self):
        for name, spec in FAMILIES.items():
            self.assertIn(spec["shape"], SHAPES, name)
            for channel in ("c1", "c2", "c3"):
                self.assertRegex(spec[channel], r"^#[0-9A-Fa-f]{6}$", f"{name} {channel}")


class AgainstTheRealLibrary(unittest.TestCase):
    """Every category actually on disk has to produce a drawable patch."""

    def test_the_whole_corpus(self):
        import glob
        import json

        categories = set()
        for path in glob.glob("books/*/*.json"):
            try:
                with open(path, encoding="utf-8") as handle:
                    categories.add((json.load(handle).get("meta") or {}).get("category"))
            except (OSError, json.JSONDecodeError):
                continue

        self.assertGreater(len(categories), 20, "expected a corpus to test against")
        for category in categories:
            patch = patch_for(category)
            self.assertIn(patch["shape"], SHAPES, category)


if __name__ == "__main__":
    unittest.main()
