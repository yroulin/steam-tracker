"""Local first-seen history for the Steam tracker."""

import json
from pathlib import Path

from steam_common import SteamError


SCHEMA_VERSION = 1


def load_history(path):
    """Read the local history, returning an empty map when it does not exist."""
    path = Path(path)
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, UnicodeError):
        raise SteamError("No se pudo leer el historial local de juegos.") from None
    if (not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION
            or not isinstance(value.get("first_seen"), dict)):
        raise SteamError("El historial local de juegos tiene un formato inválido.")
    history = value["first_seen"]
    if any(not str(appid).isdecimal() or not _valid_date(date)
           for appid, date in history.items()):
        raise SteamError("El historial local de juegos tiene un formato inválido.")
    return {str(appid): date for appid, date in history.items()}


def record_first_seen(history, appids, date):
    """Return an updated map while preserving the earliest known date."""
    if not _valid_date(date):
        raise ValueError("date must use YYYY-MM-DD format")
    updated = dict(history)
    for appid in appids:
        appid = str(appid)
        if not appid.isdecimal():
            continue
        previous = updated.get(appid)
        if previous is None or date < previous:
            updated[appid] = date
    return updated


def render_history(history):
    """Serialize history deterministically for atomic writing."""
    value = {
        "schema_version": SCHEMA_VERSION,
        "first_seen": dict(sorted(history.items(), key=lambda item: int(item[0]))),
    }
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def _valid_date(value):
    if not isinstance(value, str) or len(value) != 10:
        return False
    try:
        from datetime import date
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False
