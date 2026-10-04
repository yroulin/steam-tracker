<#
.SYNOPSIS
  steam-tracker: consolida la biblioteca de varias cuentas de Steam en un solo
  steam_games.md (legible) y steam_games.json (fuente de verdad para el agente).

.DESCRIPTION
  Dos modos, sin instalar nada (PowerShell nativo):
    * API -> una sola Steam Web API key sirve para TODAS las cuentas.
    * XML -> lee el perfil publico sin key.

  Requisito: "Detalles de juego" del perfil en Publico. Si esta en
  Privado/Amigos, la fuente no devuelve juegos y el script lo avisa.

.EXAMPLE
  .\fetch_steam.ps1
  .\fetch_steam.ps1 -Mode xml
  .\fetch_steam.ps1 -Key TU_API_KEY
  $env:STEAM_API_KEY = "..."; .\fetch_steam.ps1
#>
[CmdletBinding()]
param(
    [string]$Config = '',
    [ValidateSet('auto', 'api', 'xml')][string]$Mode = 'auto',
    [string]$Key = '',
    [string]$OutDir = ''
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$UA = @{ 'User-Agent' = 'steam-tracker/1.0 (+local)' }

# $PSScriptRoot no siempre esta disponible al evaluar los parametros (PS 5.1).
$ScriptDir = if ($PSScriptRoot) { $PSScriptRoot }
             elseif ($MyInvocation.MyCommand.Path) { Split-Path -Parent $MyInvocation.MyCommand.Path }
             else { (Get-Location).Path }
if (-not $Config) { $Config = Join-Path $ScriptDir 'accounts.json' }
if (-not $OutDir) { $OutDir = $ScriptDir }

function Get-OwnedViaApi {
    param([string]$ApiKey, [string]$SteamId)
    $uri = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/" +
           "?key=$ApiKey&steamid=$SteamId&include_appinfo=1&include_played_free_games=1&format=json"
    $data = Invoke-RestMethod -Uri $uri -Method Get -Headers $UA -TimeoutSec 30
    if ($null -eq $data.response.games) {
        throw 'la API no devolvio juegos: biblioteca privada / solo amigos, perfil invalido o sin juegos publicos'
    }
    $map = @{}
    foreach ($g in @($data.response.games)) {
        $name = if ($g.name) { [string]$g.name } else { "App $($g.appid)" }
        $hours = [math]::Round(([double]$g.playtime_forever / 60.0), 1)
        $map["$($g.appid)"] = [pscustomobject]@{
            name         = $name
            hours        = $hours
            last_played  = [int64]($g.rtime_last_played)
            img_icon_url = [string]$g.img_icon_url
        }
    }
    return $map
}

function Get-OwnedViaXml {
    param([string]$SteamId)
    $uri = "https://steamcommunity.com/profiles/$SteamId/games?tab=all&xml=1"
    $resp = Invoke-WebRequest -Uri $uri -UseBasicParsing -Headers $UA -TimeoutSec 30
    if ($resp.Content -notmatch '<gamesList') {
        throw 'perfil no publico (Steam devolvio la pagina de login, no el XML). Pon "Detalles de juego" en Publico.'
    }
    [xml]$x = $resp.Content
    $map = @{}
    foreach ($g in @($x.gamesList.games.game)) {
        $appid = ([string]$g.appID).Trim()
        if ([string]::IsNullOrWhiteSpace($appid)) { continue }
        $raw = ([string]$g.hoursOnRecord) -replace ',', ''
        $h = 0.0
        [void][double]::TryParse($raw.Trim(), [ref]$h)
        $map[$appid] = [pscustomobject]@{
            name         = ([string]$g.name).Trim()
            hours        = [math]::Round($h, 1)
            last_played  = [int64]0
            img_icon_url = ''
        }
    }
    if ($map.Count -eq 0) {
        throw 'el perfil no expone juegos: biblioteca privada / solo amigos o XML inaccesible'
    }
    return $map
}

function Get-ProfileName {
    param([string]$ApiKey, [string]$SteamId)
    try {
        $uri = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/" +
               "?key=$ApiKey&steamids=$SteamId"
        $data = Invoke-RestMethod -Uri $uri -Method Get -Headers $UA -TimeoutSec 30
        if ($data.response.players.Count -gt 0) { return [string]$data.response.players[0].personaname }
    } catch { }
    return ''
}

function ConvertFrom-Unix {
    param([int64]$Ts)
    if ($Ts -le 0) { return $null }
    return [DateTimeOffset]::FromUnixTimeSeconds($Ts).UtcDateTime.ToString('yyyy-MM-dd')
}

function Escape-Pipe {
    param([string]$Text)
    return $Text.Replace('|', '\|')
}

# --- Cargar config ---------------------------------------------------------
if (-not (Test-Path -LiteralPath $Config)) {
    Write-Error "No existe $Config. Crea accounts.json primero."
    exit 1
}
$cfg = Get-Content -LiteralPath $Config -Raw -Encoding UTF8 | ConvertFrom-Json
$accounts = @($cfg.accounts)
if ($accounts.Count -eq 0) { Write-Error 'accounts.json no tiene cuentas.'; exit 1 }

$apiKey = if ($Key) { $Key } elseif ($env:STEAM_API_KEY) { $env:STEAM_API_KEY } else { [string]$cfg.api_key }
$effectiveMode = $Mode
if ($effectiveMode -eq 'auto') { $effectiveMode = if ($apiKey) { 'api' } else { 'xml' } }
if ($effectiveMode -eq 'api' -and [string]::IsNullOrWhiteSpace($apiKey)) {
    Write-Error 'Falta la API key (-Key, $env:STEAM_API_KEY o accounts.json).'
    exit 1
}

Write-Host "[i] Modo: $effectiveMode. Cuentas: $($accounts.Count)"
$libraries = @{}
foreach ($acc in $accounts) {
    $alias = [string]$acc.alias
    $steamid = [string]$acc.steamid
    if ($steamid -match 'X{4,}|Y{4,}|Z{4,}') {
        Write-Host "    - ${alias}: placeholder sin rellenar, se omite."
        continue
    }
    try {
        if ($effectiveMode -eq 'api') {
            $acc | Add-Member -NotePropertyName personaname -NotePropertyValue (Get-ProfileName $apiKey $steamid) -Force
            $lib = Get-OwnedViaApi -ApiKey $apiKey -SteamId $steamid
        } else {
            $lib = Get-OwnedViaXml -SteamId $steamid
        }
        $libraries[$alias] = $lib
        Write-Host "    - ${alias}: $($lib.Count) juegos"
    } catch {
        Write-Host "    - ${alias}: ERROR -> $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

if ($libraries.Count -eq 0) {
    Write-Error 'No se pudo leer ninguna cuenta. Revisa IDs, privacidad o conexion.'
    exit 2
}

# --- Fusionar por appid ----------------------------------------------------
$merged = @{}
foreach ($acc in $accounts) {
    $alias = [string]$acc.alias
    if (-not $libraries.ContainsKey($alias)) { continue }
    foreach ($appid in $libraries[$alias].Keys) {
        $info = $libraries[$alias][$appid]
        if (-not $merged.ContainsKey($appid)) {
            $merged[$appid] = [pscustomobject]@{
                appid        = $appid
                name         = $info.name
                accounts     = @{}
                last_played  = [int64]0
                img_icon_url = ''
            }
        }
        $merged[$appid].accounts[$alias] = $info.hours
        if ($info.name -and $merged[$appid].name -match '^App ') {
            $merged[$appid].name = $info.name
        }
        if ($info.img_icon_url) { $merged[$appid].img_icon_url = $info.img_icon_url }
        if ($info.last_played -gt $merged[$appid].last_played) {
            $merged[$appid].last_played = $info.last_played
        }
    }
}

$games = foreach ($g in $merged.Values) {
    [pscustomobject]@{
        appid           = $g.appid
        name            = $g.name
        accounts        = $g.accounts
        total_hours     = [math]::Round((@($g.accounts.Values) | Measure-Object -Sum).Sum, 1)
        owned_count     = $g.accounts.Count
        last_played     = $g.last_played
        last_played_iso = ConvertFrom-Unix $g.last_played
        img_icon_url    = $g.img_icon_url
    }
}
$games = @($games | Sort-Object @{ Expression = 'total_hours'; Descending = $true }, name)

# --- Render markdown -------------------------------------------------------
$generated = [DateTime]::UtcNow.ToString('yyyy-MM-dd HH:mm') + ' UTC'
$multi = @($games | Where-Object { $_.owned_count -gt 1 }).Count
$backlog = @($games | Where-Object { $_.total_hours -eq 0 }).Count
$totalHours = [math]::Round((@($games | Measure-Object -Property total_hours -Sum).Sum), 1)

$md = New-Object System.Text.StringBuilder
[void]$md.AppendLine('---')
[void]$md.AppendLine("generated: $generated")
[void]$md.AppendLine("source: $effectiveMode")
[void]$md.AppendLine('accounts:')
foreach ($a in $accounts) {
    [void]$md.AppendLine("  - alias: $($a.alias)")
    [void]$md.AppendLine("    steamid: `"$($a.steamid)`"")
    if ($a.PSObject.Properties.Name -contains 'personaname' -and $a.personaname) {
        [void]$md.AppendLine("    personaname: `"$($a.personaname)`"")
    }
}
[void]$md.AppendLine("total_unique_games: $($games.Count)")
[void]$md.AppendLine("total_hours: $totalHours")
[void]$md.AppendLine('---')
[void]$md.AppendLine('')
[void]$md.AppendLine('# Biblioteca Steam (consolidada)')
[void]$md.AppendLine('')
[void]$md.AppendLine('## Resumen')
[void]$md.AppendLine("- Juegos unicos: **$($games.Count)**")
[void]$md.AppendLine("- En mas de una cuenta: **$multi**")
[void]$md.AppendLine("- Nunca jugados (backlog): **$backlog**")
[void]$md.AppendLine("- Horas totales: **$totalHours**")
[void]$md.AppendLine('')
[void]$md.AppendLine('## Indice')
[void]$md.AppendLine('')
[void]$md.AppendLine('| Juego | AppID | Cuentas | Horas totales | Ult. vez |')
[void]$md.AppendLine('|---|---|---|---|---|')
foreach ($g in $games) {
    $cuentas = ($g.accounts.GetEnumerator() | ForEach-Object { "$($_.Key) ($($_.Value)h)" }) -join ', '
    $last = if ($g.last_played_iso) { $g.last_played_iso } else { '-' }
    [void]$md.AppendLine("| $(Escape-Pipe $g.name) | $($g.appid) | $cuentas | $($g.total_hours) | $last |")
}
[void]$md.AppendLine('')
[void]$md.AppendLine('> Fuente de verdad para consultas exactas: `steam_games.json`.')
[void]$md.AppendLine('')

if (-not (Test-Path -LiteralPath $OutDir)) { New-Item -ItemType Directory -Path $OutDir -Force | Out-Null }
$utf8 = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText((Join-Path $OutDir 'steam_games.md'), $md.ToString(), $utf8)

# Sanitizar cuentas: nunca exponer api_key ni access_token en el JSON publico.
$safeAccounts = @()
foreach ($a in $accounts) {
    $safeAccounts += [pscustomobject]@{
        alias       = [string]$a.alias
        steamid     = [string]$a.steamid
        personaname = if ($a.PSObject.Properties.Name -contains 'personaname') { [string]$a.personaname } else { '' }
    }
}

$jsonObj = [pscustomobject]@{
    generated          = [DateTime]::UtcNow.ToString('o')
    source             = $effectiveMode
    accounts           = $safeAccounts
    total_unique_games = $games.Count
    total_hours        = $totalHours
    games              = $games
}
[System.IO.File]::WriteAllText(
    (Join-Path $OutDir 'steam_games.json'),
    ($jsonObj | ConvertTo-Json -Depth 8),
    $utf8
)

Write-Host "[ok] $($games.Count) juegos unicos -> steam_games.md + steam_games.json" -ForegroundColor Green

# Regenerar la web (steam_games.html) si el constructor esta disponible.
$webBuilder = Join-Path $ScriptDir 'build_web.ps1'
if (Test-Path -LiteralPath $webBuilder) { & $webBuilder }

exit 0
