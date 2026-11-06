import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import build_web
import steam_artwork
import update

ART = "https://shared.akamai.steamstatic.com/store_item_assets/steam/clusters/seasonalsales/{}/page_bg_{}english.webp"
AUTUMN_DESKTOP, AUTUMN_MOBILE = ART.format("autumn", ""), ART.format("autumn", "mobile_")
WINTER_DESKTOP, WINTER_MOBILE = ART.format("winter", ""), ART.format("winter", "mobile_")
AUTUMN = {"name": "Autumn", "type": "sale", "start": "2026-10-01T10:00:00-07:00", "end": "2026-10-08T10:00:00-07:00"}
WINTER = {"name": "Winter", "type": "sale", "start": "2026-12-17T10:00:00-08:00", "end": "2027-01-04T10:00:00-08:00"}
FEST = {"name": "Fest", "type": "festival", "start": "2026-12-01T10:00:00-08:00", "end": "2026-12-08T10:00:00-08:00"}
DURING_WINTER = datetime(2026, 12, 20, tzinfo=timezone.utc)
BETWEEN_SALES = datetime(2026, 11, 6, tzinfo=timezone.utc)


def store_page(desktop=WINTER_DESKTOP, mobile=WINTER_MOBILE):
    return (f'<div class="page_background_holder" style="background-image: url(\'{desktop}\')"></div>'
            f'<div class="page_background_holder_mobile" style="background-image: url({mobile})"></div>')


class FakeResponse(io.BytesIO):
    pass


def fetch_returning(page):
    return lambda request, timeout: FakeResponse(page.encode("utf-8"))


def failing_fetch(request, timeout):
    raise OSError("https://secret.example/?key=PRIVATE")


class ArtworkCase(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "steam_artwork.json"
        self.events = Path(temp.name) / "steam_events.json"
        self.events.write_text(json.dumps({"events": [AUTUMN, FEST, WINTER]}))

    def refresh(self, fetch, now):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            changed = steam_artwork.refresh_sale_artwork(self.path, self.events, fetch=fetch, now=now)
        return changed, stderr.getvalue()

    def saved(self):
        return steam_artwork.load_sales(self.path)


class ParserTests(unittest.TestCase):
    def test_extracts_desktop_and_mobile_backgrounds(self):
        self.assertEqual(steam_artwork.extract_sale_artwork(store_page()),
                         {"desktop": WINTER_DESKTOP, "mobile": WINTER_MOBILE})

    def test_page_without_sale_markup_has_no_artwork(self):
        self.assertEqual(steam_artwork.extract_sale_artwork('<div class="home_page"></div>'), {})

    def test_rejects_images_outside_steam_seasonal_path(self):
        page = store_page(desktop="https://evil.example/store_item_assets/steam/clusters/seasonalsales/x/page_bg_english.webp",
                          mobile="https://shared.akamai.steamstatic.com/other/page_bg_mobile_english.webp")
        self.assertEqual(steam_artwork.extract_sale_artwork(page), {})


class ActiveSaleTests(unittest.TestCase):
    def test_start_is_inclusive_and_end_is_exclusive(self):
        start = datetime.fromisoformat(WINTER["start"])
        end = datetime.fromisoformat(WINTER["end"])
        self.assertEqual(steam_artwork.active_sale([WINTER], start), WINTER)
        self.assertIsNone(steam_artwork.active_sale([WINTER], end))

    def test_festivals_and_invalid_dates_are_not_sales(self):
        self.assertIsNone(steam_artwork.active_sale(
            [FEST, {"name": "Bad", "type": "sale", "start": "soon", "end": None}],
            datetime(2026, 12, 2, tzinfo=timezone.utc)))


class RefreshTests(ArtworkCase):
    def test_saves_art_under_the_active_sale(self):
        changed, warnings = self.refresh(fetch_returning(store_page()), DURING_WINTER)
        self.assertTrue(changed)
        self.assertEqual(warnings, "")
        self.assertEqual(self.saved(), [{**{k: WINTER[k] for k in ("name", "start", "end")},
                                         "desktop": WINTER_DESKTOP, "mobile": WINTER_MOBILE}])

    def test_new_sale_does_not_replace_previous_sale_art(self):
        self.path.write_text(json.dumps({"sales": [{**AUTUMN, "desktop": AUTUMN_DESKTOP, "mobile": AUTUMN_MOBILE}]}))
        self.refresh(fetch_returning(store_page()), DURING_WINTER)
        self.assertEqual([sale["name"] for sale in self.saved()], ["Autumn", "Winter"])
        self.assertEqual(self.saved()[0]["desktop"], AUTUMN_DESKTOP)

    def test_cdn_host_change_is_not_a_change(self):
        self.refresh(fetch_returning(store_page()), DURING_WINTER)
        other_host = store_page(WINTER_DESKTOP.replace("akamai", "fastly"), WINTER_MOBILE.replace("akamai", "fastly"))
        changed, _ = self.refresh(fetch_returning(other_host), DURING_WINTER)
        self.assertFalse(changed)
        self.assertEqual(self.saved()[0]["desktop"], WINTER_DESKTOP)

    def test_steam_swapping_art_during_a_sale_updates_it(self):
        self.refresh(fetch_returning(store_page()), DURING_WINTER)
        new_art = ART.format("winter-week-2", "")
        changed, _ = self.refresh(fetch_returning(store_page(desktop=new_art)), DURING_WINTER)
        self.assertTrue(changed)
        self.assertEqual(self.saved()[0]["desktop"], new_art)

    def test_partial_page_keeps_the_other_variant(self):
        self.refresh(fetch_returning(store_page()), DURING_WINTER)
        page = f'<div class="page_background_holder" style="background-image: url({ART.format("new", "")})"></div>'
        self.refresh(fetch_returning(page), DURING_WINTER)
        self.assertEqual(self.saved()[0]["mobile"], WINTER_MOBILE)

    def test_art_outside_any_scheduled_sale_warns_and_is_not_saved(self):
        changed, warnings = self.refresh(fetch_returning(store_page()), BETWEEN_SALES)
        self.assertFalse(self.saved())
        self.assertIn("steam_events.json", warnings)
        self.assertTrue(changed)  # the empty manifest did not exist yet

    def test_known_art_lingering_after_the_sale_is_silent(self):
        self.refresh(fetch_returning(store_page()), DURING_WINTER)
        changed, warnings = self.refresh(fetch_returning(store_page()), datetime(2027, 1, 4, 18, 30, tzinfo=timezone.utc))
        self.assertFalse(changed)
        self.assertEqual(warnings, "")

    def test_missing_art_during_a_sale_warns_only_until_captured(self):
        _, warnings = self.refresh(fetch_returning("<html></html>"), DURING_WINTER)
        self.assertIn("Winter", warnings)
        self.refresh(fetch_returning(store_page()), DURING_WINTER)
        changed, warnings = self.refresh(fetch_returning("<html></html>"), DURING_WINTER)
        self.assertFalse(changed)
        self.assertEqual(warnings, "")

    def test_network_failure_keeps_art_and_hides_exception_text(self):
        self.refresh(fetch_returning(store_page()), DURING_WINTER)
        changed, warnings = self.refresh(failing_fetch, DURING_WINTER)
        self.assertFalse(changed)
        self.assertEqual(self.saved()[0]["desktop"], WINTER_DESKTOP)
        self.assertNotIn("PRIVATE", warnings)

    def test_keeps_only_the_most_recent_sales(self):
        sales = [{"name": f"Sale {year}", "start": f"{year}-01-01T00:00:00+00:00", "end": f"{year}-02-01T00:00:00+00:00",
                  "desktop": ART.format(year, "")} for year in range(2020, 2026)]
        self.path.write_text(json.dumps({"sales": sales}))
        self.refresh(fetch_returning(store_page()), DURING_WINTER)
        self.assertEqual([sale["name"] for sale in self.saved()], ["Sale 2023", "Sale 2024", "Sale 2025", "Winter"])


class ManifestTests(ArtworkCase):
    def test_legacy_format_becomes_the_autumn_sale_and_is_rewritten(self):
        self.path.write_text(json.dumps({"source": "steam-store", "artwork": {"desktop": AUTUMN_DESKTOP, "mobile": AUTUMN_MOBILE}}))
        changed, _ = self.refresh(fetch_returning("<html></html>"), BETWEEN_SALES)
        self.assertTrue(changed)
        stored = json.loads(self.path.read_text())
        self.assertNotIn("artwork", stored)
        self.assertEqual(stored["sales"][0]["name"], "Steam Autumn Sale 2026")
        self.assertEqual(stored["sales"][0]["desktop"], AUTUMN_DESKTOP)

    def test_invalid_manifests_read_as_empty(self):
        for content in ("not json", "[]", '{"sales": "x"}', '{"sales": [{"name": "x"}]}',
                        json.dumps({"sales": [{**AUTUMN, "desktop": "https://evil.example/a.webp"}]})):
            self.path.write_text(content)
            self.assertEqual(steam_artwork.load_sales(self.path), [], content)

    def test_repository_events_cover_the_legacy_sale(self):
        events = json.loads((Path(steam_artwork.__file__).parent / "steam_events.json").read_text(encoding="utf-8"))["events"]
        match = next(event for event in events if event["name"] == steam_artwork.LEGACY_SALE["name"])
        self.assertEqual((match["start"], match["end"]), (steam_artwork.LEGACY_SALE["start"], steam_artwork.LEGACY_SALE["end"]))


class PublishTests(ArtworkCase):
    def snapshot(self):
        return {"generated": "2026-11-06T00:00:00+00:00", "source": "api", "accounts": [], "games": []}

    def test_html_embeds_sale_art(self):
        self.path.write_text(json.dumps({"sales": [{**AUTUMN, "desktop": AUTUMN_DESKTOP}]}))
        with patch.object(build_web, "BASE", self.path.parent):
            html = build_web.render_html(self.snapshot(), "/*__STEAM_DATA__*/ const E = /*__STEAM_EVENTS__*/;")
        events = json.loads(html.split("const E = ", 1)[1].rstrip(";"))
        self.assertEqual(events["sale_art"][0]["desktop"], AUTUMN_DESKTOP)
        self.assertNotIn("artwork", events)

    def test_republish_rebuilds_outputs_without_config_or_requests(self):
        out = self.path.parent
        (out / "steam_games.json").write_text(json.dumps(self.snapshot()))
        with patch("update.load_config", side_effect=AssertionError("no config")), \
             patch("update.fetch_owned", side_effect=AssertionError("no requests")), \
             patch("update.refresh_sale_artwork", side_effect=AssertionError("no requests")), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(update.main(["--republish", "--out-dir", str(out)]), 0)
        self.assertTrue((out / "steam_games.html").exists())
        self.assertTrue((out / "steam_games.md").exists())

    def test_republish_fails_without_a_snapshot(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(update.main(["--republish", "--out-dir", str(self.path.parent)]), 1)


if __name__ == "__main__":
    unittest.main()
