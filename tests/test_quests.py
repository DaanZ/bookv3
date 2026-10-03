"""The finish screen's quests: a full set or nothing, never half a set."""
import json
import os
import tempfile
import unittest
from unittest import mock

from api import quests

QUEST = {"title": "Citrus peel oil", "action": "Steep orange peel in oil.", "doneWhen": "A bottle of oil exists.", "minutes": 90}


class QuestStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(quests, "STORE_DIR", self.tmp.name)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def write(self, key, record):
        with open(os.path.join(self.tmp.name, f"{key}.json"), "w", encoding="utf-8") as file:
            json.dump(record, file)

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

    def test_an_unreadable_file_is_no_set(self):
        with open(os.path.join(self.tmp.name, "Book.json"), "w", encoding="utf-8") as file:
            file.write("{not json")
        self.assertIsNone(quests.load("Book"))


if __name__ == "__main__":
    unittest.main()
