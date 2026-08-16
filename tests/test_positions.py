"""Reading history: sittings, finishes and the order books were finished in.

The store writes real files, so these point it at a temporary directory rather than at
the reader's own `data/`. Nothing here touches a real profile.

    python3 -m unittest discover -s tests
"""

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from api import positions

PROFILE = "testprofile"


class StoreTestCase(unittest.TestCase):
    """Redirect the store at a temporary directory for the length of one test."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._saved = positions.PROFILE_DIR
        positions.PROFILE_DIR = os.path.join(self._tmp.name, "positions")

    def tearDown(self):
        positions.PROFILE_DIR = self._saved
        self._tmp.cleanup()


class SavePosition(StoreTestCase):
    def test_remembers_where_you_stopped(self):
        positions.save_position(PROFILE, "book", 3, 1)
        entry = positions.get_position(PROFILE, "book")
        self.assertEqual((entry["part"], entry["page"]), (3, 1))

    def test_counts_the_first_visit_as_one_sitting(self):
        entry = positions.save_position(PROFILE, "book", 0, 0)
        self.assertEqual(entry["sittings"], 1)

    def test_turning_a_page_does_not_start_a_new_sitting(self):
        positions.save_position(PROFILE, "book", 0, 0)
        entry = positions.save_position(PROFILE, "book", 0, 1)
        self.assertEqual(entry["sittings"], 1)

    def test_coming_back_the_next_day_is_a_new_sitting(self):
        positions.save_position(PROFILE, "book", 0, 0)
        # Reach in and age the last read past the gap, which is what a night is.
        store = positions.all_positions(PROFILE)
        long_ago = datetime.now(timezone.utc) - timedelta(hours=positions.SITTING_GAP_HOURS + 1)
        store["book"]["lastReadAt"] = long_ago.isoformat(timespec="seconds")
        positions._write(PROFILE, store)

        entry = positions.save_position(PROFILE, "book", 1, 0)
        self.assertEqual(entry["sittings"], 2)

    def test_keeps_the_date_you_started_across_sittings(self):
        first = positions.save_position(PROFILE, "book", 0, 0)
        second = positions.save_position(PROFILE, "book", 2, 0)
        self.assertEqual(first["startedAt"], second["startedAt"])

    def test_refuses_to_record_a_negative_place_in_a_book(self):
        entry = positions.save_position(PROFILE, "book", -5, -2)
        self.assertEqual((entry["part"], entry["page"]), (0, 0))

    def test_keeps_profiles_apart(self):
        positions.save_position("alice", "book", 4, 0)
        positions.save_position("bob", "book", 1, 0)
        self.assertEqual(positions.get_position("alice", "book")["part"], 4)
        self.assertEqual(positions.get_position("bob", "book")["part"], 1)

    def test_rejects_a_profile_id_that_would_escape_the_directory(self):
        # The id becomes a path, so this is the one input that must not be trusted.
        for bad in ("../../etc/passwd", "a/b", ""):
            with self.assertRaises(ValueError, msg=bad):
                positions.save_position(bad, "book", 0, 0)


class RecordFinish(StoreTestCase):
    def test_remembers_what_hardcover_said(self):
        positions.save_position(PROFILE, "book", 0, 0)
        entry = positions.record_finish(PROFILE, "book", True)
        self.assertIs(entry["markedRead"], True)
        self.assertIn("finishedAt", entry)

    def test_records_a_refusal_as_a_refusal_not_as_silence(self):
        entry = positions.record_finish(PROFILE, "book", False)
        self.assertIs(entry["markedRead"], False)

    def test_keeps_none_for_a_call_that_was_never_made(self):
        # A guest's finish is real, but nothing was sent on their behalf. That is not
        # the same as sending it and being refused.
        entry = positions.record_finish(PROFILE, "book", None)
        self.assertIsNone(entry["markedRead"])

    def test_re_finishing_does_not_renumber_the_shelf(self):
        first = positions.record_finish(PROFILE, "book", True)
        again = positions.record_finish(PROFILE, "book", True)
        self.assertEqual(first["finishedAt"], again["finishedAt"])

    def test_set_marked_read_leaves_the_finish_date_alone(self):
        original = positions.record_finish(PROFILE, "book", False)
        updated = positions.set_marked_read(PROFILE, "book", True)
        self.assertIs(updated["markedRead"], True)
        self.assertEqual(updated["finishedAt"], original["finishedAt"])

    def test_set_marked_read_says_nothing_about_a_book_never_finished(self):
        self.assertIsNone(positions.set_marked_read(PROFILE, "never-read", True))


class FinishOrdinal(unittest.TestCase):
    """Pure: it reads a positions dict rather than the store."""

    @staticmethod
    def _at(hour):
        return datetime(2026, 1, 1, hour, tzinfo=timezone.utc).isoformat(timespec="seconds")

    def test_numbers_books_in_the_order_they_were_finished(self):
        store = {
            "first": {"finishedAt": self._at(9)},
            "second": {"finishedAt": self._at(11)},
            "third": {"finishedAt": self._at(13)},
        }
        self.assertEqual(positions.finish_ordinal("first", store), 1)
        self.assertEqual(positions.finish_ordinal("second", store), 2)
        self.assertEqual(positions.finish_ordinal("third", store), 3)

    def test_says_nothing_about_a_book_that_was_never_finished(self):
        store = {"open": {"part": 2}, "done": {"finishedAt": self._at(9)}}
        self.assertIsNone(positions.finish_ordinal("open", store))
        self.assertIsNone(positions.finish_ordinal("missing", store))

    def test_does_not_count_books_read_before_this_app_recorded_anything(self):
        # books/read arrived by other routes with no date; inventing one would make the
        # number a guess.
        store = {"tracked": {"finishedAt": self._at(9)}, "untracked": {"part": 4}}
        self.assertEqual(positions.finish_ordinal("tracked", store), 1)

    def test_counts_the_finished_ones_only(self):
        store = {
            "a": {"finishedAt": self._at(9)},
            "b": {"part": 1},
            "c": {"finishedAt": self._at(10)},
        }
        self.assertEqual(positions.finished_count(store), 2)
        self.assertEqual(positions.finished_count({}), 0)


class Ambience(StoreTestCase):
    def test_keeps_the_bed_with_the_book_not_the_app(self):
        positions.save_ambience(PROFILE, "book", "river", 0.4)
        entry = positions.get_position(PROFILE, "book")
        self.assertEqual(entry["ambience"], {"bed": "river", "level": 0.4})

    def test_clamps_a_level_that_could_never_be_played(self):
        positions.save_ambience(PROFILE, "book", "lake", 9.0)
        self.assertEqual(positions.get_position(PROFILE, "book")["ambience"]["level"], 1.0)
        positions.save_ambience(PROFILE, "book", "lake", -3)
        self.assertEqual(positions.get_position(PROFILE, "book")["ambience"]["level"], 0.0)

    def test_changing_the_level_keeps_the_bed(self):
        positions.save_ambience(PROFILE, "book", "wind", 0.3)
        positions.save_ambience(PROFILE, "book", None, 0.6)
        entry = positions.get_position(PROFILE, "book")["ambience"]
        self.assertEqual(entry, {"bed": "wind", "level": 0.6})

    def test_does_not_disturb_where_you_were_reading(self):
        positions.save_position(PROFILE, "book", 5, 1)
        positions.save_ambience(PROFILE, "book", "forest", 0.2)
        entry = positions.get_position(PROFILE, "book")
        self.assertEqual((entry["part"], entry["page"]), (5, 1))


if __name__ == "__main__":
    unittest.main()
