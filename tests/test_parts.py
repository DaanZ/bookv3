"""The structured part format: read the same way everywhere, and repaired by whole sentences."""
import unittest
from types import SimpleNamespace

from util.parts import (
    all_sentences,
    drop_unfinished_ending,
    has_highlights,
    paragraphs_from_model,
    part_markdown,
    part_paragraphs,
    part_text,
)

STRUCTURED = {
    "title": "Past the fun part",
    "paragraphs": [
        {"sentences": ["Grit beats **talent**.", "Practice is deliberate."]},
        {"heading": "Lessons from Experience", "sentences": ["Most people **quit** early."]},
    ],
}


class StructuredParts(unittest.TestCase):
    def test_sentences_are_read_as_stored(self):
        self.assertEqual(all_sentences(STRUCTURED),
                         ["Grit beats **talent**.", "Practice is deliberate.", "Most people **quit** early."])

    def test_markdown_keeps_highlights_and_headings_for_prompts(self):
        self.assertEqual(part_markdown(STRUCTURED),
                         "Grit beats **talent**. Practice is deliberate.\n\n"
                         "Lessons from Experience\n\nMost people **quit** early.")

    def test_plain_text_has_no_marks(self):
        self.assertNotIn("**", part_text(STRUCTURED))
        self.assertTrue(has_highlights(STRUCTURED))
        self.assertFalse(has_highlights({"paragraphs": [{"sentences": ["Nothing marked."]}]}))

    def test_a_legacy_html_body_is_still_readable(self):
        legacy = {"body": "One <b style='color: forestgreen;'>point</b>.<br><br>Two. Three."}
        self.assertEqual(part_paragraphs(legacy),
                         [{"sentences": ["One **point**."]}, {"sentences": ["Two.", "Three."]}])


class ModelAnswers(unittest.TestCase):
    def test_blank_sentences_and_empty_paragraphs_are_dropped(self):
        answer = [SimpleNamespace(sentences=[" A. ", ""]), SimpleNamespace(sentences=["  "])]
        self.assertEqual(paragraphs_from_model(answer), [{"sentences": ["A."]}])


class CutOffEndings(unittest.TestCase):
    def test_a_cut_off_last_sentence_is_dropped_and_reported(self):
        paragraphs = [{"sentences": ["Passion follows success."]},
                      {"sentences": ["Talent matters.", "Ultimately, he concludes that **passion is"]}]
        kept, dropped = drop_unfinished_ending(paragraphs)
        self.assertEqual(dropped, "Ultimately, he concludes that **passion is")
        self.assertEqual(kept[-1]["sentences"], ["Talent matters."])
        self.assertEqual(len(paragraphs[-1]["sentences"]), 2, "the input is not changed")

    def test_a_paragraph_left_empty_goes_too(self):
        kept, _ = drop_unfinished_ending([{"sentences": ["Done."]}, {"sentences": ["Cut off here"]}])
        self.assertEqual(kept, [{"sentences": ["Done."]}])

    def test_a_finished_ending_is_left_alone(self):
        paragraphs = [{"sentences": ["Finished, with a stray italic mark.*"]}]
        self.assertEqual(drop_unfinished_ending(paragraphs), (paragraphs, ""))


if __name__ == "__main__":
    unittest.main()
