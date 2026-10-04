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
    python fetch_steam.py --mode api --key TU_KEY
    set STEAM_API_KEY=...  (Windows)      # o variable de entorno
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
API_URL = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/"
SUMMARIES_URL = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
USER_AGENT = "steam-tracker/1.0 (+local)"


def http_get(url: str, params: dict | None = None, timeout: int = 30) -> bytes:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def http_json(url: str, params: dict | None = None) -> dict:
    return json.loads(http_get(url, params).decode("utf-8", "replace"))


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
    if games is None:
        raise RuntimeError(
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
        raise RuntimeError(
            "el perfil no expone juegos: biblioteca privada / solo amigos "
            "o el XML no es accesible"
        )
    return out


def profile_name(key: str, steamid: str) -> str:
    try:
        data = http_json(SUMMARIES_URL, {"key": key, "steamids": steamid})
        players = data.get("response", {}).get("players") or []
        if players:
            return players[0].get("personaname", "") or ""
    except Exception:
        pass
    return ""


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
        e["last_played_iso"] = iso_from_unix(e["last_played"])
    result.sort(key=lambda g: (-g["total_hours"], g["name"].lower()))
    return result


def esc_pipe(text: str) -> str:
    return text.replace("|", "\\|")


def render_md(accounts: list[dict], games: list[dict], mode: str) -> str:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
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
    lines.append("| Juego | AppID | Cuentas | Horas totales | Ult. vez |")
    lines.append("|---|---|---|---|---|")
    for g in games:
        cuentas = ", ".join(
            f"{alias} ({hours:g}h)" for alias, hours in g["accounts"].items()
        )
        lines.append(
            f"| {esc_pipe(g['name'])} | {g['appid']} | {cuentas} | "
            f"{g['total_hours']:g} | {g['last_played_iso'] or '-'} |"
        )
    lines.append("")
    lines.append("> Fuente de verdad para consultas exactas: `steam_games.json`.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Consolida varias cuentas de Steam.")
    parser.add_argument("--config", default=str(BASE_DIR / "accounts.json"))
    parser.add_argument("--mode", choices=["auto", "api", "xml"], default="auto")
    parser.add_argument("--key", default="", help="Steam Web API key (1 sola para todas)")
    parser.add_argument("--out-dir", default=str(BASE_DIR))
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"[!] No existe {config_path}. Crea accounts.json primero.", file=sys.stderr)
        return 1
    config = json.loads(config_path.read_text(encoding="utf-8"))
    accounts = config.get("accounts") or []
    if not accounts:
        print("[!] accounts.json no tiene cuentas.", file=sys.stderr)
        return 1

    key = args.key or os.environ.get("STEAM_API_KEY", "") or config.get("api_key", "")
    mode = args.mode
    if mode == "auto":
        mode = "api" if key else "xml"
    if mode == "api" and not key:
        print("[!] Falta la API key (--key, STEAM_API_KEY o accounts.json).", file=sys.stderr)
        return 1

    print(f"[i] Modo: {mode}. Cuentas: {len(accounts)}")
    libraries: dict[str, dict] = {}
    for acc in accounts:
        alias, steamid = acc["alias"], acc["steamid"]
        if "XXXX" in steamid or "YYYY" in steamid or "ZZZZ" in steamid:
            print(f"    - {alias}: placeholder sin rellenar, se omite.")
            continue
        try:
            if mode == "api":
                acc["personaname"] = profile_name(key, steamid)
                lib = owned_via_api(key, steamid)
            else:
                lib = owned_via_xml(steamid)
            libraries[alias] = lib
            print(f"    - {alias}: {len(lib)} juegos")
        except (urllib.error.URLError, RuntimeError, ET.ParseError) as exc:
            print(f"    - {alias}: ERROR -> {exc}")

    if not libraries:
        print("[!] No se pudo leer ninguna cuenta. Revisa IDs, privacidad o conexion.", file=sys.stderr)
        return 2

    games = merge(accounts, libraries)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    md_path = out_dir / "steam_games.md"
    json_path = out_dir / "steam_games.json"
    md_path.write_text(render_md(accounts, games, mode), encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "generated": datetime.now(timezone.utc).isoformat(),
                "source": mode,
                "accounts": accounts,
                "total_unique_games": len(games),
                "games": games,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"[ok] {len(games)} juegos unicos -> {md_path.name} + {json_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
