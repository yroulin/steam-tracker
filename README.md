# steam-tracker

Consolida la biblioteca de **varias cuentas de Steam** (y de tu **Steam Families**)
en un único dataset, más una web con filtros.

- `steam_games.json` → **fuente de verdad** estructurada (para tu agente).
- `steam_games.md` → resumen legible + tabla.
- `steam_games.html` → web autocontenida con filtros (se abre sin servidor).

## ⚠️ Seguridad (leer)

- `accounts.json` contiene tu **API key** y tu **access_token**. **NUNCA lo subas** a Git.
  Ya está en `.gitignore`, y `subir_a_github.ps1` aborta si detecta secretos.
- Los archivos publicados (`steam_games.json`, `.html`) **no** incluyen secretos: los
  scripts los sanitizan. Si algún día ves `access_token` o `api_key` ahí, algo salió mal.
- En GitHub, tus secretos van como **secreto** `STEAM_ACCOUNTS_JSON`, no en el código.

## Requisitos de privacidad de Steam

En cada cuenta, para que la API dé datos:

- **Perfil → Editar perfil → Privacidad → "Detalles de juego" = Público** (lista y horas).
- Para logros: **"Estado de los logros" = Público**. Si está privado, la API devuelve 403
  y ese juego simplemente queda sin logros (no falla).

## 1. Rellena `accounts.json`

```json
{
  "api_key": "TU_API_KEY",
  "accounts": [
    { "alias": "main", "steamid": "7656119..." },
    { "alias": "alt1", "steamid": "7656119...", "access_token": "eyA..." }
  ],
  "family_members": [
    { "alias": "L@u", "steamid": "7656119...", "country": "cr" }
  ]
}
```

- **SteamID64**: en el perfil, la URL es `steamcommunity.com/profiles/<ID>`.
- **`access_token`**: solo si quieres juegos de familia. Se saca logueado en Steam desde
  `https://store.steampowered.com/pointssummary/ajaxgetasyncconfig` (campo `webapi_token`).
  **Caduca**: si el script de familia deja de traer datos, genéralo de nuevo.
- **`family_members`**: opcional; solo para poner alias/país bonitos a los dueños.

## 2. API key (recomendada)

Una sola key sirve para **todas** las cuentas. Se pide en
<https://steamcommunity.com/dev/apikey> (la cuenta debe haber comprado algo alguna vez).

## 3. Ejecuta

```powershell
cd steam-tracker
.\fetch_steam.ps1     # biblioteca de tus cuentas -> json + md + web
.\fetch_family.ps1    # Steam Families: juegos compartidos, horas reales y fecha de compra
.\fetch_meta.ps1      # precios (USD), costo por hora y logros
```

Los tres regeneran la web automáticamente al terminar. `fetch_meta.ps1` y `fetch_genres.ps1`
usan **caché** (`meta_cache.json`, `genres_cache.json`) y pausas para respetar el rate limit
de Steam (si ves 429, sube `-SleepMs`).

`fetch_genres.ps1` queda **opcional**: la web actual no muestra géneros, pero los guarda en el JSON.

## 4. Publicar (GitHub Pages)

```powershell
.\subir_a_github.ps1
```

Luego, en GitHub: secreto `STEAM_ACCOUNTS_JSON` (contenido de `accounts.json`) y
Pages con Source "GitHub Actions". El workflow `.github/workflows/update.yml` corre a diario
y con cada push de código; publica en `https://TU_USUARIO.github.io/steam-tracker/`.

## Problemas típicos

| Síntoma | Causa |
|---|---|
| `perfil no publico ... pagina de login` | "Detalles de juego" en Privado/Amigos |
| Horas en 0 en una cuenta | Esa cuenta tiene el tiempo de juego privado |
| Logros en 0 / 403 | "Estado de los logros" privado |
| Familia sin datos | `access_token` caducado: genéralo de nuevo |
| 429 Too Many Requests | Sube `-SleepMs` en `fetch_meta`/`fetch_genres` |
