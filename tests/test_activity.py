"""The activity endpoint: off without a key, closed to a wrong one, and honest about "today".

Run from the repository root, standard library only:

    python -m unittest discover tests

Stores point at a temporary folder for the duration, so the real reading history is never
read or written.
"""

import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from fastapi.testclient import TestClient

from api import library, positions, profiles
from api.main import app

KEY = "test-activity-key"


class ActivityEndpoint(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="bookv3-test-")
        self.addCleanup(shutil.rmtree, self.store, ignore_errors=True)
        paths = {
            (profiles, "STORE_DIR"): self.store,
            (profiles, "STORE_PATH"): os.path.join(self.store, "profiles.json"),
            (profiles, "ATTEMPTS_PATH"): os.path.join(self.store, "pin-attempts.json"),
            (positions, "STORE_DIR"): self.store,
            (positions, "PROFILE_DIR"): os.path.join(self.store, "positions"),
            (positions, "LEGACY_PATH"): os.path.join(self.store, "positions.json"),
        }
        for (module, name), value in paths.items():
            patcher = mock.patch.object(module, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        env = mock.patch.dict(os.environ, {"BOOKS_TRUSTED_PROFILE": "", "BOOKS_ACTIVITY_KEY": KEY})
        env.start()
        self.addCleanup(env.stop)

        self.client = TestClient(app)
        profiles.all_profiles()  # seeds the owner
        self.anna = profiles.create("Anna")[0]["id"]

        keys = sorted(library.index())
        self.assertGreaterEqual(len(keys), 3, "needs three books in books/ to run")
        self.first, self.second, self.third = keys[:3]

    def get(self, path="/api/activity/today", key=KEY, **params):
        headers = {"Authorization": f"Bearer {key}"} if key is not None else {}
        return self.client.get(path, params=params, headers=headers)

    def stamp(self, profile, key, **fields):
        """Write a position with exact dates, since `save_position` can only say now."""
        data = positions.all_positions(profile)
        data[key] = {**data.get(key, {}), **fields}
        positions._write(profile, data)

    def test_off_when_no_key_is_configured(self):
        with mock.patch.dict(os.environ, {"BOOKS_ACTIVITY_KEY": ""}):
            self.assertEqual(self.get().status_code, 404)
            # Even the right-looking guess gets the same answer: the door is not there.
            self.assertEqual(self.get(key="").status_code, 404)

    def test_wrong_or_missing_key_is_refused(self):
        self.assertEqual(self.get(key=None).status_code, 401)
        self.assertEqual(self.get(key="not-it").status_code, 401)
        self.assertEqual(
            self.client.get("/api/activity/today", headers={"Authorization": KEY}).status_code, 401
        )

    def test_a_profile_header_is_not_a_key(self):
        response = self.client.get("/api/activity/today", headers={"X-Profile": profiles.OWNER_ID})
        self.assertEqual(response.status_code, 401)

    def test_nothing_read_is_an_empty_list_not_an_error(self):
        body = self.get(tz="Europe/Amsterdam").json()
        self.assertEqual(body["books"], [])
        self.assertEqual(body["counts"], {"touched": 0, "finished": 0})

    def test_a_book_saved_today_is_listed_and_one_from_yesterday_is_not(self):
        positions.save_position(profiles.OWNER_ID, self.first, 1, 0)
        yesterday = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(timespec="seconds")
        self.stamp(profiles.OWNER_ID, self.second, part=2, page=0, lastReadAt=yesterday)

        body = self.get(tz="UTC").json()
        self.assertEqual([book["key"] for book in body["books"]], [self.first])
        self.assertEqual(body["counts"], {"touched": 1, "finished": 0})
        self.assertFalse(body["books"][0]["finished"])
        self.assertEqual(body["books"][0]["profile"]["id"], profiles.OWNER_ID)

    def test_finishing_today_is_counted_apart_from_touching(self):
        positions.save_position(profiles.OWNER_ID, self.first, 1, 0)
        positions.save_position(profiles.OWNER_ID, self.second, 4, 0)
        positions.record_finish(profiles.OWNER_ID, self.second, None)

        counts = self.get(tz="UTC").json()["counts"]
        self.assertEqual(counts, {"touched": 2, "finished": 1})

    def test_finished_is_exact_for_a_past_day_even_if_the_book_was_touched_since(self):
        day = "2026-03-05"
        self.stamp(
            profiles.OWNER_ID,
            self.third,
            part=3,
            page=0,
            lastReadAt="2026-09-01T10:00:00+00:00",
            finishedAt=f"{day}T09:30:00+00:00",
        )
        body = self.get(tz="UTC", date=day).json()
        self.assertEqual([book["key"] for book in body["books"]], [self.third])
        self.assertTrue(body["books"][0]["finished"])
        self.assertEqual(body["counts"]["finished"], 1)

    def test_the_day_is_cut_in_the_callers_timezone(self):
        # 23:30 UTC on the 4th is already the 5th in Amsterdam (CET, UTC+1, in March).
        self.stamp(
            profiles.OWNER_ID, self.first, part=1, page=0, lastReadAt="2026-03-04T23:30:00+00:00"
        )
        in_utc = self.get(tz="UTC", date="2026-03-04").json()["books"]
        in_amsterdam = self.get(tz="Europe/Amsterdam", date="2026-03-05").json()["books"]
        self.assertEqual(len(in_utc), 1)
        self.assertEqual(len(in_amsterdam), 1)
        self.assertEqual(self.get(tz="Europe/Amsterdam", date="2026-03-04").json()["books"], [])

    def test_readers_are_separate_unless_asked_for_together(self):
        positions.save_position(profiles.OWNER_ID, self.first, 1, 0)
        positions.save_position(self.anna, self.second, 1, 0)

        owner_only = self.get(tz="UTC").json()["books"]
        self.assertEqual([book["key"] for book in owner_only], [self.first])

        anna = self.get(tz="UTC", profile=self.anna).json()["books"]
        self.assertEqual([book["key"] for book in anna], [self.second])
        self.assertEqual(anna[0]["profile"]["name"], "Anna")

        everyone = self.get(tz="UTC", profile="all").json()
        self.assertEqual({book["key"] for book in everyone["books"]}, {self.first, self.second})

    def test_bad_input_is_a_clear_error(self):
        self.assertEqual(self.get(tz="Not/AZone").status_code, 400)
        self.assertEqual(self.get(profile="nobody").status_code, 404)
        self.assertEqual(self.get(date="yesterday").status_code, 422)

    def test_a_reader_is_named_by_id_and_name_only(self):
        # The profile row also holds a PIN hash, device tokens and a Hardcover token.
        profiles.set_pin(profiles.OWNER_ID, "1111", None)
        positions.save_position(profiles.OWNER_ID, self.first, 1, 0)
        book = self.get(tz="UTC").json()["books"][0]
        self.assertEqual(set(book["profile"]), {"id", "name"})


if __name__ == "__main__":
    unittest.main()
