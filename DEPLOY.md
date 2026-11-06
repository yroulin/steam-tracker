# GitHub Actions y Pages

El workflow `.github/workflows/update.yml` ejecuta `python update.py` en Ubuntu.
No usa PowerShell ni depende de tu PC. Está programado a las 15:00 UTC,
9:00 de Costa Rica, y también se ejecuta manualmente. Ya no se dispara al subir
código: de eso se encarga `build.yml` sin consultar Steam.

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
las ejecuciones programadas no compiten con tus pushes de código. Los archivos
generados (`steam_games.json`, `steam_games.md`, `steam_games.html` y
`steam_artwork.json`) no se versionan en `main`: el snapshot vive solo en
`steam-data` y la web en Pages. Los cambios en esa rama no disparan los workflows.
Un fallo al obtener las bibliotecas propias impide
publicar una biblioteca incompleta; si falla Steam Families, se conserva su último
snapshot y se publican las bibliotecas propias actualizadas. Los precios o logros
inaccesibles generan un aviso; el resto de datos puede publicarse.

El workflow `build.yml` publica en Pages cada push a `main` y también se puede
ejecutar a mano. No usa secretos ni consulta Steam: restaura el snapshot de
`steam-data`, ejecuta `python update.py --republish` y despliega. Así un cambio de
plantilla, estilos o fechas de eventos llega al sitio sin esperar la actualización
diaria. Los tres workflows comparten el grupo de concurrencia `steam-tracker`, de
modo que nunca hay dos despliegues de Pages a la vez.

La web prevista para este repositorio es <https://yroulin.github.io/steam-tracker/>.
Los datos publicados están en `steam_games.json` y `steam_games.md` bajo esa misma
dirección. El snapshot diario más reciente está en `steam-data`.
Esto describe la configuración; no confirma que el despliegue esté activo.

Los archivos publicados incluyen SteamID, alias, juegos y horas. `accounts.json`
nunca debe estar en el repositorio. Los secretos de Actions no son archivos
versionados: conserva una copia privada del original para configurar otra PC.

El workflow `update-artwork.yml` corre cada hora de 17:20 a 20:20 UTC, justo después
de la hora en que Steam inicia sus ofertas. Solo consulta la portada de la tienda y
no necesita secretos. Regenera la web con el snapshot y, si el arte cambió, guarda
el manifiesto en `steam-data` y publica Pages; si no cambió, no despliega. Ejecutarlo
a mano (`workflow_dispatch`) siempre publica, aunque el manifiesto sea idéntico, para
forzar un redespliegue. Un fallo de las bibliotecas no lo bloquea.

El workflow `tests.yml` verifica por separado Windows, macOS y Linux sin secretos,
incluidos los pull requests. La actualización también ejecuta las pruebas antes
de consultar Steam.
