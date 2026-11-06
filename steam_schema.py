"""Contrato del snapshot publicado: valida tipos antes de generar la web.

La página usa estos campos directamente, sin defensas, así que un valor del tipo
equivocado (por ejemplo `total_hours: "2.5"`) rompe los filtros en silencio. Esta
validación corre antes de escribir los artefactos y falla la ejecución en vez de
publicar una biblioteca rota.
"""

import re

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_APPID = re.compile(r"^\d+$")
_HOURS_SOURCES = {"accounts", "family"}


class SnapshotError(ValueError):
    """El snapshot no cumple el contrato que consume la página."""


def _fail(where, message):
    raise SnapshotError(f"{where}: {message}")


def _number(value, where, field, *, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(where, f"{field} debe ser numérico")
    if value < minimum:
        _fail(where, f"{field} no puede ser negativo")
    return value


def _optional_number(value, where, field):
    if value is None:
        return
    _number(value, where, field)


def _date(value, where, field):
    if value is None:
        return
    if not isinstance(value, str) or not _DATE.match(value):
        _fail(where, f"{field} debe usar YYYY-MM-DD")


def validate_snapshot(data):
    """Comprueba el snapshot normalizado y lanza ``SnapshotError`` si no sirve."""
    if not isinstance(data, dict):
        raise SnapshotError("el snapshot debe ser un objeto JSON")
    version = data.get("schema_version")
    if version is not None and (not isinstance(version, int) or isinstance(version, bool) or version < 1):
        raise SnapshotError("schema_version debe ser un entero positivo")
    v2 = isinstance(version, int) and version >= 2

    games = data.get("games")
    if not isinstance(games, list):
        raise SnapshotError("games debe ser una lista")
    if not isinstance(data.get("generated"), str) or not data["generated"]:
        raise SnapshotError("generated debe ser una fecha ISO en texto")
    if not isinstance(data.get("source"), str):
        raise SnapshotError("source debe ser texto")
    if not isinstance(data.get("accounts"), list):
        raise SnapshotError("accounts debe ser una lista")
    if not isinstance(data.get("family_members", []), list):
        raise SnapshotError("family_members debe ser una lista")

    seen = set()
    for index, game in enumerate(games):
        where = f"games[{index}]"
        if not isinstance(game, dict):
            _fail(where, "debe ser un objeto")
        appid = game.get("appid")
        if not isinstance(appid, str) or not _APPID.match(appid):
            _fail(where, "appid debe ser texto numérico")
        where = f"games[{index}] ({appid})"
        if appid in seen:
            _fail(where, "appid duplicado")
        seen.add(appid)
        if not isinstance(game.get("name"), str) or not game["name"].strip():
            _fail(where, "name debe ser texto no vacío")
        _number(game.get("total_hours"), where, "total_hours")
        accounts = game.get("accounts")
        if not isinstance(accounts, dict):
            _fail(where, "accounts debe ser un objeto")
        for alias, hours in accounts.items():
            if not isinstance(alias, str):
                _fail(where, "las claves de accounts deben ser texto")
            _number(hours, where, f"accounts[{alias}]")
        if game.get("owned_count") is not None:
            _number(game["owned_count"], where, "owned_count")
            if not isinstance(game["owned_count"], int) or isinstance(game["owned_count"], bool):
                _fail(where, "owned_count debe ser entero")
        _optional_number(game.get("price_usd"), where, "price_usd")
        _optional_number(game.get("cost_per_hour"), where, "cost_per_hour")
        _optional_number(game.get("family_hours"), where, "family_hours")
        for field in ("first_seen", "acquired"):
            _date(game.get(field), where, field)
        last_played = game.get("last_played")
        if last_played is not None:
            _number(last_played, where, "last_played")
        if game.get("last_played_iso") is not None and not isinstance(game["last_played_iso"], str):
            _fail(where, "last_played_iso debe ser texto o null")
        if game.get("img_icon_url") is not None and not isinstance(game["img_icon_url"], str):
            _fail(where, "img_icon_url debe ser texto o null")
        if game.get("is_free") is not None and not isinstance(game["is_free"], bool):
            _fail(where, "is_free debe ser booleano")
        complete = game.get("achievements_complete")
        if complete is not None and not isinstance(complete, bool):
            _fail(where, "achievements_complete debe ser booleano")
        for field in ("achievements_got", "achievements_total"):
            if game.get(field) is not None:
                _number(game[field], where, field)
                if not isinstance(game[field], int) or isinstance(game[field], bool):
                    _fail(where, f"{field} debe ser entero")
        if game.get("achieved_by") is not None:
            achieved = game["achieved_by"]
            if not isinstance(achieved, dict):
                _fail(where, "achieved_by debe ser un objeto")
            for alias, entry in achieved.items():
                if not isinstance(entry, dict):
                    _fail(where, f"achieved_by[{alias}] debe ser un objeto")
                _number(entry.get("got"), where, f"achieved_by[{alias}].got")
                _number(entry.get("total"), where, f"achieved_by[{alias}].total")
        if v2:
            if not isinstance(game.get("family"), bool):
                _fail(where, "family debe ser booleano en schema_version 2")
            if game.get("hours_source") not in _HOURS_SOURCES:
                _fail(where, "hours_source debe ser 'accounts' o 'family'")
            if not isinstance(game.get("owned_accounts"), list):
                _fail(where, "owned_accounts debe ser una lista en schema_version 2")
            for alias in game["owned_accounts"]:
                if not isinstance(alias, str):
                    _fail(where, "owned_accounts debe contener alias de texto")
    return data
