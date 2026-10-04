# steam-tracker — guía para el agente

Este directorio contiene una biblioteca de Steam consolidada de **varias cuentas**
propias + los juegos compartidos por **Steam Families**.

## Archivos

- `steam_games.json` → **fuente de verdad**. Úsala para cualquier consulta exacta,
  conteos o filtros. No intentes inferir datos desde el markdown si el JSON está disponible.
- `steam_games.md` → resumen legible (frontmatter + tabla). Útil para mostrar al usuario.
- `steam_games.html` → web con filtros (para el usuario, no la leas entera).
- `steam_events.json` → fechas de ofertas estacionales y festivales temáticos; fuente
  oficial enlazada dentro del archivo. Actualízalo cuando Steam anuncie fechas nuevas.
- `accounts.json` → configuración de cuentas, API key y access token. **NUNCA expongas
  `api_key` ni `access_token`.**
- `meta_cache.json`, `genres_cache.json` → cachés locales (no las edites a mano).

## Esquema de `steam_games.json`

```jsonc
{
  "generated": "2026-10-04T12:00:00Z",   // cuándo se generó
  "source": "api",
  "accounts": [{ "alias": "y.roulin.tk", "steamid": "7656...", "personaname": "..." }],
  "family_members": [{ "alias": "L@u", "steamid": "7656...", "country": "cr" }],
  "total_unique_games": 806,
  "total_hours": 7036.1,
  "games": [
    {
      "appid": "1245620",
      "name": "ELDEN RING",
      "accounts": {},                 // solo horas de cuentas propias
      "owned_accounts": [],          // cuentas propias que poseen el juego
      "hours_source": "family",
      "family_hours": 126.3,
      "total_hours": 126.3,
      "owned_count": 0,
      "last_played": 1753037626,
      "last_played_iso": "2025-07-20",
      "first_seen": "2026-10-04",   // primera detección local, no fecha de compra
      "img_icon_url": "b6e2...",

      // --- Steam Families ---
      "family": true,                  // ninguna cuenta propia posee el juego
      "family_owner": "L@u",           // de quién es
      "family_country": "cr",
      "acquired": "2025-03-16",        // adquisición informada por Families, UTC

      // --- Precio / valor (steam_meta.py) ---
      "price_usd": 59.99,              // precio actual en USD; null si gratis/sin datos
      "is_free": false,
      "cost_per_hour": 0.47,           // price_usd / total_hours; null si 0 horas o gratis

      // --- Logros (solo cuentas propias; steam_meta.py) ---
      "achieved_by": { "y.roulin.tk": { "got": 30, "total": 42 } },
      "achievements_got": 30,
      "achievements_total": 42,
      "achievements_pct": 71           // 0-100; null si no hay logros
    }
  ]
}
```

## Consultas de ejemplo

- **Backlog** (nunca jugados): `total_hours == 0`
- **Dinero parado** (pagados sin jugar): `price_usd > 0 && total_hours == 0`
- **Costo por hora**: ordenar por `cost_per_hour` asc (más barato por hora = mejor gastado)
- **Más jugados**: `total_hours` desc
- **Abandonados**: `last_played_iso` de hace más de 1 año con `total_hours` alto
- **Juegos de un miembro de familia**: `family_owner == "L@u"` (o gEo!, Pai170)
- **Solo familia**: `family == true`
- **Juegos en varias cuentas**: `owned_count > 1`
- **Con logros pendientes**: `achievements_total > 0 && achievements_got < achievements_total`
- **Completados 100%**: `achievements_total > 0 && achievements_got == achievements_total`
- **Logros de una cuenta**: leer `achieved_by.<alias>`
- **Compras por año**: agrupar por `acquired` (YYYY)

## Reglas

- Los datos son de Steam y pueden estar **desactualizados**: revisa `generated`.
- Si el usuario pregunta por "mi cuenta X", filtra `accounts.<alias>`.
- En datos `schema_version: 2`, `.accounts` contiene solo horas de cuentas propias.
  `family_hours` no se atribuye al dueño; `hours_source` indica qué horas se muestran.
  Los datos anteriores a la migración mezclan esos conceptos. No reinterpretarlos
  ni corregirlos a mano; esperar a la siguiente consulta real con `update.py`.
- El precio es **actual** (hoy), no lo que se pagó. `cost_per_hour` es una estimación.
- `first_seen` es la primera fecha UTC en que el tracker vio el juego. El historial
  fuente está en `steam_history.json` (local/cache de Actions); no inferir compras.
- No modifiques `steam_games.json` a mano; se regenera con los comando `python3 update.py`.

## Desarrollo

- Python 3.10+, solo biblioteca estándar. No reintroducir PowerShell.
- Flujo completo: `python3 update.py`; HTML offline: `python3 build_web.py`.
- Pruebas: `python3 -m unittest discover -s tests -v`, sin credenciales.
- No publicar datos si falla una biblioteca requerida; no imprimir excepciones HTTP
  crudas porque pueden contener URLs con credenciales.
