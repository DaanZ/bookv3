"""The pure helpers in api/library.py — the ones that clean up what the LLM wrote.

Nothing here touches the filesystem: the scanning and moving functions have real side
effects on books/ and are deliberately left out.

    python3 -m unittest discover -s tests
"""

import unittest

from api.library import _plain, _split_title, recap_of, tidy_name


class SplitTitle(unittest.TestCase):
    def test_splits_a_subtitle_off_the_colon(self):
        self.assertEqual(
            _split_title("Balinese Textiles: A Journey Through Tradition and Artistry"),
            ("Balinese Textiles", "A Journey Through Tradition and Artistry"),
        )

    def test_leaves_a_plain_title_alone(self):
        self.assertEqual(_split_title("The Clear Light"), ("The Clear Light", None))

    def test_keeps_a_colon_that_is_not_a_subtitle_break(self):
        # Nothing worth showing on one side of it, so the title stays whole.
        self.assertEqual(_split_title("Go: Now"), ("Go: Now", None))

    def test_only_splits_on_the_first_colon(self):
        title, subtitle = _split_title("Alpha: Two: Three and more")
        self.assertEqual(title, "Alpha")
        self.assertEqual(subtitle, "Two: Three and more")

    def test_a_head_too_short_to_stand_alone_keeps_the_whole_title(self):
        # "One" is not a title anyone would recognise on a shelf row.
        self.assertEqual(_split_title("One: Two and three"), ("One: Two and three", None))

    def test_trims_the_whitespace_it_finds(self):
        self.assertEqual(_split_title("  Spaced Out: A Subtitle  "), ("Spaced Out", "A Subtitle"))

    def test_a_colon_with_no_space_is_not_a_break(self):
        self.assertEqual(_split_title("Ratio 1:2 Explained"), ("Ratio 1:2 Explained", None))


class TidyName(unittest.TestCase):
    def test_fixes_a_name_shouted_by_a_title_page(self):
        self.assertEqual(tidy_name("MIHALY CSIKSZENTMIHALYI"), "Mihaly Csikszentmihalyi")

    def test_leaves_a_name_that_already_has_case(self):
        # Somebody's own spelling is not ours to correct.
        for name in ("bell hooks", "danah boyd", "Peter C. Brown", "Ursula K. Le Guin"):
            self.assertEqual(tidy_name(name), name)

    def test_keeps_particles_lowercase_inside_a_name(self):
        self.assertEqual(tidy_name("LUDWIG VAN BEETHOVEN"), "Ludwig van Beethoven")

    def test_capitalises_a_leading_particle(self):
        # "Van Gogh" at the front of a name is a surname, not a particle.
        self.assertTrue(tidy_name("VAN GOGH").startswith("Van"))

    def test_handles_initials_and_hyphens(self):
        self.assertEqual(tidy_name("J. R. R. TOLKIEN"), "J. R. R. Tolkien")
        self.assertEqual(tidy_name("JEAN-PAUL SARTRE"), "Jean-Paul Sartre")

    def test_leaves_roman_numerals_alone(self):
        self.assertEqual(tidy_name("HENRY VIII"), "Henry VIII")

    def test_survives_nothing(self):
        self.assertIsNone(tidy_name(None))
        self.assertEqual(tidy_name(""), "")


class Plain(unittest.TestCase):
    def test_strips_the_pipelines_html(self):
        self.assertEqual(
            _plain("This is <b style='color: forestgreen;'>important</b> text."),
            "This is important text.",
        )

    def test_collapses_the_whitespace_that_leaves_behind(self):
        self.assertEqual(_plain("a\n\n  b   c"), "a b c")

    def test_survives_nothing(self):
        self.assertEqual(_plain(""), "")
        self.assertEqual(_plain(None), "")


class RecapOf(unittest.TestCase):
    def test_names_the_part_it_is_recapping(self):
        recap = recap_of({"body": "<b>Bali</b> weaves cloth. It matters."})
        self.assertTrue(recap.startswith("Last part: "))
        self.assertIn("Bali weaves cloth.", recap)

    def test_stops_at_a_sentence_rather_than_mid_word(self):
        body = " ".join(f"Sentence number {i} runs on for a while here." for i in range(40))
        recap = recap_of({"body": body}, limit=120)
        self.assertLess(len(recap), 200)
        self.assertTrue(recap.rstrip().endswith("."), recap)

    def test_keeps_the_first_sentence_even_when_it_is_too_long(self):
        # Better one over-long sentence than an empty resume strip.
        body = "A single sentence that is far longer than the limit allows for."
        self.assertIn("A single sentence", recap_of({"body": body}, limit=10))

    def test_says_nothing_when_there_is_nothing_to_say(self):
        self.assertEqual(recap_of({"body": ""}), "")
        self.assertEqual(recap_of({}), "")


if __name__ == "__main__":
    unittest.main()
