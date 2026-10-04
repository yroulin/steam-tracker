# steam-tracker — guía para el agente

Este directorio contiene una biblioteca de Steam consolidada de **varias cuentas**
propias + los juegos compartidos por **Steam Families**.

## Archivos

- `steam_games.json` → **fuente de verdad**. Úsala para cualquier consulta exacta,
  conteos o filtros. No intentes inferir datos desde el markdown si el JSON está disponible.
- `steam_games.md` → resumen legible (frontmatter + tabla). Útil para mostrar al usuario.
- `steam_games.html` → web con filtros (para el usuario, no la leas entera).
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
      "accounts": { "L@u": 126.3 },   // horas por cuenta (clave = alias)
      "total_hours": 126.3,
      "owned_count": 1,
      "last_played": 1753037626,
      "last_played_iso": "2025-07-20",
      "img_icon_url": "b6e2...",

      // --- Steam Families ---
      "family": true,                  // true si es compartido (no propio)
      "family_owner": "L@u",           // de quién es
      "family_country": "cr",
      "acquired": "2025-03-16",        // FECHA DE COMPRA (unix convertido)

      // --- Precio / valor (fetch_meta.ps1) ---
      "price_usd": 59.99,              // precio actual en USD; null si gratis/sin datos
      "is_free": false,
      "cost_per_hour": 0.47,           // price_usd / total_hours; null si 0 horas o gratis

      // --- Logros (solo cuentas propias; fetch_meta.ps1) ---
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
- Los juegos de familia NO tienen horas propias completas: su `.accounts` puede tener
  solo al dueño. Para "cuántas horas jugué yo", mira juegos propios.
- El precio es **actual** (hoy), no lo que se pagó. `cost_per_hour` es una estimación.
- No modifiques `steam_games.json` a mano; se regenera con los scripts `fetch_*.ps1`.
