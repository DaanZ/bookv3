"""The finish screen's quests: a full set or nothing, never half a set."""
import json
import os
import tempfile
import unittest
from unittest import mock

from fastapi.testclient import TestClient

import quests as maker
from api import library, quest_reroll, quests
from api.deps import admin, reader
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


def quest(title):
    return dict(QUEST, title=title, short=f"{title}, briefly.")


class Reroll(TempStore):
    """New quests replace only what nobody started, and remember what was passed on."""

    def setUp(self):
        super().setUp()
        self.old = {"small": quest("Citrus peel oil"), "medium": quest("Soap bars"), "large": quest("Enfleurage")}
        quests.save("Book", self.old, model="m", generated_at="t")
        self.asked = {}

        def fake_make(book, model, keep=None, avoid=None, direction=None):
            self.asked = {"keep": dict(keep or {}), "avoid": [q["title"] for q in avoid or []], "direction": direction}
            fresh = {"small": quest("Rose water"), "medium": quest("Lavender sachets"), "large": quest("Herb tincture")}
            return {**fresh, **(keep or {})}, "openai/gpt-4o"

        patch = mock.patch.object(maker, "make_quests", fake_make)
        patch.start()
        self.addCleanup(patch.stop)

    def test_a_started_quest_is_kept_and_the_rest_are_passed_on(self):
        quests.set_started("anna", "Book", "medium", "2026-10-05T08:00:00+00:00")
        maker.reroll("Book", {}, "owner")
        now = quests.load("Book")
        self.assertEqual([now[s]["title"] for s in quests.SIZES], ["Rose water", "Soap bars", "Herb tincture"])
        self.assertEqual(sorted(p["title"] for p in quests.passed("Book")), ["Citrus peel oil", "Enfleurage"])
        self.assertEqual(set(self.asked["keep"]), {"medium"})

    def test_a_reflected_quest_from_another_reader_is_kept_too(self):
        quests.set_done("bob", "Book", "large", {"happened": "a", "wentWrong": "b", "why": "c"}, "t")
        maker.reroll("Book", {}, "owner")
        self.assertEqual(quests.load("Book")["large"]["title"], "Enfleurage")

    def test_the_next_reroll_is_told_everything_passed_on_so_far(self):
        maker.reroll("Book", {}, "owner")
        maker.reroll("Book", {}, "owner")
        self.assertEqual(sorted(self.asked["avoid"]), sorted(
            ["Citrus peel oil", "Soap bars", "Enfleurage", "Rose water", "Lavender sachets", "Herb tincture"]))
        self.assertEqual(len(quests.passed("Book")), 6)

    def test_nothing_to_replace_is_refused_before_any_model_call(self):
        for size in quests.SIZES:
            quests.set_started("owner", "Book", size, "t")
        with self.assertRaises(maker.QuestsRejected):
            maker.reroll("Book", {}, "owner")
        self.assertEqual(self.asked, {})

    def test_a_direction_reaches_the_model(self):
        maker.reroll("Book", {}, "owner", direction="indoor plants")
        self.assertEqual(self.asked["direction"], "indoor plants")

    def test_making_a_set_again_keeps_the_passed_list(self):
        maker.reroll("Book", {}, "owner")
        quests.save("Book", self.old, model="m", generated_at="t")
        self.assertEqual(len(quests.passed("Book")), 3)


class ThinkingSteps(unittest.TestCase):
    def test_a_step_that_only_asks_for_thought_is_caught(self):
        steps = ["Think of one alternative.", "Consider the costs.", "List every expense.",
                 "Write down two changes.", "Send the plan to one person."]
        self.assertEqual(maker.thinking_steps(steps), ["Think of one alternative.", "Consider the costs."])


class QuestProblems(unittest.TestCase):
    """Each quest is checked on its own, so a retry can keep the ones that passed."""

    def quest(self, **fields):
        base = {"method": "Living soil", "title": "Compost a pot", "short": "Mix compost into one pot.",
                "steps": ["Fill a bowl.", "Mix in compost.", "Repot the plant."], "minutes": 15}
        return maker.SimpleNamespace(**{**base, **fields})

    def test_a_good_next_break_quest_has_no_problems(self):
        self.assertEqual(maker.quest_problems("small", self.quest(), {"living soil"}, []), [])

    def test_each_moment_has_its_own_minutes(self):
        self.assertTrue(maker.quest_problems("small", self.quest(minutes=45), {"living soil"}, []))
        self.assertEqual(maker.quest_problems("medium", self.quest(minutes=90), {"living soil"}, []), [])
        self.assertTrue(maker.quest_problems("large", self.quest(minutes=180), {"living soil"}, []))

    def test_a_method_named_with_its_part_still_matches(self):
        self.assertEqual(maker.quest_problems("small", self.quest(method="Living Soil (part 1)"), {"living soil"}, []), [])

    def test_a_thinking_step_an_unknown_method_and_a_repeat_are_all_named(self):
        found = maker.quest_problems("small", self.quest(method="Feng shui", steps=["Consider the pot.", "Repot.", "Water."]),
                                     {"living soil"}, ["Compost the pot"])
        self.assertEqual(len(found), 3)


class TooClose(unittest.TestCase):
    def test_a_reworded_title_is_a_repeat_and_a_new_activity_is_not(self):
        self.assertEqual(maker.too_close("Make Citrus Peel Oil", ["Extract Citrus Peel Oil"]), "Extract Citrus Peel Oil")
        self.assertIsNone(maker.too_close("Create a Floral Enfleurage", ["Create Scented Soap Bars"]))


class RerollRoute(TempStore):
    def setUp(self):
        super().setUp()
        quests.save("Book", {size: dict(QUEST) for size in quests.SIZES})
        patches = [
            mock.patch.object(library, "index", lambda: {"Book": {"path": "book.json", "finished": True}}),
            mock.patch.object(quest_reroll, "has_key", lambda: True),
            mock.patch.object(quest_reroll, "submit", self.submitted),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        app.dependency_overrides[admin] = lambda: {"id": "owner", "owner": True}
        self.addCleanup(app.dependency_overrides.pop, admin, None)
        self.client = TestClient(app)

    def submitted(self, key, path, by, direction=None):
        self.direction = direction
        return {"state": "running", "startedAt": "t"}

    def test_a_direction_is_trimmed_and_an_empty_one_is_none(self):
        self.client.post("/api/books/Book/quests/reroll", json={"direction": "  indoor plants "})
        self.assertEqual(self.direction, "indoor plants")
        self.client.post("/api/books/Book/quests/reroll", json={"direction": "   "})
        self.assertIsNone(self.direction)

    def test_a_direction_is_kept_on_the_quest(self):
        quests.save("Book", {size: dict(QUEST, direction="indoor plants") for size in quests.SIZES})
        self.assertEqual(quests.load("Book")["small"]["direction"], "indoor plants")

    def test_a_reroll_is_accepted_and_runs_in_the_background(self):
        response = self.client.post("/api/books/Book/quests/reroll")
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(response.json()["reroll"]["state"], "running")

    def test_a_book_whose_quests_are_all_taken_has_nothing_to_reroll(self):
        for size in quests.SIZES:
            quests.set_started("owner", "Book", size, "t")
        self.assertEqual(self.client.post("/api/books/Book/quests/reroll").status_code, 409)

    def test_without_a_key_nothing_is_queued(self):
        with mock.patch.object(quest_reroll, "has_key", lambda: False):
            self.assertEqual(self.client.post("/api/books/Book/quests/reroll").status_code, 503)


if __name__ == "__main__":
    unittest.main()
