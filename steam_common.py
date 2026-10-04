"""HTTP, configuración y escritura compartidos, sin dependencias externas."""

import json
import os
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class SteamError(RuntimeError):
    """Error publicable: nunca incluye URLs, respuestas ni credenciales."""


def http_get(url, params=None, timeout=30):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "steam-tracker/2.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            raise SteamError(f"Steam respondió HTTP {exc.code}.") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            raise SteamError("No se pudo conectar con Steam.") from None


def http_json(url, params=None):
    try:
        value = json.loads(http_get(url, params).decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (ValueError, UnicodeError):
        raise SteamError("Steam devolvió una respuesta JSON inválida.") from None


def load_config(path):
    try:
        config = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise SteamError("Falta accounts.json. Copia tu archivo a la carpeta del proyecto o usa --config.") from None
    except (ValueError, UnicodeError):
        raise SteamError("accounts.json no contiene JSON válido.") from None
    if not isinstance(config, dict) or not isinstance(config.get("accounts"), list) or not config["accounts"]:
        raise SteamError("accounts.json debe contener una lista accounts no vacía.")
    aliases, ids = set(), set()
    for account in config["accounts"]:
        if not isinstance(account, dict):
            raise SteamError("Cada cuenta debe ser un objeto con alias y steamid.")
        alias, sid = account.get("alias"), str(account.get("steamid", ""))
        if not isinstance(alias, str) or not alias.strip() or not sid.isdecimal() or len(sid) != 17:
            raise SteamError("Cada cuenta necesita un alias y un SteamID64 de 17 dígitos.")
        if alias in aliases or sid in ids:
            raise SteamError("Hay alias o SteamID64 duplicados en accounts.")
        aliases.add(alias)
        ids.add(sid)
        account["steamid"] = sid
        if not isinstance(account.get("access_token", ""), str):
            raise SteamError("access_token debe ser texto.")
    members = config.get("family_members", [])
    if not isinstance(members, list) or any(not isinstance(m, dict) for m in members):
        raise SteamError("family_members debe ser una lista de objetos.")
    config["api_key"] = os.environ.get("STEAM_API_KEY") or config.get("api_key", "")
    if not isinstance(config["api_key"], str):
        raise SteamError("api_key debe ser texto.")
    return config


def public_accounts(accounts):
    return [{key: str(a.get(key, "")) for key in ("alias", "steamid", "personaname", "country")} for a in accounts]


def without_secrets(value):
    if isinstance(value, dict):
        return {k: without_secrets(v) for k, v in value.items() if k.lower() not in {"api_key", "access_token", "webapi_token"}}
    if isinstance(value, list):
        return [without_secrets(v) for v in value]
    return value


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as file:
            name = file.name
            file.write(text)
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)
