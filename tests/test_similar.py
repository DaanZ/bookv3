"""Books like this one: nearness comes from what the summaries say, not the category."""
import unittest

from api import similar


def book(title, category, sentences):
    return {"meta": {"title": title, "category": category},
            "parts": [{"title": "One", "paragraphs": [{"sentences": sentences}]}]}


BOOKS = {
    # No category in common with either garden book, only the subject.
    "homestead": book("Homesteading", "Homesteading",
                      ["Grow **herbs** in rich **compost** beside the kitchen.",
                       "Keep **chickens** and save **seeds** every autumn."]),
    "herbs": book("The Cook's Herb Garden", "Gardening",
                  ["Sow **herbs** in pots of **compost** on a sunny sill.",
                   "Harvest **seeds** once the flowers dry."]),
    "coop": book("Backyard Poultry", "",
                 ["Build a dry coop so the **chickens** lay through winter."]),
    "sales": book("Closing Deals", "Business",
                  ["Ask for the **commitment** before the meeting ends.",
                   "Follow up on every **proposal** within a day."]),
    "pitch": book("The Pitch", "Business",
                  ["A **proposal** wins on the **commitment** it asks for."]),
}


class Similar(unittest.TestCase):
    def setUp(self):
        self.vecs = similar.vectors({key: similar.terms(data) for key, data in BOOKS.items()})

    def keys(self, key):
        return [other for other, _ in similar.nearest(key, vecs=self.vecs)]

    def test_shared_subject_ranks_first_across_categories(self):
        self.assertEqual(self.keys("homestead")[0], "herbs")

    def test_a_book_with_no_category_is_still_found(self):
        self.assertIn("coop", self.keys("homestead"))

    def test_unrelated_books_share_nothing(self):
        self.assertNotIn("sales", self.keys("homestead"))
        self.assertEqual(self.keys("sales"), ["pitch"])

    def test_never_itself(self):
        self.assertNotIn("herbs", self.keys("herbs"))

    def test_highlights_count_double(self):
        counts = similar.terms(book("T", "", ["Plain words here and **compost** there."]))
        self.assertEqual(counts["compost"], 1 + similar.HIGHLIGHT_WEIGHT)
        self.assertEqual(counts["plain"], 1)


if __name__ == "__main__":
    unittest.main()
