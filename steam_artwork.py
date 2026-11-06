#!/usr/bin/env python3
"""Guarda, por oferta estacional, los fondos que Steam muestra en su tienda."""

from datetime import datetime, timezone
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from steam_common import atomic_write

BASE = Path(__file__).resolve().parent
ARTWORK_FILE = BASE / "steam_artwork.json"
EVENTS_FILE = BASE / "steam_events.json"
MAX_SALES_KEPT = 4
# Formato anterior: {"artwork": {...}} sin oferta. Ese arte se capturó el 2026-10-04,
# durante esta oferta. Se puede borrar cuando steam-data tenga el formato nuevo.
LEGACY_SALE = {
    "name": "Steam Autumn Sale 2026",
    "start": "2026-10-01T10:00:00-07:00",
    "end": "2026-10-08T10:00:00-07:00",
}
ART_KEYS = ("desktop", "mobile")
STEAM_STORE_URL = "https://store.steampowered.com/?l=english"
ARTWORK_TIMEOUT_SECONDS = 8
ARTWORK_HOST_SUFFIX = ".steamstatic.com"
ARTWORK_PATH = "/store_item_assets/steam/clusters/seasonalsales/"
ARTWORK_RE = re.compile(r"url\(\s*['\"]?([^)'\"]+)['\"]?\s*\)", re.I)


def _canonical_steam_artwork(value):
    """Accept only Steam seasonal-sale desktop/mobile image resources."""
    candidate = urlsplit(value)
    host = (candidate.hostname or "").lower()
    filename = candidate.path.rsplit("/", 1)[-1]
    if (candidate.scheme != "https" or candidate.username or candidate.password
            or not host.endswith(ARTWORK_HOST_SUFFIX)
            or ARTWORK_PATH not in candidate.path
            or filename not in {"page_bg_english.webp", "page_bg_mobile_english.webp"}):
        return None
    return urlunsplit((candidate.scheme, candidate.netloc, candidate.path, "", ""))


class _SaleArtworkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.artwork = {}

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        target = None
        if "page_background_holder" in classes:
            target = "desktop"
        elif "page_background_holder_mobile" in classes:
            target = "mobile"
        if not target:
            return
        style = attributes.get("style") or ""
        for match in ARTWORK_RE.finditer(style):
            artwork_url = _canonical_steam_artwork(match.group(1).strip())
            if artwork_url:
                self.artwork[target] = artwork_url
                break


def extract_sale_artwork(page_html):
    """Return Steam's current seasonal-sale backgrounds found in store HTML."""
    parser = _SaleArtworkParser()
    parser.feed(page_html)
    return parser.artwork


def _parse_time(value):
    """Return an aware datetime, or None if the value is not a usable timestamp."""
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else None


def active_sale(events, now):
    """Return the scheduled seasonal sale running at `now`, if any."""
    for event in events:
        if not isinstance(event, dict) or event.get("type") != "sale" or not isinstance(event.get("name"), str):
            continue
        start, end = _parse_time(event.get("start")), _parse_time(event.get("end"))
        if start and end and start <= now < end:
            return event
    return None


def _clean_sale(entry):
    """Keep one manifest entry only if it has valid dates and valid Steam images."""
    if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
        return None
    if not _parse_time(entry.get("start")) or not _parse_time(entry.get("end")):
        return None
    art = {}
    for key in ART_KEYS:
        url = _canonical_steam_artwork(entry[key]) if isinstance(entry.get(key), str) else None
        if url:
            art[key] = url
    if not art:
        return None
    return {"name": entry["name"], "start": entry["start"], "end": entry["end"], **art}


def load_sales(path):
    """Read the manifest as a list ordered by sale start; bad data reads as empty."""
    try:
        manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(manifest, dict):
        return []
    if isinstance(manifest.get("sales"), list):
        entries = manifest["sales"]
    elif isinstance(manifest.get("artwork"), dict):
        entries = [{**LEGACY_SALE, **manifest["artwork"]}]
    else:
        return []
    sales = [sale for sale in map(_clean_sale, entries) if sale]
    return sorted(sales, key=lambda sale: _parse_time(sale["start"]))


def _load_events(path):
    try:
        events = json.loads(Path(path).read_text(encoding="utf-8")).get("events", [])
    except (OSError, ValueError, AttributeError):
        return []
    return events if isinstance(events, list) else []


def _warn(message):
    """Show a warning on stderr, and as an annotation when running in Actions."""
    prefix = "::warning::" if os.environ.get("GITHUB_ACTIONS") else "[!] "
    print(prefix + message, file=sys.stderr)


def _same_image(first, second):
    """Steam serves one image from several CDN hosts, so only the path identifies it."""
    return bool(first and second) and urlsplit(first).path == urlsplit(second).path


def _merge_art(sales, sale, found):
    """Return the manifest with `found` stored under `sale`."""
    current = next((item for item in sales if item["name"] == sale["name"]), {})
    merged = {"name": sale["name"], "start": sale["start"], "end": sale["end"]}
    for key in ART_KEYS:
        url = current.get(key)
        if key in found and not _same_image(url, found[key]):
            url = found[key]
        if url:
            merged[key] = url
    others = [item for item in sales if item["name"] != sale["name"]]
    updated = sorted(others + [merged], key=lambda item: _parse_time(item["start"]))
    return updated[-MAX_SALES_KEPT:]


def _fetch_store_artwork(fetch):
    request = Request(
        STEAM_STORE_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; SteamTracker/1.0)",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with fetch(request, timeout=ARTWORK_TIMEOUT_SECONDS) as response:
        return extract_sale_artwork(response.read().decode("utf-8", "replace"))


def refresh_sale_artwork(path=ARTWORK_FILE, events_path=EVENTS_FILE, *, fetch=urlopen, now=None):
    """Update the manifest and return True if it changed; failures never block updates."""
    path = Path(path)
    now = now or datetime.now(timezone.utc)
    sales = load_sales(path)
    sale = active_sale(_load_events(events_path), now)
    try:
        found = _fetch_store_artwork(fetch)
    except Exception:
        found = {}

    if sale and found:
        sales = _merge_art(sales, sale, found)
    elif found:
        known = any(_same_image(item.get(key), url) for item in sales for key, url in found.items())
        if not known:
            _warn("Steam muestra arte de una oferta que no está activa en steam_events.json; no se guardó.")
    elif sale and not any(item["name"] == sale["name"] for item in sales):
        _warn(f"No se encontró el arte de {sale['name']} en la tienda de Steam.")

    serialized = json.dumps({"source": "steam-store", "sales": sales}, ensure_ascii=False, indent=2) + "\n"
    try:
        if path.exists() and path.read_text(encoding="utf-8") == serialized:
            return False
        atomic_write(path, serialized)
        return True
    except OSError:
        return False


def main():
    changed = refresh_sale_artwork()
    print("[i] Arte actualizado." if changed else "[i] Sin cambios en el arte.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
