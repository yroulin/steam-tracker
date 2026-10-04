# Publicar en la nube (GitHub Actions + Pages)

Objetivo: que la biblioteca se actualice sola **cada día en los servidores de GitHub**,
sin depender de tu PC, y quede una web accesible desde cualquier dispositivo.

No necesitas instalar git ni nada: todo se hace desde el navegador.

## 1. Crea el repositorio

1. Entra a <https://github.com> e inicia sesión (crea cuenta si no tienes).
2. Botón **New repository**.
3. Nombre: `steam-tracker`. Visibilidad: **Public**. Crea el repo.

> ¿Public o privado? GitHub Pages gratis solo funciona en repos **públicos**.
> Si lo quieres privado, avísame y lo hacemos con Cloudflare Pages en su lugar.

## 2. Sube los archivos

En la página del repo: **Add file → Upload files**, y arrastra **todo** el contenido de
`C:\Users\yroul\Downloads\steam-tracker`, **excepto**:

- `accounts.json`  ← contiene tu API key, NO lo subas
- `steam-tracker.log`
- cualquier `*.csv`

Confirma que se subió la carpeta `.github/workflows/update.yml`.
(Si el navegador no sube la carpeta `.github`, créala a mano:
**Add file → Create new file**, escribe la ruta `.github/workflows/update.yml` y pega
el contenido de ese archivo.)

Luego **Commit changes**.

## 3. Guarda la configuración como secreto

1. En el repo: **Settings → Secrets and variables → Actions**.
2. **New repository secret**.
3. Name: `STEAM_ACCOUNTS_JSON`
4. Secret: abre `accounts.json` en el Bloc de notas, selecciona todo (Ctrl+A), copia
   (Ctrl+C) y pega aquí el contenido completo.
5. **Add secret**.

## 4. Activa GitHub Pages

**Settings → Pages → Build and deployment → Source: “GitHub Actions”.**

## 5. Ejecuta una vez

Pestaña **Actions → “Actualizar biblioteca Steam” → Run workflow**.
En 1–2 minutos verás la ejecución en verde y tus archivos actualizados.

## 6. Tu web ya está online

```
https://TU_USUARIO.github.io/steam-tracker/
```

Ábrela desde el celular o cualquier PC. Se refresca sola todos los días a las 15:00 UTC
(edítalo en `.github/workflows/update.yml`, campo `cron`).

También quedan disponibles para tu agente:

```
https://TU_USUARIO.github.io/steam-tracker/steam_games.json
https://TU_USUARIO.github.io/steam-tracker/steam_games.md
```

## Notas

- La API key vive **solo** como secreto en GitHub; no está en ningún archivo del repo.
- Si cambias cuentas, edita el secreto `STEAM_ACCOUNTS_JSON`.
- Si GitHub desactiva el horario por inactividad (60 días), vuelve a ejecutarlo a mano o
  haz cualquier cambio en el repo.

## Privacidad (importante)

Como el repo es **público**, cualquiera puede ver:

- Los **SteamID64** de tus cuentas y sus **alias**.
- Tu **biblioteca completa** y las **horas** por juego (en `steam_games.json`).

Lo que **NO** se expone: tu API key (está en el secreto). Si te incomoda que las horas
sean públicas, la alternativa es un repo privado con **Cloudflare Pages** o tu propio
servidor. Dímelo y lo cambiamos a esa ruta.

## Estructura de la web

La página tiene: carátula por juego, banderas de país por cuenta, filtro por cuenta,
buscar, orden por horas/nombre/última vez, "solo backlog", "en varias cuentas",
mínimo de horas y exportar CSV. Los géneros se dejaron fuera de la web a propósito
(pero siguen en el JSON por si los quieres).
