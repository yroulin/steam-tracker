# GitHub Actions y Pages

El workflow `.github/workflows/update.yml` ejecuta `python update.py` en Ubuntu.
No usa PowerShell ni depende de tu PC. Está programado a las 15:00 UTC,
9:00 de Costa Rica; también se ejecuta manualmente y al subir código a `main`.

## Configuración del repositorio

1. En Settings → Secrets and variables → Actions, guarda el contenido completo de
   `accounts.json` como `STEAM_ACCOUNTS_JSON`. Si ya existe, no necesitas reemplazarlo
   por esta migración. Un token de Steam caducado sí requiere actualizar el contenido.
2. En Settings → Pages, selecciona GitHub Actions como origen.
3. En Actions → Actualizar biblioteca Steam → Run workflow, inicia una ejecución.

El workflow instala Python, ejecuta las pruebas, restaura la caché de tienda y
crea un `accounts.json` temporal a partir del secreto. Luego actualiza las cuentas,
familia, precios y logros, y elimina el archivo de configuración incluso si falla.
Antes de actualizar, restaura `steam_games.json` y `steam_artwork.json` desde la rama
`steam-data`; después guarda ahí el nuevo snapshot. HTML, JSON y Markdown se copian
al artefacto de Pages. La caché no contiene claves ni tokens. La primera actualización
puede tardar varios minutos.

Los datos diarios se guardan en `steam-data`, separados del código en `main`; así
las ejecuciones programadas no compiten con tus pushes de código. Los cambios en esa
rama no disparan este workflow. Un fallo al obtener las bibliotecas propias impide
publicar una biblioteca incompleta; si falla Steam Families, se conserva su último
snapshot y se publican las bibliotecas propias actualizadas. Los precios o logros
inaccesibles generan un aviso; el resto de datos puede publicarse.

La web prevista para este repositorio es <https://yroulin.github.io/steam-tracker/>.
Los datos publicados están en `steam_games.json` y `steam_games.md` bajo esa misma
dirección. La copia versionada en `main` funciona como snapshot inicial/offline y
puede quedar desactualizada; el snapshot diario más reciente está en `steam-data`.
Esto describe la configuración; no confirma que el despliegue esté activo.

Los archivos publicados incluyen SteamID, alias, juegos y horas. `accounts.json`
nunca debe estar en el repositorio. Los secretos de Actions no son archivos
versionados: conserva una copia privada del original para configurar otra PC.

El workflow `tests.yml` verifica por separado Windows, macOS y Linux sin secretos,
incluidos los pull requests. La actualización también ejecuta las pruebas antes
de consultar Steam.
