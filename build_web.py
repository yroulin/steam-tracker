"""Genera el HTML sin consultar Steam: python3 build_web.py."""

import argparse
import json
from pathlib import Path

from steam_common import atomic_write, without_secrets

BASE = Path(__file__).resolve().parent


def render_html(data, template):
    if "/*__STEAM_DATA__*/" not in template:
        raise ValueError("La plantilla no contiene el marcador de datos.")
    compact = json.dumps(without_secrets(data), ensure_ascii=False, separators=(",", ":"))
    # Escape every '<', including mixed-case </script> and HTML comment openers.
    compact = compact.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    compact = compact.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return template.replace("/*__STEAM_DATA__*/", compact)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=BASE / "steam_games.json")
    parser.add_argument("--template", type=Path, default=BASE / "web_template.html")
    parser.add_argument("--out", type=Path, default=BASE / "steam_games.html")
    args = parser.parse_args(argv)
    data = json.loads(args.json.read_text(encoding="utf-8-sig"))
    atomic_write(args.out, render_html(data, args.template.read_text(encoding="utf-8")))
    print(f"[ok] Web generada: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
