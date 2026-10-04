#!/usr/bin/env python3
"""steam-tracker: junta las bibliotecas de varias cuentas de Steam en un solo
steam_games.md (legible) y steam_games.json (fuente de verdad para el agente).

Dos modos, sin dependencias externas (solo stdlib):
  * API  -> usa UNA sola Steam Web API key para todas las cuentas.
  * XML  -> lee el perfil publico sin key.

El unico requisito es que "Detalles de juego" del perfil sea Publico.
Si es Privado/Amigos, la fuente no devuelve juegos y lo avisa.

Uso:
    python fetch_steam.py                 # auto: API si hay key, si no XML
    python fetch_steam.py --mode xml      # forzar XML publico
    python fetch_steam.py --mode api
    set STEAM_API_KEY=...  (Windows)      # o variable de entorno
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

BASE_DIR = Path(__file__).resolve().parent
API_URL = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/"
SUMMARIES_URL = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
_PROFILE_SUMMARIES: dict[str, dict[str, str]] = {}
from steam_common import SteamError, http_get, http_json, load_config, public_accounts, atomic_write
from steam_history import load_history, record_first_seen, render_history


def owned_via_api(key: str, steamid: str) -> dict[str, dict]:
    """Devuelve {appid: {name, hours, last_played}} usando la Web API."""
    data = http_json(
        API_URL,
        {
            "key": key,
            "steamid": steamid,
            "include_appinfo": 1,
            "include_played_free_games": 1,
            "format": "json",
        },
    )
    games = data.get("response", {}).get("games")
    if games is None and data.get("response", {}).get("game_count") == 0:
        games = []
    if not isinstance(games, list):
        raise SteamError(
            "la API no devolvio juegos: biblioteca privada / solo amigos, "
            "perfil invalido o cuenta sin juegos publicos"
        )
    out: dict[str, dict] = {}
    for g in games:
        appid = str(g.get("appid"))
        out[appid] = {
            "name": g.get("name") or f"App {appid}",
            "hours": round(g.get("playtime_forever", 0) / 60.0, 1),
            "last_played": int(g.get("rtime_last_played") or 0),
            "img_icon_url": g.get("img_icon_url") or "",
        }
    return out


def owned_via_xml(steamid: str) -> dict[str, dict]:
    """Devuelve {appid: {name, hours, last_played}} leyendo el XML publico."""
    url = f"https://steamcommunity.com/profiles/{steamid}/games?tab=all&xml=1"
    root = ET.fromstring(http_get(url).decode("utf-8", "replace"))
    out: dict[str, dict] = {}
    for game in root.iter("game"):
        appid = (game.findtext("appID") or "").strip()
        if not appid:
            continue
        name = (game.findtext("name") or f"App {appid}").strip()
        raw = (game.findtext("hoursOnRecord") or "0").replace(",", "").strip()
        try:
            hours = float(raw)
        except ValueError:
            hours = 0.0
        out[appid] = {"name": name, "hours": round(hours, 1), "last_played": 0, "img_icon_url": ""}
    if not out:
        raise SteamError(
            "el perfil no expone juegos: biblioteca privada / solo amigos "
            "o el XML no es accesible"
        )
    return out


def profile_name(key: str, steamid: str) -> str:
    _PROFILE_SUMMARIES.pop(steamid, None)
    try:
        data = http_json(SUMMARIES_URL, {"key": key, "steamids": steamid})
        players = data.get("response", {}).get("players") or []
        if players:
            player = players[0]
            avatar = str(player.get("avatarfull", "") or "")
            avatar_url = urlsplit(avatar)
            if (avatar_url.scheme != "https" or avatar_url.username or avatar_url.password
                    or not (avatar_url.hostname or "").endswith(".steamstatic.com")
                    or not avatar_url.path.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))):
                avatar = ""
            _PROFILE_SUMMARIES[steamid] = {
                "personaname": str(player.get("personaname", "") or ""),
                "avatar": avatar,
            }
            return _PROFILE_SUMMARIES[steamid]["personaname"]
    except Exception:
        pass
    return ""


def profile_avatar(steamid: str) -> str:
    """Return the public avatar from the summary request, if Steam supplied one."""
    return _PROFILE_SUMMARIES.get(steamid, {}).get("avatar", "")


def iso_from_unix(ts: int) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def merge(accounts: list[dict], libraries: dict[str, dict]) -> list[dict]:
    """Fusiona por appid: un juego -> horas por cuenta + total."""
    merged: dict[str, dict] = {}
    for acc in accounts:
        alias = acc["alias"]
        for appid, info in libraries.get(alias, {}).items():
            entry = merged.setdefault(
                appid,
                {
                    "appid": appid,
                    "name": info["name"],
                    "accounts": {},
                    "last_played": 0,
                    "img_icon_url": "",
                },
            )
            entry["accounts"][alias] = info["hours"]
            if info["name"] and entry["name"].startswith("App "):
                entry["name"] = info["name"]
            entry["last_played"] = max(entry["last_played"], info.get("last_played", 0))
            if info.get("img_icon_url"):
                entry["img_icon_url"] = info["img_icon_url"]
    result = list(merged.values())
    for e in result:
        e["total_hours"] = round(sum(e["accounts"].values()), 1)
        e["owned_count"] = len(e["accounts"])
        e["owned_accounts"] = sorted(e["accounts"])
        e["family"] = False
        e["hours_source"] = "accounts"
        e["last_played_iso"] = iso_from_unix(e["last_played"])
    result.sort(key=lambda g: (-g["total_hours"], g["name"].lower()))
    return result


def esc_pipe(text: str) -> str:
    return text.replace("|", "\\|")


def render_md(accounts: list[dict], games: list[dict], mode: str, generated=None) -> str:
    generated = generated or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    multi = sum(1 for g in games if g["owned_count"] > 1)
    backlog = sum(1 for g in games if g["total_hours"] == 0)
    total_hours = round(sum(g["total_hours"] for g in games), 1)

    lines: list[str] = []
    lines.append("---")
    lines.append(f"generated: {generated}")
    lines.append(f"source: {mode}")
    lines.append("accounts:")
    for a in accounts:
        lines.append(f"  - alias: {a['alias']}")
        lines.append(f"    steamid: \"{a['steamid']}\"")
        if a.get("personaname"):
            lines.append(f"    personaname: \"{a['personaname']}\"")
    lines.append(f"total_unique_games: {len(games)}")
    lines.append(f"total_hours: {total_hours}")
    lines.append("---")
    lines.append("")
    lines.append("# Biblioteca Steam (consolidada)")
    lines.append("")
    lines.append("## Resumen")
    lines.append(f"- Juegos unicos: **{len(games)}**")
    lines.append(f"- En mas de una cuenta: **{multi}**")
    lines.append(f"- Nunca jugados (backlog): **{backlog}**")
    lines.append(f"- Horas totales: **{total_hours}**")
    lines.append("")
    lines.append("## Indice")
    lines.append("")
    lines.append("| Juego | AppID | Cuentas | Familia | Horas | Adquirido | Ult. vez |")
    lines.append("|---|---|---|---|---|---|---|")
    for g in games:
        cuentas = ", ".join(
            f"{alias} ({hours:g}h)" for alias, hours in g["accounts"].items()
        )
        lines.append(
            f"| {esc_pipe(g['name'])} | {g['appid']} | {esc_pipe(cuentas)} | "
            f"{esc_pipe(g.get('family_owner', '')) if g.get('family') else '-'} | "
            f"{g['total_hours']:g} | {g.get('acquired') or '-'} | {g['last_played_iso'] or '-'} |"
        )
    lines.append("")
    lines.append("> Fuente de verdad para consultas exactas: `steam_games.json`.")
    lines.append("")
    return "\n".join(lines)


def fetch_owned(config, mode="auto"):
    """Fetch every configured account before replacing any output."""
    key = config.get("api_key", "")
    mode = ("api" if key else "xml") if mode == "auto" else mode
    if mode == "api" and not key:
        raise SteamError("Falta api_key o STEAM_API_KEY.")
    accounts = public_accounts(config["accounts"])
    libraries = {}
    for account in accounts:
        alias, sid = account["alias"], account["steamid"]
        try:
            if mode == "api":
                libraries[alias] = owned_via_api(key, sid)
                account["personaname"] = profile_name(key, sid)
                account["avatar"] = profile_avatar(sid)
            else:
                libraries[alias] = owned_via_xml(sid)
        except Exception:
            # Network exception messages can contain the authenticated URL.
            raise SteamError(f"No se pudo leer la cuenta {alias}. Revisa privacidad, credenciales y conexión. No se actualizaron los archivos.") from None
        print(f"[i] {alias}: {len(libraries[alias])} juegos")
    games = merge(accounts, libraries)
    return {
        "generated": datetime.now(timezone.utc).isoformat(), "source": mode,
        "accounts": accounts, "total_unique_games": len(games),
        "total_hours": round(sum(g["total_hours"] for g in games), 1), "games": games,
    }


def main():
    parser = argparse.ArgumentParser(description="Solo bibliotecas propias. Para el flujo completo usa update.py.")
    parser.add_argument("--config", type=Path, default=BASE_DIR / "accounts.json")
    parser.add_argument("--mode", choices=["auto", "api", "xml"], default="auto")
    parser.add_argument("--out-dir", type=Path, default=BASE_DIR)
    parser.add_argument("--history", type=Path, help="Ruta del historial local de primeras detecciones")
    args = parser.parse_args()
    try:
        data = fetch_owned(load_config(args.config), args.mode)
        history_path = args.history or args.out_dir / "steam_history.json"
        history = record_first_seen(
            load_history(history_path),
            (game["appid"] for game in data["games"]),
            data["generated"][:10],
        )
        for game in data["games"]:
            game["first_seen"] = history[str(game["appid"])]
        from update import publish
        publish(data, args.out_dir)
        atomic_write(history_path, render_history(history))
    except SteamError as exc:
        print(f"[!] {exc}", file=sys.stderr)
        return 1
    print(f"[ok] {len(data['games'])} juegos propios. Usa update.py para incluir familia y metadatos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
