<#
.SYNOPSIS
  Obtiene la biblioteca de Steam Families (juegos compartidos) y enriquece
  steam_games.json con: dueno, horas reales y FECHA DE COMPRA de cada juego.

.DESCRIPTION
  Los juegos de familia NO se pueden obtener con la API key. Requieren un
  ACCESS TOKEN de usuario (webapi_token). Ese token caduca, asi que si el script
  deja de traer datos, hay que renovarlo.

  Como obtener el token:
    1. Inicia sesion en https://store.steampowered.com en el navegador.
    2. Abre https://store.steampowered.com/pointssummary/ajaxgetasyncconfig
    3. Copia el valor de la clave "webapi_token" (sin comillas).
    4. Pegalo en accounts.json, en la cuenta que pertenece a la familia:
         { "alias": "e]g[e > yves - cr", "steamid": "...", "access_token": "eyA..." }

  El endpoint GetSharedLibraryApps devuelve, por juego:
    owner_steamids[]  -> de quien es
    rt_playtime       -> minutos jugados (real, incluso de cuentas privadas)
    rt_time_acquired  -> fecha de compra (unix)
    app_type          -> 1 = juego, >2 = software/herramienta

.EXAMPLE
  .\fetch_family.ps1
#>
[CmdletBinding()]
param(
    [string]$Config = '',
    [string]$JsonPath = '',
    [string]$Account = ''
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$UA = @{ 'User-Agent' = 'steam-tracker/1.0 (+local)' }

$ScriptDir = if ($PSScriptRoot) { $PSScriptRoot }
             elseif ($MyInvocation.MyCommand.Path) { Split-Path -Parent $MyInvocation.MyCommand.Path }
             else { (Get-Location).Path }
if (-not $Config)   { $Config   = Join-Path $ScriptDir 'accounts.json' }
if (-not $JsonPath) { $JsonPath = Join-Path $ScriptDir 'steam_games.json' }

if (-not (Test-Path -LiteralPath $JsonPath)) { Write-Error "No existe $JsonPath. Corre fetch_steam.ps1 primero."; exit 1 }
$cfg = Get-Content -LiteralPath $Config -Raw -Encoding UTF8 | ConvertFrom-Json

# Cuenta con access_token (la indicada, o la primera que lo tenga)
$acc = $null
foreach ($a in $cfg.accounts) {
    if ($Account -and $a.alias -ne $Account) { continue }
    if ($a.PSObject.Properties.Name -contains 'access_token' -and $a.access_token) { $acc = $a; break }
}
if (-not $acc) {
    Write-Host "[!] Ninguna cuenta tiene access_token en accounts.json." -ForegroundColor Yellow
    exit 3
}
$token = [string]$acc.access_token
Write-Host "[i] Token de: $($acc.alias)"

# Mapa steamid -> alias
$idToAlias = @{}
foreach ($a in $cfg.accounts) { $idToAlias[[string]$a.steamid] = $a.alias }

# 1) FamilyGroupID del usuario autenticado
$g = Invoke-RestMethod "https://api.steampowered.com/IFamilyGroupsService/GetFamilyGroupForUser/v1/?access_token=$token&format=json" -Headers $UA -TimeoutSec 30
$groupId = [string]$g.response.family_groupid
if (-not $groupId) { Write-Host "[!] La cuenta no esta en una familia o el token no sirve." -ForegroundColor Yellow; exit 2 }
Write-Host "[i] family_groupid = $groupId"

# 2) Biblioteca compartida
$lib = Invoke-RestMethod "https://api.steampowered.com/IFamilyGroupsService/GetSharedLibraryApps/v1/?access_token=$token&family_groupid=$groupId&include_own=true&include_excluded=false&include_free=true&format=json" -Headers $UA -TimeoutSec 60
$apps = @($lib.response.apps)
Write-Host "[i] Apps en la familia: $($apps.Count)"

function Unix-Date($ts) {
    if (-not $ts -or [int64]$ts -le 0) { return $null }
    return [DateTimeOffset]::FromUnixTimeSeconds([int64]$ts).UtcDateTime.ToString('yyyy-MM-dd')
}

$data = Get-Content -LiteralPath $JsonPath -Raw -Encoding UTF8 | ConvertFrom-Json
$byId = @{}
foreach ($game in $data.games) { $byId[[string]$game.appid] = $game }

$added = 0; $enriched = 0
foreach ($app in $apps) {
    # Solo juegos (app_type 0/1). >2 suele ser software.
    $at = 0; if ($app.PSObject.Properties.Name -contains 'app_type') { $at = [int]$app.app_type }
    if ($at -gt 2) { continue }

    $appid = [string]$app.appid
    if (-not $appid) { continue }
    $name = if ($app.name) { [string]$app.name } else { "App $appid" }

    # Dueno (el primero que no sea la propia cuenta token; si no, el primero)
    $owners = @($app.owner_steamids)
    $ownerId = $owners | Where-Object { $_ -and $_ -ne $acc.steamid } | Select-Object -First 1
    if (-not $ownerId) { $ownerId = $owners | Select-Object -First 1 }
    $ownerAlias = if ($idToAlias.ContainsKey([string]$ownerId)) { $idToAlias[[string]$ownerId] } else { [string]$ownerId }

    $hours = 0.0
    if ($app.PSObject.Properties.Name -contains 'rt_playtime') { $hours = [math]::Round(([double]$app.rt_playtime / 60.0), 1) }
    $acquired = Unix-Date $app.rt_time_acquired
    $lastPlayed = 0; if ($app.PSObject.Properties.Name -contains 'rt_last_played') { $lastPlayed = [int64]$app.rt_last_played }
    # rt_playtime de familia ya es el total real del juego; lo guardamos como horas del juego.
    $familyHours = $hours

    if ($byId.ContainsKey($appid)) {
        $game = $byId[$appid]
        $game | Add-Member -NotePropertyName family          -NotePropertyValue $true        -Force
        $game | Add-Member -NotePropertyName family_owner    -NotePropertyValue $ownerAlias   -Force
        $game | Add-Member -NotePropertyName acquired        -NotePropertyValue $acquired    -Force
        $game | Add-Member -NotePropertyName img_icon_hash   -NotePropertyValue ([string]$app.img_icon_hash) -Force
        # Si la cuenta propia no daba horas (privada), usamos las de familia.
        if ($game.total_hours -eq 0 -and $familyHours -gt 0) {
            $game.total_hours = $familyHours
            $game.accounts = @{ $ownerAlias = $familyHours }
            $game.owned_count = 1
        }
        if ($lastPlayed -gt 0 -and $game.last_played -lt $lastPlayed) {
            $game.last_played = $lastPlayed
            $game.last_played_iso = Unix-Date $lastPlayed
        }
        $enriched++
    } else {
        $new = [pscustomobject]@{
            appid           = $appid
            name            = $name
            accounts        = $(if ($familyHours -gt 0) { @{ $ownerAlias = $familyHours } } else { @{} })
            total_hours     = $familyHours
            owned_count     = $(if ($familyHours -gt 0) { 1 } else { 0 })
            last_played     = $lastPlayed
            last_played_iso = (Unix-Date $lastPlayed)
            img_icon_url    = ''
            img_icon_hash   = [string]$app.img_icon_hash
            family          = $true
            family_owner    = $ownerAlias
            acquired        = $acquired
        }
        $data.games = @($data.games) + $new
        $byId[$appid] = $new
        $added++
    }
}

$sorted = @($data.games | Sort-Object @{ Expression = 'total_hours'; Descending = $true }, name)
$out = [pscustomobject]@{
    generated          = $data.generated
    source             = $data.source
    accounts           = $data.accounts
    total_unique_games = $sorted.Count
    total_hours        = [math]::Round((@($sorted | Measure-Object -Property total_hours -Sum).Sum), 1)
    games              = $sorted
}
$utf8 = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($JsonPath, ($out | ConvertTo-Json -Depth 12), $utf8)

Write-Host "[ok] Familia: $enriched existentes enriquecidos, $added nuevos agregados" -ForegroundColor Green

$web = Join-Path $ScriptDir 'build_web.ps1'
if (Test-Path -LiteralPath $web) { & $web }
exit 0
