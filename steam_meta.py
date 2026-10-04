"""Precios USD, logros y géneros opcionales con caché de tienda de 24 horas."""

import json
import time
from pathlib import Path

from steam_common import SteamError, atomic_write, http_json


def enrich_metadata(games, config, cache_path, *, sleep_ms=900, refresh=False,
                    no_achievements=False, genres=False):
    cache_path = Path(cache_path)
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        if not isinstance(cache, dict):
            cache = {}
    except (FileNotFoundError, ValueError):
        cache = {}
    warnings = {"prices": 0, "achievements": 0}
    key = config.get("api_key", "")
    eligible = {a["alias"]: a for a in config["accounts"] if not a.get("skip_achievements", False)}
    for index, game in enumerate(games, 1):
        appid = game["appid"]
        entry = cache.get(appid, {})
        if not isinstance(entry, dict):
            entry = {}
        fresh = time.time() - entry.get("fetched_at", 0) < 86400
        if refresh or not fresh:
            try:
                response = http_json("https://store.steampowered.com/api/appdetails", {
                    "appids": appid, "cc": "us", "l": "spanish",
                }).get(appid, {})
                if "success" not in response:
                    raise SteamError("Respuesta de tienda incompleta.")
                details = response.get("data", {}) if response["success"] else {}
                price = details.get("price_overview", {})
                free = bool(details.get("is_free", False))
                usd = 0 if free else round(price["final"] / 100, 2) if price.get("currency") == "USD" and "final" in price else None
                entry = {"price_usd": usd, "is_free": free, "fetched_at": time.time(),
                         "genres": [g["description"] for g in details.get("genres", [])],
                         "released": details.get("release_date", {}).get("date", "")}
                cache[appid] = entry
            except SteamError:
                warnings["prices"] += 1
            finally:
                time.sleep(sleep_ms / 1000)
        game["price_usd"] = entry.get("price_usd")
        game["is_free"] = entry.get("is_free", False)
        game["price_updated"] = entry.get("fetched_at")
        price, hours = game["price_usd"], game["total_hours"]
        game["cost_per_hour"] = round(price / hours, 2) if price and hours else None
        if genres:
            game["genres"] = entry.get("genres", [])
            game["released"] = entry.get("released", "")
        achieved = {}
        if key and not no_achievements:
            for alias in game["accounts"]:
                if alias not in eligible:
                    continue
                try:
                    stats = http_json("https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v0001/", {
                        "key": key, "steamid": eligible[alias]["steamid"], "appid": appid, "l": "spanish",
                    }).get("playerstats", {})
                    if not stats.get("success"):
                        warnings["achievements"] += 1
                        continue
                    achievements = stats.get("achievements", [])
                    if achievements:
                        achieved[alias] = {"got": sum(a.get("achieved") == 1 for a in achievements), "total": len(achievements)}
                except SteamError:
                    warnings["achievements"] += 1
                finally:
                    time.sleep(min(sleep_ms, 150) / 1000)
        got = sum(a["got"] for a in achieved.values())
        total = sum(a["total"] for a in achieved.values())
        game.update(achieved_by=achieved, achievements_got=got,
                    achievements_total=total, achievements_pct=round(100 * got / total) if total else None)
        if index % 50 == 0:
            print(f"[i] Metadatos: {index}/{len(games)}")
    atomic_write(cache_path, json.dumps(cache, ensure_ascii=False, indent=2))
    if any(warnings.values()):
        print(f"[!] Metadatos incompletos: {warnings['prices']} precios y {warnings['achievements']} consultas de logros sin respuesta disponible.")
    return warnings
