"""The shelf's "Recently added": the stored date decides, never the file's mtime."""
import json
import os
import tempfile
import unittest
from unittest import mock

from api import library


def book(title, added_at=None):
    meta = {"title": title, "author": "A. Writer", "category": "Self-Help", "pages": 100}
    if added_at:
        meta["addedAt"] = added_at
    return {"meta": meta, "parts": [{"title": "One", "paragraphs": [{"sentences": ["A **point**."]}]}]}


class ShelfOrder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        available = os.path.join(self.tmp.name, "available")
        os.makedirs(available)
        os.makedirs(os.path.join(self.tmp.name, "read"))
        self.patches = [
            mock.patch.object(library, "AVAILABLE_DIR", available),
            mock.patch.object(library, "FINISHED_DIR", os.path.join(self.tmp.name, "read")),
            mock.patch.object(library, "all_positions", lambda profile_id: {}),
            mock.patch.object(library.enrich, "lookups", lambda: {}),
        ]
        for patch in self.patches:
            patch.start()

        # Written last, so it has the newest mtime: exactly the book a tidy pass rewrites.
        for key, record in (("Old", book("Old", "2024-12-28T12:00:00+00:00")),
                            ("New", book("New", "2026-10-03T06:00:00+00:00")),
                            ("Undated", book("Undated"))):
            with open(os.path.join(available, f"{key}.json"), "w", encoding="utf-8") as file:
                json.dump(record, file)

    def tearDown(self):
        for patch in self.patches:
            patch.stop()
        self.tmp.cleanup()

    def test_a_book_with_no_date_sorts_last_however_fresh_its_file(self):
        shelf = library.shelf({"id": "owner", "owner": True})
        self.assertEqual([b["title"] for b in shelf], ["New", "Old", "Undated"])
        self.assertIsNone(shelf[-1]["addedAt"])


if __name__ == "__main__":
    unittest.main()
