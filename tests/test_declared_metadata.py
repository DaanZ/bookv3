"""A PDF's own title and author are trusted over its pages, so a placeholder must not pass."""
import unittest

from api.jobs import is_placeholder


class Placeholders(unittest.TestCase):
    def test_proquest_defaults_are_refused(self):
        self.assertTrue(is_placeholder("someTitle"))
        self.assertTrue(is_placeholder("someAuthor"))

    def test_other_unfilled_values_are_refused(self):
        for value in ["", "  ", "Untitled", "Unknown", "Microsoft Word - draft3.docx", "chapter1.pdf", "Admin", "Document1"]:
            self.assertTrue(is_placeholder(value), value)

    def test_real_titles_and_authors_pass(self):
        for value in ["Ethics", "Baruch Spinoza", "The Gardener and the Carpenter", "Gopnik, Alison", "Documenting Hate"]:
            self.assertFalse(is_placeholder(value), value)


if __name__ == "__main__":
    unittest.main()
