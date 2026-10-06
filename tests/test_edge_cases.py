import contextlib
import copy
import io
import json
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

import fetch_steam
import steam_common
import steam_family
import steam_meta
import update
from test_update import CONFIG, library


class EdgeCases(unittest.TestCase):
    def test_valid_empty_api_library(self):
        with patch("fetch_steam.http_json", return_value={"response": {"game_count": 0}}):
            self.assertEqual(fetch_steam.owned_via_api("key", "sid"), {})
        with patch("fetch_steam.http_json", return_value={"response": {}}):
            with self.assertRaises(steam_common.SteamError):
                fetch_steam.owned_via_api("key", "sid")

    def test_config_supports_windows_bom_and_rejects_duplicate_alias(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "accounts.json"
            path.write_text(json.dumps(CONFIG), encoding="utf-8-sig")
            with patch.dict("os.environ", {}, clear=True):
                self.assertEqual(steam_common.load_config(path), CONFIG)
            cfg = copy.deepcopy(CONFIG)
            cfg["accounts"][1]["alias"] = "main"
            path.write_text(json.dumps(cfg))
            with self.assertRaises(steam_common.SteamError):
                steam_common.load_config(path)

    def test_http_retries_rate_limit_and_never_prints_url(self):
        error = urllib.error.HTTPError("https://steam/?key=PRIVATE_KEY", 429, "PRIVATE_TOKEN", {}, None)
        with patch("urllib.request.urlopen", side_effect=error) as request, patch("steam_common.time.sleep"):
            with self.assertRaises(steam_common.SteamError) as caught:
                steam_common.http_get("https://steam/", {"key": "PRIVATE_KEY"})
            self.assertEqual(request.call_count, 3)
            self.assertNotIn("PRIVATE_", str(caught.exception))
            self.assertIn("429", str(caught.exception))

    def test_http_auth_failure_is_not_retried(self):
        error = urllib.error.HTTPError("https://steam/", 403, "denied", {}, None)
        with patch("urllib.request.urlopen", side_effect=error) as request, patch("steam_common.time.sleep"):
            with self.assertRaises(steam_common.SteamError):
                steam_common.http_get("https://steam/")
            self.assertEqual(request.call_count, 1)

    def test_invalid_family_token_publishes_owned_games_and_stale_family_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cfg = root / "accounts.json"
            cfg.write_text(json.dumps(CONFIG))
            family_game = {
                "appid": "99", "name": "Family game", "accounts": {},
                "total_hours": 4, "family_hours": 4, "family": True,
                "owned_count": 0, "owned_accounts": [], "hours_source": "family",
            }
            old = {
                "source": "api", "generated": "old", "accounts": [],
                "family_members": [{"alias": "Friend", "steamid": "76561198000000003"}],
                "games": [family_game],
            }
            update.publish(old, root)
            with patch("fetch_steam.owned_via_api", return_value={"10": {"name": "Fresh owned", "hours": 1, "last_played": 0}}), \
                 patch("fetch_steam.profile_name", return_value=""), \
                 patch("steam_family.http_json", return_value={"response": {}}), \
                 patch("update.refresh_sale_artwork", return_value=False), \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(update.main(["--config", str(cfg), "--out-dir", temp, "--skip-meta"]), 0)
            data = json.loads((root / "steam_games.json").read_text())
            self.assertEqual(data["family_sync_status"], "stale")
            games = {game["appid"]: game for game in data["games"]}
            self.assertIn("10", games)
            self.assertIn("99", games)
            self.assertEqual(games["99"]["total_hours"], 4)

    def test_missing_token_publishes_owned_data_and_retains_family_snapshot(self):
        cfg = copy.deepcopy(CONFIG)
        cfg["accounts"][0].pop("access_token")
        cfg["family_members"] = []
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "accounts.json"
            config.write_text(json.dumps(cfg))
            previous = {
                "games": [{"appid": "99", "name": "Family game", "accounts": {}, "family": True,
                           "total_hours": 4, "family_hours": 4, "owned_count": 0,
                           "owned_accounts": [], "hours_source": "family"}],
                "family_members": [{"alias": "Friend", "steamid": "76561198000000003"}],
            }
            (root / "steam_games.json").write_text(json.dumps(previous))
            owned = {"generated": "2026-10-06T00:00:00+00:00", "source": "api", "accounts": [],
                     "games": [], "family_members": []}
            with patch("update.fetch_owned", return_value=owned) as fetch, \
                 patch("update.refresh_sale_artwork", return_value=False), \
                 contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(update.main(["--config", str(config), "--out-dir", temp, "--skip-meta"]), 0)
                fetch.assert_called_once()
            data = json.loads((root / "steam_games.json").read_text())
            self.assertEqual(data["family_sync_status"], "stale")
            self.assertEqual(data["games"][0]["name"], "Family game")

    def test_partial_owned_failure_aborts_instead_of_dropping_account(self):
        with patch("fetch_steam.owned_via_api", side_effect=[{}, steam_common.SteamError("private")]), \
             patch("fetch_steam.profile_name", return_value=""), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(steam_common.SteamError):
                fetch_steam.fetch_owned(CONFIG)

    def test_family_multiple_owners_retained_without_duplicate_games(self):
        games = []
        apps = [{"appid": 30, "owner_steamids": ["76561198000000003", "76561198000000004"]}]
        steam_family.merge_family(games, apps * 2, CONFIG)
        self.assertEqual(len(games), 1)
        self.assertEqual(len(games[0]["family_owners"]), 2)
        self.assertIsNone(games[0]["acquired"])
        self.assertEqual(games[0]["family_owners"][1]["alias"], "76561198000000004")

    def test_zero_owned_hours_are_not_overwritten_with_family_hours(self):
        games = library()
        games[0].update(total_hours=0, accounts={"main": 0})
        steam_family.merge_family(games, [{"appid": 10, "rt_playtime": 120}], CONFIG)
        self.assertEqual(games[0]["total_hours"], 0)
        self.assertEqual(games[0]["accounts"], {"main": 0})
        self.assertEqual(games[0]["family_hours"], 2)

    def test_expired_cache_refresh_and_non_usd_is_not_labeled_usd(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "cache.json"
            path.write_text(json.dumps({"10": {"price_usd": 99, "fetched_at": time.time() - 86401}}))
            games = library()
            with patch("steam_meta.http_json", return_value={"10": {"success": True, "data": {"price_overview": {"final": 123, "currency": "EUR"}}}}) as request:
                steam_meta.enrich_metadata(games, CONFIG, path, sleep_ms=0, no_achievements=True)
                request.assert_called_once()
            self.assertIsNone(games[0]["price_usd"])

    def test_store_failure_keeps_old_price_and_private_achievements_are_unknown(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "cache.json"
            path.write_text(json.dumps({"10": {"price_usd": 12, "fetched_at": 1}}))
            games = library()
            with patch("steam_meta.http_json", side_effect=steam_common.SteamError("HTTP 403")), \
                 contextlib.redirect_stdout(io.StringIO()):
                warnings = steam_meta.enrich_metadata(games, CONFIG, path, sleep_ms=0)
            self.assertEqual(games[0]["price_usd"], 12)
            self.assertEqual(games[0]["price_updated"], 1)
            self.assertIsNone(games[0]["achievements_pct"])
            self.assertEqual(warnings, {"prices": 1, "achievements": 1})

    def test_skip_achievements_false_is_not_treated_as_true(self):
        config = copy.deepcopy(CONFIG)
        config["accounts"][0]["skip_achievements"] = False
        with tempfile.TemporaryDirectory() as temp, patch("steam_meta.http_json", return_value={"10": {"success": False}, "playerstats": {"success": True, "achievements": [{"achieved": 0}]}}) as request:
            games = library()
            steam_meta.enrich_metadata(games, config, Path(temp) / "cache.json", sleep_ms=0)
            self.assertEqual(request.call_count, 2)
            self.assertEqual(games[0]["achievements_pct"], 0)


if __name__ == "__main__":
    unittest.main()
