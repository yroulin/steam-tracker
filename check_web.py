"""Comprueba que los bloques <script> de la web sean JavaScript válido.

No agrega dependencias de Python: extrae los bloques y delega en `node --check`.
Si Node no está instalado, avisa y termina con éxito para no romper el desarrollo
local; en GitHub Actions siempre está disponible y el paso sí bloquea el despliegue.
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
DEFAULT = BASE / "steam_games.html"
DATA_MARKER = "/*__STEAM_DATA__*/"
EVENTS_MARKER = "/*__STEAM_EVENTS__*/"

_SCRIPT = re.compile(r"<script\b[^>]*>(.*?)</script>", re.IGNORECASE | re.DOTALL)


def extract_scripts(html):
    """Return every inline script body, with the template placeholders neutralized."""
    scripts = []
    for body in _SCRIPT.findall(html):
        body = body.replace(DATA_MARKER, "{}").replace(EVENTS_MARKER, "{}")
        if body.strip():
            scripts.append(body)
    return scripts


def check(html, *, node=None):
    """Validate every script block; returns 0 on success, 1 on a syntax error."""
    scripts = extract_scripts(html)
    if not scripts:
        print("[!] No se encontraron bloques <script> para comprobar.", file=sys.stderr)
        return 1
    node = node or shutil.which("node")
    if not node:
        print("[!] Node no está disponible; se omite la comprobación de JavaScript.")
        return 0
    for index, script in enumerate(scripts, 1):
        handle = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8")
        try:
            handle.write(script)
            handle.close()
            result = subprocess.run([node, "--check", handle.name], capture_output=True, text=True)
        finally:
            handle.close()
            Path(handle.name).unlink(missing_ok=True)
        if result.returncode:
            print(f"[!] Error de sintaxis en el bloque <script> #{index}:", file=sys.stderr)
            print(result.stderr.strip(), file=sys.stderr)
            return 1
    print(f"[ok] {len(scripts)} bloques <script> con sintaxis válida.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, default=DEFAULT,
                        help="HTML a comprobar (por defecto steam_games.html)")
    args = parser.parse_args(argv)
    try:
        html = args.path.read_text(encoding="utf-8")
    except OSError:
        print(f"[!] No se pudo leer {args.path}.", file=sys.stderr)
        return 1
    return check(html)


if __name__ == "__main__":
    raise SystemExit(main())
