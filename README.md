# steam-tracker

Consolida la biblioteca de **varias cuentas de Steam** en un solo archivo:

- `steam_games.md` → resumen + tabla, legible por humanos.
- `steam_games.json` → fuente de verdad estructurada, para que el agente consulte.

## Requisito único

En cada cuenta: **Perfil → Editar perfil → Privacidad → "Detalles de juego" = Público**.
Si está en *Privado* o *Solo amigos*, Steam no entrega la lista (la API/XML devuelven vacío).

## 1. Rellena `accounts.json`

```json
{
  "api_key": "",
  "accounts": [
    { "alias": "main", "steamid": "7656119XXXXXXXXXX" },
    { "alias": "alt1", "steamid": "7656119YYYYYYYYYY" },
    { "alias": "alt2", "steamid": "7656119ZZZZZZZZZZ" }
  ]
}
```

- **SteamID64**: ábrelo en el perfil → la URL es
  `steamcommunity.com/profiles/<AQUI_VA_EL_ID>`. También sirve el nombre de usuario,
  pero el ID es más seguro.
- Los `XXXX/YYYY/ZZZZ` son placeholders; el script los salta.

## 2. API key (opcional pero recomendada)

**Una sola key sirve para TODAS las cuentas.** La key es tuya como desarrollador,
no de la cuenta que consultas.

1. Entra a <https://steamcommunity.com/dev/apikey> con **cualquiera** de tus cuentas.
2. Copia la key en `accounts.json` (`api_key`) o pásala por parámetro.

> La cuenta que pide la key debe haber gastado al menos ~5 USD alguna vez.

## 3. Ejecuta

Windows PowerShell (sin instalar nada):

```powershell
cd steam-tracker
.\fetch_steam.ps1                 # usa API si hay key, si no XML público
.\fetch_steam.ps1 -Mode xml       # fuerza el modo sin key
.\fetch_steam.ps1 -Key "TU_KEY"   # key puntual
```

Si algún día instalas Python: `python fetch_steam.py` (mismos archivos de salida).

## 4. Automatizar (opcional)

Programador de tareas → tarea diaria que ejecute:

```
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\ruta\steam-tracker\fetch_steam.ps1"
```

Así el `.md`/`.json` siempre están frescos.

## Problemas típicos

| Síntoma | Causa |
|---|---|
| `perfil no publico ... pagina de login` | "Detalles de juego" en Privado/Amigos |
| `la API no devolvio juegos` | Perfil privado, SteamID mal, o cuenta sin juegos públicos |
| Solo aparece una cuenta | Las demás fallaron; revisa el log por alias |

## Alternativas si prefieres no programar

- **Playnite**: importa varias cuentas de Steam y otros launchers, unifica horas y exporta.
- **Obsidian + Dataview**: mete `steam_games.json` y consulta con tablas vivas.
- **MCP server**: si tu agente soporta MCP, exponer `steam_buscar` / `steam_backlog`
  da consultas en vivo en vez de un archivo estático.
