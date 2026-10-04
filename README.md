# steam-tracker

Biblioteca de Steam consolidada de varias cuentas propias y Steam Families.
Python 3.10 o posterior, sin paquetes externos. Funciona en Windows, macOS y Linux.
La web es un HTML estático que se puede abrir sin servidor.

## Configuración

Copia tu `accounts.json` de la otra PC a esta carpeta. El formato sigue siendo el
mismo; `accounts.example.json` sirve como referencia si necesitas reconstruirlo.
Incluye `api_key`, una lista `accounts` con `alias` y `steamid`, y un
`access_token` en la cuenta que pertenece a la familia. `family_members` permite
asignar alias y país a los propietarios compartidos.

`accounts.json` está excluido de Git. No lo publiques ni pegues sus valores en
issues, capturas o logs. La API key también puede venir de `STEAM_API_KEY`.
Los archivos públicos se generan con campos de cuenta seleccionados y sin tokens.
Los alias, SteamID, bibliotecas y horas sí son parte de los archivos públicos.

Para leer las bibliotecas, los detalles de juego y las horas deben ser públicos.
Los logros privados se omiten. Si un token de familia caduca, debes renovarlo
iniciando sesión en Steam y obteniendo el `webapi_token` de
<https://store.steampowered.com/pointssummary/ajaxgetasyncconfig>.

## Actualizar todo

En macOS o Linux, desde la carpeta del proyecto:

```sh
python3 update.py
```

En Windows:

```text
py -3 update.py
```

El comando consulta cuentas, agrega familia, obtiene precios USD y logros, y
regenera `steam_games.json`, `steam_games.md` y `steam_games.html` con los mismos
datos. También conserva localmente la primera fecha en que el tracker vio cada
juego en `steam_history.json`; este archivo no se publica. No requiere PowerShell.
La primera consulta de precios puede tardar varios minutos; la caché de tienda
dura 24 horas. Los logros se consultan en cada ejecución.

Opciones:

```sh
python3 update.py --skip-meta          # solo bibliotecas y familia
python3 update.py --skip-family        # solo juegos propios, elimina familia de esta salida
python3 update.py --no-achievements    # precios sin consultas de logros
python3 update.py --genres             # añade géneros y lanzamiento al JSON
python3 update.py --refresh            # vuelve a consultar los precios
python3 update.py --sleep-ms 250        # pausa entre consultas (por defecto)
python3 update.py --price-cache-days 7  # reutilizar precios durante 7 días
python3 update.py --achievement-cache-days 7  # reutilizar logros durante 7 días
python3 update.py --config /ruta/accounts.json --out-dir /ruta/salida
python3 update.py --history /ruta/steam_history.json
python3 update.py --family-account main
```

Por defecto se usa la primera cuenta con token para consultar una familia. Para
usar otra cuenta, indica `--family-account`. Las bibliotecas propias siempre se
consultan todas. Sin API key se intenta el XML público, que puede no estar
accesible y no incluye última vez jugado ni logros.

Si falla una biblioteca propia o una familia solicitada, el proceso sale con
error antes de publicar datos, conservando las salidas anteriores. Precios y
logros se reutilizan 7 días por defecto para reducir llamadas repetidas; usa
`--refresh` para actualizar precios o `--achievement-cache-days 0` para consultar
logros en cada ejecución. Un fallo de
precios o logros se informa y no impide actualizar la biblioteca. Si falla la tienda,
se conserva el precio en caché cuando existe; `price_updated` indica su antigüedad.
Los logros no disponibles se muestran sin datos, no como cero logros conseguidos.

Los tres archivos se preparan antes de escribir. Cada reemplazo es atómico; no hay
una transacción conjunta ante un fallo de disco entre reemplazos.

## Consultar y reconstruir la web

Abre `steam_games.html` en el navegador. Para regenerarla desde el JSON existente,
sin secretos ni consultas a Steam:

```sh
python3 build_web.py
```

El calendario visual de festivales temáticos y ofertas estacionales usa las fechas
de `steam_events.json`, tomadas de los anuncios de Steamworks enlazados en ese
archivo. Actualízalo cuando Valve publique nuevas fechas. Steam anuncia fechas, pero
no siempre la hora; en esos casos se usa como referencia las 10:00 del Pacífico,
y el sitio presenta la hora en la zona local del navegador. El contador solo sigue
las ofertas estacionales; la lista también muestra los festivales.
El encabezado usa el arte estacional actual de la tienda de Steam, con variantes
para escritorio y móvil. `update.py` refresca sus URLs una vez al día y conserva
el último fondo disponible si Steam no responde.

Esto conserva los datos y la fecha de la última consulta. No corrige datos antiguos:
la clasificación nueva de propios y compartidos requiere ejecutar `update.py`.
Las carátulas y banderas requieren internet, aunque los filtros funcionan sin conexión.

`fetch_steam.py` sigue disponible para consultar únicamente las cuentas propias.
También regenera las tres salidas, pero no agrega familia ni metadatos; normalmente
conviene usar `update.py`.

## Interpretación de los datos

- `accounts`: horas por cuenta informadas por la API de bibliotecas propias.
- `owned_accounts` y `owned_count`: tus cuentas que poseen el juego, independientes
  de si hay horas disponibles.
- `family`: verdadero solo cuando ninguna de tus cuentas posee el juego.
- `family_owners`: todos los dueños externos informados, usados por el filtro de miembro.
  `family_owner` conserva el primer dueño por compatibilidad.
- `family_hours`: horas de la respuesta de Steam Families, sin atribuirlas a un dueño.
- `total_hours`: suma de `accounts` cuando hay datos propios; en caso contrario,
  horas informadas por Families. `hours_source` distingue `accounts` y `family`.
  La suma global no representa necesariamente tus horas personales.
- `acquired`: fecha informada por Families en `rt_time_acquired`, en UTC. No es la
  fecha de incorporación al tracker ni un historial de compras por cuenta.
- `first_seen`: primera fecha UTC en que este tracker observó el juego. En la
  primera actualización que crea el historial, los juegos ya existentes reciben
  ese día; no es una fecha de compra ni se puede reconstruir retroactivamente.
  En GitHub Actions se conserva mediante caché y solo el campo `first_seen` de
  cada juego se publica con la biblioteca.
- `last_played_iso`: última actividad de tus cuentas, o la de Families cuando no
  hay desglose propio.
- `price_usd`: precio de tienda de EE. UU. al consultar, no importe pagado.
  `cost_per_hour` es una estimación. Gratis tiene precio cero; desconocido, `null`.
- `achieved_by`: logros por cuenta propia; los totales agregan las cuentas con datos.
  `skip_achievements: true` permite omitir una cuenta.

## GitHub Actions y pruebas

Consulta `DEPLOY.md` para las actualizaciones diarias y GitHub Pages.
El secreto existente `STEAM_ACCOUNTS_JSON` sigue funcionando sin cambiar de formato.

```sh
python3 -m unittest discover -s tests -v
```

Las pruebas usan respuestas simuladas y no necesitan credenciales ni internet.
GitHub Actions tiene una matriz para Windows, macOS y Linux con Python 3.10,
y una ejecución adicional en Python 3.14.
