#!/usr/bin/env python3
"""Actualiza cuentas, familia, metadatos y web con Python 3.10 o posterior."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from build_web import render_html
from fetch_steam import fetch_owned, render_md
from steam_common import SteamError, atomic_write, load_config, without_secrets
from steam_family import fetch_family, merge_family
from steam_meta import enrich_metadata
from steam_history import load_history, record_first_seen, render_history
from steam_artwork import refresh_sale_artwork

BASE = Path(__file__).resolve().parent


def previous_snapshot(out_dir):
    path = Path(out_dir) / "steam_games.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) and isinstance(data.get("games"), list) else None
    except (OSError, ValueError):
        return None


def retain_family_snapshot(games, previous):
    """Carry forward known family data without replacing newly fetched owned data."""
    if not previous:
        return
    previous_games = {str(game.get("appid")): game for game in previous["games"] if game.get("appid")}
    current = {str(game.get("appid")): game for game in games if game.get("appid")}
    family_fields = (
        "family_owners", "family_owner", "family_country", "acquired", "family_hours",
    )
    for appid, old in previous_games.items():
        if not old.get("family") and not old.get("family_owners"):
            continue
        game = current.get(appid)
        if game is None:
            if old.get("family"):
                games.append(dict(old))
            continue
        for field in family_fields:
            if field in old:
                game[field] = old[field]
        # Preserve the freshly fetched owned-game hours and ownership classification.
        game["family"] = not bool(game.get("owned_accounts") or game.get("accounts"))
        if game["family"]:
            game["hours_source"] = old.get("hours_source", "family")
            game["family_hours"] = old.get("family_hours", game.get("family_hours", 0))
            game["total_hours"] = old.get("total_hours", game.get("total_hours", 0))
            game["last_played"] = old.get("last_played", game.get("last_played", 0))
            game["last_played_iso"] = old.get("last_played_iso", game.get("last_played_iso"))
            game["owned_count"] = old.get("owned_count", 0)
            game["owned_accounts"] = old.get("owned_accounts", [])


def has_family_snapshot(data):
    return bool(data and (
        data.get("family_members") or any(
            game.get("family") or game.get("family_owners") for game in data.get("games", [])
        )
    ))


def publish(data, out_dir):
    """Render all artifacts before writing; each file is replaced atomically."""
    data = without_secrets(data)
    data["games"].sort(key=lambda g: (-g["total_hours"], g["name"].lower()))
    data["total_unique_games"] = len(data["games"])
    data["total_hours"] = round(sum(g["total_hours"] for g in data["games"]), 1)
    files = {
        "steam_games.json": json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        "steam_games.md": render_md(data["accounts"], data["games"], data["source"], data["generated"]),
        "steam_games.html": render_html(data, (BASE / "web_template.html").read_text(encoding="utf-8")),
    }
    for name, content in files.items():
        atomic_write(Path(out_dir) / name, content)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=BASE / "accounts.json")
    parser.add_argument("--out-dir", type=Path, default=BASE)
    parser.add_argument("--history", type=Path, help="Ruta del historial local de primeras detecciones")
    parser.add_argument("--mode", choices=["auto", "api", "xml"], default="auto")
    parser.add_argument("--skip-family", action="store_true", help="Generar solo bibliotecas propias")
    parser.add_argument("--family-account", help="Alias de la cuenta cuyo token consultar; por defecto la primera con token")
    parser.add_argument("--skip-meta", action="store_true", help="Omitir precios y logros")
    parser.add_argument("--no-achievements", action="store_true")
    parser.add_argument("--genres", action="store_true", help="Incluir géneros y lanzamiento en JSON")
    parser.add_argument("--refresh", action="store_true", help="Ignorar la caché de tienda")
    parser.add_argument("--sleep-ms", type=int, default=250, help="Pausa entre consultas de Steam")
    parser.add_argument("--price-cache-days", type=int, default=7, help="Días que se reutiliza cada precio")
    parser.add_argument("--achievement-cache-days", type=int, default=7, help="Días que se reutilizan los logros; 0 los consulta siempre")
    args = parser.parse_args(argv)
    if args.sleep_ms < 0:
        parser.error("--sleep-ms debe ser positivo o cero")
    if args.price_cache_days < 0 or args.achievement_cache_days < 0:
        parser.error("los días de caché deben ser positivos o cero")
    try:
        config = load_config(args.config)
        previous = previous_snapshot(args.out_dir)
        # Try Steam Families when the configuration provides a token or member list.
        use_family = not args.skip_family and (args.family_account or config.get("family_members") or
                      any(a.get("access_token") for a in config["accounts"]))
        data = fetch_owned(config, args.mode)
        if use_family:
            print("[i] Consultando Steam Families...")
            try:
                apps, members = fetch_family(config, args.family_account)
            except SteamError as exc:
                retain_family_snapshot(data["games"], previous)
                data["family_members"] = previous.get("family_members", []) if previous else config.get("family_members", [])
                has_snapshot = has_family_snapshot(previous)
                data["family_sync_status"] = "stale" if has_snapshot else "unavailable"
                data["family_last_success"] = (
                    (previous or {}).get("family_last_success") or (previous or {}).get("generated")
                    if has_snapshot else None
                )
                data["family_sync_checked"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                if has_snapshot:
                    print(f"[!] Steam Families no se actualizó; se conserva la última copia disponible. Detalle: {exc}")
                else:
                    print(f"[!] Steam Families no se actualizó y aún no hay una copia anterior. Detalle: {exc}")
            else:
                data["family_members"] = members
                merge_family(data["games"], apps, {**config, "family_members": members})
                data["family_sync_status"] = "ok"
                data["family_last_success"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                data["family_sync_checked"] = data["family_last_success"]
        else:
            if args.skip_family:
                data["family_members"] = []
                print("[i] Se actualizarán solo juegos propios (--skip-family).")
            else:
                retain_family_snapshot(data["games"], previous)
                data["family_members"] = previous.get("family_members", []) if previous else []
                has_snapshot = has_family_snapshot(previous)
                data["family_sync_status"] = "stale" if has_snapshot else "unavailable"
                data["family_last_success"] = (
                    (previous or {}).get("family_last_success") or (previous or {}).get("generated")
                    if has_snapshot else None
                )
                data["family_sync_checked"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                if has_snapshot:
                    print("[!] No hay token configurado para Steam Families; se conserva la última copia disponible.")
                else:
                    print("[!] No hay token ni una copia previa de Steam Families; se publicarán solo cuentas propias.")
        history_path = args.history or args.out_dir / "steam_history.json"
        history = record_first_seen(
            load_history(history_path),
            (game["appid"] for game in data["games"]),
            data["generated"][:10],
        )
        for game in data["games"]:
            game["first_seen"] = history[str(game["appid"])]
        if not args.skip_meta:
            print("[i] Consultando precios y logros...")
            data["metadata_warnings"] = enrich_metadata(
                data["games"], config, args.out_dir / "meta_cache.json", sleep_ms=args.sleep_ms,
                refresh=args.refresh, no_achievements=args.no_achievements, genres=args.genres,
                price_cache_days=args.price_cache_days,
                achievement_cache_days=args.achievement_cache_days,
            )
        if refresh_sale_artwork(BASE / "steam_artwork.json"):
            print("[i] Arte de la campaña de Steam actualizado.")
        else:
            print("[i] Se conserva el último arte de Steam disponible.")
        data["schema_version"] = 2
        publish(data, args.out_dir)
        atomic_write(history_path, render_history(history))
    except SteamError as exc:
        print(f"[!] {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError, KeyError):
        print("[!] No se pudo completar la actualización. Revisa los archivos de configuración, los permisos y las respuestas de Steam.", file=sys.stderr)
        return 1
    print(f"[ok] {len(data['games'])} juegos -> JSON, Markdown y HTML en {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
