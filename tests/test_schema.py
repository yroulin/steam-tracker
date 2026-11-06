import copy
import json
import tempfile
import unittest
from pathlib import Path

import update
from steam_schema import SnapshotError, validate_snapshot


def snapshot():
    return {
        "generated": "2026-01-01T00:00:00+00:00",
        "source": "api",
        "schema_version": 2,
        "accounts": [{"alias": "main", "steamid": "76561198000000001"}],
        "family_members": [],
        "games": [{
            "appid": "10",
            "name": "Game",
            "accounts": {"main": 2.5},
            "owned_accounts": ["main"],
            "owned_count": 1,
            "hours_source": "accounts",
            "total_hours": 2.5,
            "family": False,
            "last_played": 0,
            "last_played_iso": None,
            "img_icon_url": "",
            "first_seen": "2026-01-01",
            "price_usd": None,
            "is_free": True,
            "cost_per_hour": None,
            "achieved_by": {"main": {"got": 1, "total": 2}},
            "achievements_got": 1,
            "achievements_total": 2,
            "achievements_pct": 50,
            "achievements_complete": True,
        }],
    }


class SnapshotSchemaTests(unittest.TestCase):
    def test_accepts_a_complete_v2_snapshot(self):
        data = snapshot()
        self.assertIs(validate_snapshot(data), data)

    def test_accepts_an_empty_library(self):
        data = snapshot()
        data["games"] = []
        validate_snapshot(data)

    def test_accepts_legacy_snapshots_without_v2_fields(self):
        data = snapshot()
        data.pop("schema_version")
        for field in ("owned_accounts", "hours_source", "family"):
            data["games"][0].pop(field)
        validate_snapshot(data)

    def test_rejects_non_numeric_hours(self):
        data = snapshot()
        data["games"][0]["total_hours"] = "2.5"
        with self.assertRaises(SnapshotError):
            validate_snapshot(data)

    def test_rejects_negative_numbers(self):
        for field, value in (("total_hours", -1), ("price_usd", -0.01), ("cost_per_hour", -3)):
            data = snapshot()
            data["games"][0][field] = value
            with self.assertRaises(SnapshotError, msg=field):
                validate_snapshot(data)

    def test_rejects_boolean_as_number(self):
        data = snapshot()
        data["games"][0]["total_hours"] = True
        with self.assertRaises(SnapshotError):
            validate_snapshot(data)

    def test_rejects_duplicate_or_malformed_appids(self):
        data = snapshot()
        data["games"].append(copy.deepcopy(data["games"][0]))
        with self.assertRaises(SnapshotError):
            validate_snapshot(data)
        for appid in ("", "abc", 10, None):
            data = snapshot()
            data["games"][0]["appid"] = appid
            with self.assertRaises(SnapshotError, msg=repr(appid)):
                validate_snapshot(data)

    def test_rejects_bad_dates(self):
        for value in ("2026-1-1", "01/01/2026", "hoy", 20260101):
            data = snapshot()
            data["games"][0]["first_seen"] = value
            with self.assertRaises(SnapshotError, msg=repr(value)):
                validate_snapshot(data)

    def test_rejects_unknown_hours_source_in_v2(self):
        data = snapshot()
        data["games"][0]["hours_source"] = "manual"
        with self.assertRaises(SnapshotError):
            validate_snapshot(data)

    def test_rejects_missing_payload_keys(self):
        for key in ("games", "generated", "source", "accounts"):
            data = snapshot()
            data.pop(key)
            with self.assertRaises(SnapshotError, msg=key):
                validate_snapshot(data)

    def test_publish_refuses_to_write_an_invalid_snapshot(self):
        data = snapshot()
        data["games"][0]["total_hours"] = "muchas"
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(SnapshotError):
                update.publish(data, temp)
            self.assertEqual(sorted(p.name for p in Path(temp).iterdir()), [])

    def test_publish_writes_artifacts_for_a_valid_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            update.publish(snapshot(), temp)
            names = sorted(p.name for p in Path(temp).iterdir())
            self.assertEqual(names, ["steam_games.html", "steam_games.json", "steam_games.md"])
            written = json.loads((Path(temp) / "steam_games.json").read_text())
            self.assertEqual(written["total_unique_games"], 1)
            self.assertEqual(written["total_hours"], 2.5)


if __name__ == "__main__":
    unittest.main()
