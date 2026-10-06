"""Bibliotecas compartidas. Propiedad y horas son datos distintos."""

from fetch_steam import iso_from_unix
from steam_common import SteamError, http_json, public_accounts

BASE = "https://api.steampowered.com/IFamilyGroupsService/"


def fetch_family(config, account_alias=None):
    candidates = [a for a in config["accounts"] if a.get("access_token") and
                  (not account_alias or a["alias"] == account_alias)]
    if not candidates:
        raise SteamError("Falta access_token para Steam Families. Usa --skip-family para actualizar solo juegos propios.")
    account = candidates[0]
    auth = {"access_token": account["access_token"], "format": "json"}
    try:
        response = http_json(BASE + "GetFamilyGroupForUser/v1/", {**auth, "steamid": account["steamid"]}).get("response", {})
    except SteamError as exc:
        raise SteamError(f"No se pudo consultar GetFamilyGroupForUser para {account['alias']}: {exc}") from None
    group = response.get("family_groupid")
    if not group or str(group) == "0":
        raise SteamError("Steam no devolvió una familia. Revisa la cuenta y renueva su access_token.")
    try:
        response = http_json(BASE + "GetSharedLibraryApps/v1/", {
            **auth, "family_groupid": group, "steamid": account["steamid"],
            "include_own": "true", "include_excluded": "false", "include_non_games": "false",
            "language": "spanish",
        }).get("response", {})
    except SteamError as exc:
        raise SteamError(f"No se pudo consultar GetSharedLibraryApps para {account['alias']}: {exc}") from None
    apps = response.get("apps")
    if not isinstance(apps, list):
        raise SteamError("Steam no devolvió la biblioteca familiar. Se conservan los archivos anteriores.")
    members = {str(m["steamid"]): dict(m) for m in config.get("family_members", []) if m.get("steamid")}
    own_ids = {str(a["steamid"]) for a in config["accounts"]}
    owner_ids = {str(sid) for app in apps for sid in app.get("owner_steamids", [])} - own_ids
    unresolved = sorted(sid for sid in owner_ids if not members.get(sid, {}).get("alias"))
    if config.get("api_key"):
        for offset in range(0, len(unresolved), 100):
            try:
                profiles = http_json("https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/", {
                    "key": config["api_key"], "steamids": ",".join(unresolved[offset:offset + 100])
                }).get("response", {}).get("players", [])
                for profile in profiles:
                    sid = str(profile["steamid"])
                    member = members.setdefault(sid, {"steamid": sid})
                    member.setdefault("alias", profile.get("personaname") or sid)
                    member.setdefault("country", profile.get("loccountrycode", "").lower())
            except SteamError:
                print("[!] No se pudieron resolver algunos nombres de familia; se usan sus SteamID.")
    for sid in sorted(owner_ids):
        member = members.setdefault(sid, {"steamid": sid})
        member.setdefault("alias", sid)
    return apps, public_accounts(list(members.values()))


def merge_family(games, apps, config):
    own = {str(a["steamid"]): a["alias"] for a in config["accounts"]}
    members = {str(m["steamid"]): m for m in config.get("family_members", [])}
    by_id = {g["appid"]: g for g in games}
    for app in apps:
        if int(app.get("app_type", 1)) not in (0, 1) or app.get("exclude_reason", 0):
            continue
        appid = str(app.get("appid") or "")
        if not appid:
            continue
        game = by_id.get(appid)
        if game is None:
            game = {"appid": appid, "name": app.get("name") or f"App {appid}",
                    "accounts": {}, "total_hours": 0, "last_played": 0,
                    "last_played_iso": None, "img_icon_url": ""}
            by_id[appid] = game
            games.append(game)
        owners = list(dict.fromkeys(str(s) for s in app.get("owner_steamids", [])))
        owned_aliases = set(game["accounts"]) | {own[s] for s in owners if s in own}
        game["owned_accounts"] = sorted(owned_aliases)
        game["owned_count"] = len(owned_aliases)
        game["family"] = not bool(owned_aliases)
        external = [{"steamid": sid, "alias": members.get(sid, {}).get("alias") or sid,
                     "country": members.get(sid, {}).get("country", "")} for sid in owners if sid not in own]
        game["family_owners"] = external
        game["family_owner"] = external[0]["alias"] if external else ""
        game["family_country"] = external[0]["country"] if external else ""
        game["acquired"] = iso_from_unix(int(app.get("rt_time_acquired") or 0))
        game["img_icon_url"] = game.get("img_icon_url") or app.get("img_icon_hash", "")
        game["family_hours"] = round(float(app.get("rt_playtime") or 0) / 60, 1)
        # The shared-library endpoint gives no per-player breakdown. Never assign
        # this playtime to the selected lender or add it to owned-account hours.
        if not game["accounts"]:
            game["total_hours"] = game["family_hours"]
            game["hours_source"] = "family"
            game["last_played"] = int(app.get("rt_last_played") or 0)
            game["last_played_iso"] = iso_from_unix(game["last_played"])
        else:
            game["hours_source"] = "accounts"
