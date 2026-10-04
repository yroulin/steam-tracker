"""Obtiene los fondos de campaña que Steam muestra actualmente en su tienda."""

from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from steam_common import atomic_write

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


def refresh_sale_artwork(path, *, fetch=urlopen):
    """Refresh a small last-known-good manifest; failures never block updates."""
    path = Path(path)
    try:
        request = Request(
            STEAM_STORE_URL,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; SteamTracker/1.0)",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        with fetch(request, timeout=ARTWORK_TIMEOUT_SECONDS) as response:
            page_html = response.read().decode("utf-8", "replace")
        found = extract_sale_artwork(page_html)
    except Exception:
        return False

    if not found:
        return False
    try:
        current = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if not isinstance(current, dict):
            current = {}
        previous = current.get("artwork", {})
        artwork = dict(previous) if isinstance(previous, dict) else {}
        artwork.update(found)
        updated = {"source": "steam-store", "artwork": artwork}
        serialized = json.dumps(updated, ensure_ascii=False, indent=2) + "\n"
        if path.exists() and path.read_text(encoding="utf-8") == serialized:
            return False
        atomic_write(path, serialized)
        return True
    except (OSError, TypeError, ValueError):
        return False
