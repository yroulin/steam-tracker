# steam-tracker — guía para el agente

Este directorio contiene una biblioteca de Steam consolidada de **varias cuentas**.

## Archivos

- `steam_games.json` → **fuente de verdad**. Úsala para cualquier consulta exacta,
  conteos o filtros. No intentes inferir datos desde el markdown si el JSON está disponible.
- `steam_games.md` → resumen legible (frontmatter + tabla). Útil para mostrar al usuario.
- `accounts.json` → configuración de cuentas y API key. **No expongas la API key.**

## Esquema de `steam_games.json`

```jsonc
{
  "generated": "2026-10-03T12:00:00Z",   // cuándo se generó
  "source": "api",                        // "api" o "xml"
  "accounts": [{ "alias": "main", "steamid": "7656...", "personaname": "..." }],
  "total_unique_games": 342,
  "total_hours": 1234.5,
  "games": [
    {
      "appid": "1145360",
      "name": "Hades",
      "accounts": { "main": 42.3, "alt": 5.0 },  // horas por cuenta
      "total_hours": 47.3,                        // suma entre cuentas
      "owned_count": 2,                           // en cuántas cuentas está
      "last_played": 1750000000,                  // unix, 0 si nunca
      "last_played_iso": "2025-06-15"             // null si nunca
    }
  ]
}
```

## Consultas de ejemplo

- Juegos nunca jugados (backlog): `total_hours == 0`
- Juegos en más de una cuenta: `owned_count > 1`
- Más jugados: ordenar por `total_hours` desc
- Abandonados: `last_played_iso` anterior a hace un año y `total_hours` alto
- Buscar por nombre: comparar `name` (case-insensitive), puede haber ediciones repetidas

## Reglas

- Los datos son de Steam y pueden estar **desactualizados**: revisa `generated`.
- Si el usuario pregunta por "mi cuenta X", filtra `accounts.<alias>`.
- No modifiques `steam_games.json` a mano; se regenera con `fetch_steam.ps1`.
