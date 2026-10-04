#!/usr/bin/env python3
"""Actualiza cuentas, familia, metadatos y web con Python 3.10 o posterior."""

import argparse
import json
import sys
from pathlib import Path

from build_web import render_html
from fetch_steam import fetch_owned, render_md
from steam_common import SteamError, atomic_write, load_config, without_secrets
from steam_family import fetch_family, merge_family
from steam_meta import enrich_metadata
from steam_history import load_history, record_first_seen, render_history

BASE = Path(__file__).resolve().parent


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
    parser.add_argument("--sleep-ms", type=int, default=900, help="Pausa entre consultas de tienda")
    args = parser.parse_args(argv)
    if args.sleep_ms < 0:
        parser.error("--sleep-ms debe ser positivo o cero")
    try:
        config = load_config(args.config)
        # A configured family is required unless the caller explicitly opts out.
        use_family = not args.skip_family and (args.family_account or config.get("family_members") or
                      any(a.get("access_token") for a in config["accounts"]))
        if not args.skip_family and not use_family:
            previous = args.out_dir / "steam_games.json"
            if previous.exists():
                old = json.loads(previous.read_text(encoding="utf-8-sig"))
                if old.get("family_members") or any(g.get("family") for g in old.get("games", [])):
                    raise SteamError("La biblioteca anterior contiene familia, pero falta access_token. Recupéralo o usa --skip-family.")
        data = fetch_owned(config, args.mode)
        if use_family:
            print("[i] Consultando Steam Families...")
            apps, members = fetch_family(config, args.family_account)
            data["family_members"] = members
            merge_family(data["games"], apps, {**config, "family_members": members})
        else:
            data["family_members"] = []
            print("[i] Se actualizarán solo juegos propios.")
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
            )
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
