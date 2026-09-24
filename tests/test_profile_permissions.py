"""Who may change a profile: its own reader, or the owner — nobody else, and nobody unlocked.

Run from the repository root, standard library only:

    python -m unittest discover tests

Every profile and position these tests touch lives in a temporary folder: the store paths
in `api.profiles` and `api.positions` are pointed at it for the duration, so the real
`data/` is never read or written.
"""

import os
import shutil
import tempfile
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from api import positions, profiles
from api.main import app


class ProfilePermissions(unittest.TestCase):
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
        # This machine's own trust setting must not answer for the test client.
        env = mock.patch.dict(os.environ, {"BOOKS_TRUSTED_PROFILE": ""})
        env.start()
        self.addCleanup(env.stop)

        self.client = TestClient(app)

        profiles.all_profiles()  # seeds the owner
        self.anna = profiles.create("Anna")[0]["id"]
        self.bob = profiles.create("Bob")[0]["id"]
        profiles.set_pin(profiles.OWNER_ID, "1111", None)
        profiles.set_pin(self.anna, "2222", None)
        profiles.set_pin(self.bob, "3333", None)

        self.as_owner = self.login(profiles.OWNER_ID, "1111")
        self.as_anna = self.login(self.anna, "2222")

    def login(self, profile_id, pin):
        response = self.client.post(f"/api/profiles/{profile_id}/unlock", json={"pin": pin})
        self.assertEqual(response.status_code, 200, response.text)
        return {"X-Profile": profile_id, "X-Device": response.json()["device"]}

    # Every route that changes a profile, as (method, path, body).
    def changes(self, profile_id):
        return [
            ("PATCH", f"/api/profiles/{profile_id}", {"name": "Renamed"}),
            ("PUT", f"/api/profiles/{profile_id}/pin", {"pin": "9999", "current": "0000"}),
            ("POST", f"/api/profiles/{profile_id}/forget-devices", None),
            ("PUT", f"/api/profiles/{profile_id}/prefs", {"theme": "day"}),
            ("PUT", f"/api/profiles/{profile_id}/hardcover", {"token": "not-yours"}),
            ("DELETE", f"/api/profiles/{profile_id}", None),
        ]

    def call(self, method, path, body=None, headers=None):
        return self.client.request(method, path, json=body, headers=headers or {})

    def test_nobody_may_change_a_profile(self):
        for method, path, body in self.changes(self.anna):
            with self.subTest(route=f"{method} {path}"):
                self.assertEqual(self.call(method, path, body).status_code, 401)

    def test_a_locked_profile_proves_nothing(self):
        # Naming yourself without the device token from an unlock is not being yourself.
        for method, path, body in self.changes(self.anna):
            with self.subTest(route=f"{method} {path}"):
                response = self.call(method, path, body, {"X-Profile": self.anna})
                self.assertEqual(response.status_code, 401)

    def test_a_reader_may_not_change_somebody_else(self):
        for target in (profiles.OWNER_ID, self.bob):
            for method, path, body in self.changes(target):
                with self.subTest(target=target, route=f"{method} {path}"):
                    self.assertEqual(self.call(method, path, body, self.as_anna).status_code, 403)

    def test_a_reader_may_change_themselves(self):
        ok = self.call("PUT", f"/api/profiles/{self.anna}/prefs", {"theme": "day"}, self.as_anna)
        self.assertEqual(ok.status_code, 200, ok.text)
        renamed = self.call("PATCH", f"/api/profiles/{self.anna}", {"name": "Anna B"}, self.as_anna)
        self.assertEqual(renamed.status_code, 200, renamed.text)
        self.assertEqual(renamed.json()["name"], "Anna B")

    def test_the_owner_may_change_any_reader(self):
        renamed = self.call("PATCH", f"/api/profiles/{self.bob}", {"name": "Robert"}, self.as_owner)
        self.assertEqual(renamed.status_code, 200, renamed.text)
        deleted = self.call("DELETE", f"/api/profiles/{self.bob}", None, self.as_owner)
        self.assertEqual(deleted.status_code, 200, deleted.text)

    def test_only_the_owner_adds_a_reader(self):
        self.assertEqual(self.call("POST", "/api/profiles", {"name": "Eve"}).status_code, 401)
        self.assertEqual(self.call("POST", "/api/profiles", {"name": "Eve"}, self.as_anna).status_code, 403)
        added = self.call("POST", "/api/profiles", {"name": "Eve"}, self.as_owner)
        self.assertEqual(added.status_code, 200, added.text)

    def test_the_picker_and_unlock_stay_open(self):
        # Somebody has to be able to see who reads here, and to log in.
        self.assertEqual(self.call("GET", "/api/profiles").status_code, 200)
        self.assertEqual(
            self.call("POST", f"/api/profiles/{self.bob}/unlock", {"pin": "3333"}).status_code, 200
        )

    def test_the_real_store_was_not_touched(self):
        self.assertTrue(profiles.STORE_PATH.startswith(self.store))


if __name__ == "__main__":
    unittest.main()
