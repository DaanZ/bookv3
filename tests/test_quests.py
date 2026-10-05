"""The finish screen's quests: a full set or nothing, never half a set."""
import json
import os
import tempfile
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from api import library, quests
from api.deps import reader
from api.main import app

QUEST = {
    "title": "Citrus peel oil", "short": "Steep orange peel in oil.", "source": "Maceration, part 2",
    "needs": ["an orange", "a jar"], "steps": ["Peel the orange.", "Cover the peel with oil."],
    "doneWhen": "A bottle of oil exists.", "minutes": 90,
}


class TempStore(unittest.TestCase):
    """Points every quest store at a temporary folder. Holds no tests of its own."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [mock.patch.object(quests, "STORE_DIR", self.tmp.name),
                        mock.patch.object(quests, "STARTED_DIR", os.path.join(self.tmp.name, "started")),
                        mock.patch.object(quests, "DONE_DIR", os.path.join(self.tmp.name, "done"))]
        for patch in self.patches:
            patch.start()

    def tearDown(self):
        for patch in self.patches:
            patch.stop()
        self.tmp.cleanup()

    def write(self, key, record):
        with open(os.path.join(self.tmp.name, f"{key}.json"), "w", encoding="utf-8") as file:
            json.dump(record, file)


class QuestStore(TempStore):
    def test_no_file_means_no_quests(self):
        self.assertIsNone(quests.load("Missing_Book"))

    def test_a_saved_set_reads_back(self):
        quests.save("Book", {size: dict(QUEST) for size in quests.SIZES}, model="m", generated_at="t")
        loaded = quests.load("Book")
        self.assertEqual(set(loaded), set(quests.SIZES))
        self.assertEqual(loaded["medium"]["doneWhen"], "A bottle of oil exists.")

    def test_half_a_set_is_no_set(self):
        self.write("Book", {"small": QUEST, "medium": QUEST})
        self.assertIsNone(quests.load("Book"))

    def test_a_quest_without_a_done_when_is_no_set(self):
        self.write("Book", {"small": QUEST, "medium": QUEST, "large": dict(QUEST, doneWhen=" ")})
        self.assertIsNone(quests.load("Book"))

    def test_a_bad_estimate_is_dropped_not_fatal(self):
        self.write("Book", {"small": dict(QUEST, minutes="soon"), "medium": QUEST, "large": QUEST})
        self.assertIsNone(quests.load("Book")["small"]["minutes"])

    def test_a_set_from_before_steps_is_no_set(self):
        old = {"title": "T", "action": "One paragraph.", "doneWhen": "D", "minutes": 9}
        self.write("Book", {"small": old, "medium": old, "large": old})
        self.assertIsNone(quests.load("Book"))

    def test_starting_and_undoing_a_quest_is_per_reader(self):
        quests.set_started("owner", "Book", "medium", "2026-10-03T08:00:00+00:00")
        self.assertEqual(quests.started("owner"), {"Book": {"medium": "2026-10-03T08:00:00+00:00"}})
        self.assertEqual(quests.started("someone-else"), {})
        quests.set_started("owner", "Book", "medium", None)
        self.assertEqual(quests.started("owner"), {})

    def test_editing_a_reflection_keeps_the_day_it_was_done(self):
        first = {"happened": "Made it.", "wentWrong": "Too much oil.", "why": "To learn the ratio."}
        quests.set_done("owner", "Book", "small", first, "2026-10-04T10:00:00+00:00")
        later = dict(first, wentWrong="Too much oil, and the peel was wet.")
        quests.set_done("owner", "Book", "small", later, "2026-10-06T10:00:00+00:00")
        saved = quests.done("owner")["Book"]["small"]
        self.assertEqual(saved["doneAt"], "2026-10-04T10:00:00+00:00")
        self.assertEqual(saved["wentWrong"], "Too much oil, and the peel was wet.")
        quests.set_done("owner", "Book", "small", None)
        self.assertEqual(quests.done("owner"), {})

    def test_a_quest_is_open_from_its_start_until_its_reflection(self):
        reflection = {"happened": "a", "wentWrong": "b", "why": "c"}
        quests.set_started("owner", "Book", "small", "2026-10-04T08:00:00+00:00")
        quests.set_started("owner", "Book", "large", "2026-10-04T08:00:00+00:00")
        self.assertEqual(quests.open_count("owner"), {"Book": 2})
        quests.set_done("owner", "Book", "small", reflection, "2026-10-05T08:00:00+00:00")
        self.assertEqual(quests.open_count("owner"), {"Book": 1})
        quests.set_done("owner", "Book", "large", reflection, "2026-10-05T08:00:00+00:00")
        self.assertEqual(quests.open_count("owner"), {})

    def test_an_unreadable_file_is_no_set(self):
        with open(os.path.join(self.tmp.name, "Book.json"), "w", encoding="utf-8") as file:
            file.write("{not json")
        self.assertIsNone(quests.load("Book"))


class QuestDoneRoute(TempStore):
    """PUT .../done: every question answered, or nothing is saved."""

    def setUp(self):
        super().setUp()
        quests.save("Book", {size: dict(QUEST) for size in quests.SIZES})
        index = mock.patch.object(library, "index", lambda: {"Book": {"path": "", "finished": True}})
        index.start()
        self.addCleanup(index.stop)
        app.dependency_overrides[reader] = lambda: {"id": "tester"}
        self.addCleanup(app.dependency_overrides.pop, reader, None)
        self.client = TestClient(app)

    def test_a_reflection_with_an_empty_answer_is_refused(self):
        body = {"happened": "Made the oil.", "wentWrong": "  ", "why": "To feel the ratio."}
        response = self.client.put("/api/books/Book/quests/small/done", json=body)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(quests.done("tester"), {})

    def test_a_full_reflection_is_saved_and_comes_back_with_the_quests(self):
        body = {"happened": " Made the oil. ", "wentWrong": "Too much.", "why": "Ratios."}
        response = self.client.put("/api/books/Book/quests/small/done", json=body)
        self.assertEqual(response.status_code, 200, response.text)
        done = self.client.get("/api/books/Book/quests").json()["done"]
        self.assertEqual(done["small"]["happened"], "Made the oil.")
        self.assertTrue(done["small"]["doneAt"])

    def test_an_unknown_size_is_not_found(self):
        body = {"happened": "a", "wentWrong": "b", "why": "c"}
        self.assertEqual(self.client.put("/api/books/Book/quests/huge/done", json=body).status_code, 404)


if __name__ == "__main__":
    unittest.main()
