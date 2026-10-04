import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fetch_steam


CONFIG = {"api_key": "PRIVATE_KEY", "accounts": [
    {"alias": "main", "steamid": "76561198000000001", "access_token": "PRIVATE_TOKEN"},
    {"alias": "alt", "steamid": "76561198000000002"}],
    "family_members": [{"alias": "Friend", "steamid": "76561198000000003", "country": "cr"}]}


def library():
    return [{"appid": "10", "name": "Game", "accounts": {"main": 2.5},
             "total_hours": 2.5, "owned_count": 1, "last_played": 0,
             "last_played_iso": None, "img_icon_url": ""}]


class MigrationTests(unittest.TestCase):
    def test_legacy_entrypoint_does_not_publish_tokens(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = Path(temp) / "accounts.json"
            cfg.write_text(json.dumps(CONFIG))
            with patch("sys.argv", ["fetch_steam.py", "--config", str(cfg), "--out-dir", temp]), \
                 patch.object(fetch_steam, "owned_via_api", return_value={}), \
                 patch.object(fetch_steam, "profile_name", return_value="Player"), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(fetch_steam.main(), 0)
            published = (Path(temp) / "steam_games.json").read_text()
            self.assertNotIn("PRIVATE_TOKEN", published)
            self.assertNotIn("PRIVATE_KEY", published)
            self.assertEqual(json.loads(published)["total_hours"], 0)

    def test_family_does_not_reclassify_owned_or_overwrite_hours(self):
        from steam_family import merge_family
        games = library()
        apps = [{"appid": 10, "name": "Game", "owner_steamids": [CONFIG["accounts"][0]["steamid"], CONFIG["family_members"][0]["steamid"]], "rt_playtime": 999, "rt_time_acquired": 1704067200}]
        merge_family(games, apps, CONFIG)
        self.assertFalse(games[0]["family"])
        self.assertEqual(games[0]["accounts"], {"main": 2.5})
        self.assertEqual(games[0]["total_hours"], 2.5)
        self.assertEqual(games[0]["acquired"], "2024-01-01")

    def test_family_ownership_uses_all_my_accounts_and_all_owners(self):
        from steam_family import merge_family
        games = []
        merge_family(games, [{"appid": 20, "owner_steamids": [CONFIG["family_members"][0]["steamid"], CONFIG["accounts"][1]["steamid"]]}], CONFIG)
        self.assertFalse(games[0]["family"])
        self.assertEqual(games[0]["owned_count"], 1)
        self.assertEqual(games[0]["owned_accounts"], ["alt"])

    def test_shared_hours_are_not_assigned_to_owner(self):
        from steam_family import merge_family
        games = []
        merge_family(games, [{"appid": 30, "name": "Shared", "owner_steamids": [CONFIG["family_members"][0]["steamid"]], "rt_playtime": 120}], CONFIG)
        self.assertTrue(games[0]["family"])
        self.assertEqual(games[0]["accounts"], {})
        self.assertEqual(games[0]["owned_count"], 0)
        self.assertEqual(games[0]["family_hours"], 2)
        self.assertEqual(games[0]["family_owner"], "Friend")

    def test_only_games_not_dlc_or_software(self):
        from steam_family import merge_family
        games = []
        merge_family(games, [{"appid": n, "app_type": kind} for n, kind in [(1, 1), (2, 2), (3, 4), (4, 0)]], CONFIG)
        self.assertEqual({g["appid"] for g in games}, {"1", "4"})

    def test_html_embedding_cannot_close_script(self):
        from build_web import render_html
        data = {"games": [{"name": "</ScRiPt><script>alert(1)</script> & test"}]}
        html = render_html(data, "const DATA = /*__STEAM_DATA__*/;")
        self.assertNotIn("</", html)
        self.assertEqual(json.loads(html[len("const DATA = "):-1]), data)

    def test_failed_update_preserves_all_existing_outputs_and_hides_errors(self):
        import update
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cfg = root / "accounts.json"
            cfg.write_text(json.dumps(CONFIG))
            for name in ("steam_games.json", "steam_games.md", "steam_games.html"):
                (root / name).write_text("original")
            output = io.StringIO()
            with patch("fetch_steam.owned_via_api", side_effect=RuntimeError("url?key=PRIVATE_KEY&access_token=PRIVATE_TOKEN")), \
                 patch("fetch_steam.profile_name", return_value=""), \
                 contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                self.assertNotEqual(update.main(["--config", str(cfg), "--out-dir", temp]), 0)
            self.assertNotIn("PRIVATE_KEY", output.getvalue())
            self.assertNotIn("PRIVATE_TOKEN", output.getvalue())
            for name in ("steam_games.json", "steam_games.md", "steam_games.html"):
                self.assertEqual((root / name).read_text(), "original")

    def test_full_pipeline_generates_consistent_outputs_without_secrets(self):
        import update
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cfg = root / "accounts.json"
            cfg.write_text(json.dumps(CONFIG))
            def fake_json(url, params=None):
                if "GetFamilyGroupForUser" in url:
                    return {"response": {"family_groupid": "123"}}
                if "GetSharedLibraryApps" in url:
                    return {"response": {"apps": [{"appid": 30, "name": "Shared", "owner_steamids": [CONFIG["family_members"][0]["steamid"]], "rt_playtime": 120}]}}
                return {"response": {"players": []}}
            with patch("fetch_steam.owned_via_api", return_value={"10": {"name": "Game", "hours": 1, "last_played": 0}}), \
                 patch("fetch_steam.profile_name", return_value=""), \
                 patch("steam_family.http_json", side_effect=fake_json), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(update.main(["--config", str(cfg), "--out-dir", temp, "--skip-meta"]), 0)
            data = json.loads((root / "steam_games.json").read_text())
            self.assertEqual(data["total_unique_games"], 2)
            self.assertEqual(data["total_hours"], 4)
            for name in ("steam_games.json", "steam_games.md", "steam_games.html"):
                text = (root / name).read_text()
                self.assertIn("Shared", text)
                self.assertNotIn("PRIVATE_", text)
            self.assertNotIn("/*__STEAM_DATA__*/", (root / "steam_games.html").read_text())

    def test_metadata_prices_achievements_and_free_games(self):
        from steam_meta import enrich_metadata
        games = library()
        def fake_json(url, params=None):
            if "appdetails" in url:
                return {"10": {"success": True, "data": {"is_free": False, "price_overview": {"final": 1000, "currency": "USD"}, "genres": [{"description": "Action"}], "release_date": {"date": "2020"}}}}
            return {"playerstats": {"success": True, "achievements": [{"achieved": 1}, {"achieved": 0}]}}
        with tempfile.TemporaryDirectory() as temp, patch("steam_meta.http_json", side_effect=fake_json):
            enrich_metadata(games, CONFIG, Path(temp) / "cache.json", sleep_ms=0, genres=True)
        game = games[0]
        self.assertEqual(game["price_usd"], 10)
        self.assertEqual(game["cost_per_hour"], 4)
        self.assertEqual(game["achievements_pct"], 50)
        self.assertEqual(game["genres"], ["Action"])

    def test_metadata_cache_reuses_prices_but_refreshes_achievements(self):
        from steam_meta import enrich_metadata
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "cache.json"
            with patch("steam_meta.http_json", return_value={"10": {"success": True, "data": {"is_free": True}}}):
                enrich_metadata(library(), CONFIG, path, sleep_ms=0, no_achievements=True)
            with patch("steam_meta.http_json", return_value={"playerstats": {"success": True, "achievements": []}}) as http:
                games = library()
                enrich_metadata(games, CONFIG, path, sleep_ms=0)
                self.assertEqual(http.call_count, 1)
                self.assertIn("GetPlayerAchievements", http.call_args.args[0])
                self.assertEqual(games[0]["price_usd"], 0)

    def test_invalid_token_does_not_publish_partial_library(self):
        from steam_family import fetch_family
        with patch("steam_family.http_json", return_value={"response": {}}):
            with self.assertRaises(RuntimeError):
                fetch_family(copy.deepcopy(CONFIG))


if __name__ == "__main__":
    unittest.main()
