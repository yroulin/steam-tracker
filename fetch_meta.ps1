<#
.SYNOPSIS
  Enriquece steam_games.json con:
    - Precio actual en USD (appdetails) y costo por hora jugada.
    - Logros: conseguidos/total y % de completado, por cuenta propia.

.DESCRIPTION
  - Precio: store.steampowered.com/api/appdetails (sin key). Con cache y pausa
    para respetar el rate limit (429).
  - Logros: ISteamUserStats/GetPlayerAchievements (requiere API key). Solo para
    las cuentas de "accounts" (no miembros de familia). Respeta privacidad: si el
    perfil tiene logros privados, la API devuelve 403 y se omite sin fallar.
  - Guarda cache en meta_cache.json para no repetir consultas.

.EXAMPLE
  .\fetch_meta.ps1
  .\fetch_meta.ps1 -SleepMs 1200 -Refresh
#>
[CmdletBinding()]
param(
    [string]$Config = '',
    [string]$JsonPath = '',
    [string]$CachePath = '',
    [int]$SleepMs = 900,
    [string]$Lang = 'spanish',
    [string]$CC = 'us',
    [switch]$Refresh,
    [switch]$NoAchievements
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$UA = @{ 'User-Agent' = 'steam-tracker/1.0 (+local)' }

$ScriptDir = if ($PSScriptRoot) { $PSScriptRoot }
             elseif ($MyInvocation.MyCommand.Path) { Split-Path -Parent $MyInvocation.MyCommand.Path }
             else { (Get-Location).Path }
if (-not $Config)    { $Config    = Join-Path $ScriptDir 'accounts.json' }
if (-not $JsonPath)  { $JsonPath  = Join-Path $ScriptDir 'steam_games.json' }
if (-not $CachePath) { $CachePath = Join-Path $ScriptDir 'meta_cache.json' }

if (-not (Test-Path -LiteralPath $JsonPath)) { Write-Error "No existe $JsonPath."; exit 1 }
$cfg = Get-Content -LiteralPath $Config -Raw -Encoding UTF8 | ConvertFrom-Json
$apiKey = [string]$cfg.api_key
$data = Get-Content -LiteralPath $JsonPath -Raw -Encoding UTF8 | ConvertFrom-Json

# Cache
$cache = @{}
if ((Test-Path -LiteralPath $CachePath) -and -not $Refresh) {
    $raw = Get-Content -LiteralPath $CachePath -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($p in $raw.PSObject.Properties) {
        $v = $p.Value
        $price = -1
        if ($v.PSObject.Properties.Name -contains 'price' -and $null -ne $v.price) { $price = [int]$v.price }
        $free = $false
        if ($v.PSObject.Properties.Name -contains 'free' -and $null -ne $v.free) { $free = [bool]$v.free }
        $achTotal = 0
        if ($v.PSObject.Properties.Name -contains 'ach_total' -and $null -ne $v.ach_total) { $achTotal = [int]$v.ach_total }
        $cache[$p.Name] = [pscustomobject]@{ price = $price; free = $free; ach_total = $achTotal }
    }
}

function Get-AppPrice($appid) {
    $url = "https://store.steampowered.com/api/appdetails?appids=$appid&cc=$CC&l=$Lang"
    for ($a = 1; $a -le 3; $a++) {
        try {
            $resp = Invoke-RestMethod -Uri $url -Method Get -Headers $UA -TimeoutSec 20
            $e = $resp.$appid
            if ($e -and $e.success -and $e.data) {
                $free = [bool]$e.data.is_free
                $price = -1
                if ($e.data.price_overview) { $price = [int]$e.data.price_overview.final }
                return [pscustomobject]@{ price = $price; free = $free }
            }
            return [pscustomobject]@{ price = -1; free = $false }  # sin datos de tienda
        } catch {
            if ($_.Exception.Message -match '429') { Start-Sleep -Milliseconds (5000 * $a) } else { break }
        }
    }
    return $null  # fallo tras reintentos: no cachear
}

$games = @($data.games)
Write-Host "[i] Precios: consultando $($games.Count) juegos (CC=$CC)..."

$i = 0
foreach ($g in $games) {
    $i++
    $appid = [string]$g.appid
    if ($cache.ContainsKey($appid) -and -not $Refresh) { continue }
    $res = Get-AppPrice $appid
    if ($null -eq $res) { continue }
    # total de logros se llena despues; conservar si ya existe
    $achTotal = 0
    if ($cache.ContainsKey($appid)) { $achTotal = [int]$cache[$appid].ach_total }
    $cache[$appid] = [pscustomobject]@{ price = $res.price; free = $res.free; ach_total = $achTotal }
    if ($SleepMs -gt 0) { Start-Sleep -Milliseconds $SleepMs }
    if ($i % 50 -eq 0) { Write-Host "  ... $i / $($games.Count)" -ForegroundColor DarkGray }
}

Write-Host "[i] Precios listos. Cache: $($cache.Count) entradas."

# Logros por cuenta propia
$achievementsByAccount = @{}
if (-not $NoAchievements -and $apiKey) {
    $ownAccounts = @($cfg.accounts | Where-Object { -not ($_.PSObject.Properties.Name -contains 'skip_achievements') })
    foreach ($acc in $ownAccounts) {
        $alias = [string]$acc.alias
        $sid = [string]$acc.steamid
        Write-Host "[i] Logros de $alias ..."
        $map = @{}
        # Solo juegos que posee esa cuenta
        foreach ($g in $games) {
            if (-not ($g.accounts.PSObject.Properties.Name -contains $alias)) { continue }
            $appid = [string]$g.appid
            try {
                $r = Invoke-RestMethod "https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v0001/?appid=$appid&key=$apiKey&steamid=$sid&l=$Lang&format=json" -Headers $UA -TimeoutSec 20
                $ach = @($r.playerstats.achievements)
                if ($ach.Count -gt 0) {
                    $got = @($ach | Where-Object { $_.achieved -eq 1 }).Count
                    $map[$appid] = [pscustomobject]@{ got = $got; total = $ach.Count }
                }
            } catch {
                # 403 = logros privados; se omite. Otros errores: ignorar.
            }
            if ($SleepMs -gt 0) { Start-Sleep -Milliseconds 150 }
        }
        $achievementsByAccount[$alias] = $map
        Write-Host "    ${alias}: $($map.Count) juegos con logros"
    }
}

# Volcar cache
$cacheObj = @{}
foreach ($k in $cache.Keys) { $cacheObj[$k] = $cache[$k] }
$utf8 = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($CachePath, ($cacheObj | ConvertTo-Json -Depth 5), $utf8)

# Enriquecer juegos
foreach ($g in $games) {
    $appid = [string]$g.appid
    $c = $cache[$appid]
    $priceUsd = $null; $free = $false
    if ($c) {
        $free = [bool]$c.free
        if ([int]$c.price -ge 0) { $priceUsd = [math]::Round([int]$c.price / 100.0, 2) }
    }
    $g | Add-Member -NotePropertyName price_usd -NotePropertyValue $priceUsd -Force
    $g | Add-Member -NotePropertyName is_free   -NotePropertyValue $free -Force
    $cph = $null
    if ($priceUsd -gt 0 -and $g.total_hours -gt 0) { $cph = [math]::Round($priceUsd / [double]$g.total_hours, 2) }
    $g | Add-Member -NotePropertyName cost_per_hour -NotePropertyValue $cph -Force

    # Logros por cuenta -> achieved_by = { alias: {got,total} } y agregado
    $byAcc = @{}
    foreach ($alias in $achievementsByAccount.Keys) {
        $accMap = $achievementsByAccount[$alias]
        if ($null -eq $accMap) { continue }
        $hasIt = $false
        if ($accMap -is [System.Collections.IDictionary]) {
            $hasIt = $accMap.Contains($appid)
        } elseif ($accMap.PSObject.Properties.Name -contains 'Keys') {
            $hasIt = $accMap.Keys -contains $appid
        }
        if ($hasIt) { $byAcc[$alias] = $accMap[$appid] }
    }
    $g | Add-Member -NotePropertyName achieved_by -NotePropertyValue $byAcc -Force
    $gotMax = 0; $totMax = 0
    foreach ($v in $byAcc.Values) { $gotMax += [int]$v.got; $totMax += [int]$v.total }
    $g | Add-Member -NotePropertyName achievements_got   -NotePropertyValue $gotMax -Force
    $g | Add-Member -NotePropertyName achievements_total -NotePropertyValue $totMax -Force
    $pct = $null
    if ($totMax -gt 0) { $pct = [math]::Round(100.0 * $gotMax / $totMax, 0) }
    $g | Add-Member -NotePropertyName achievements_pct -NotePropertyValue $pct -Force
}

# Reescribir json conservando cabecera (SANITIZADO: sin token ni api key)
$safeAccounts = @()
foreach ($a in @($data.accounts)) {
    $safeAccounts += [pscustomobject]@{
        alias       = [string]$a.alias
        steamid     = [string]$a.steamid
        personaname = if ($a.PSObject.Properties.Name -contains 'personaname') { [string]$a.personaname } else { '' }
    }
}
$out = [pscustomobject]@{
    generated          = $data.generated
    source             = $data.source
    accounts           = $safeAccounts
    family_members     = $data.family_members
    total_unique_games = $data.total_unique_games
    total_hours        = $data.total_hours
    games              = $games
}
[System.IO.File]::WriteAllText($JsonPath, ($out | ConvertTo-Json -Depth 12), $utf8)

$withPrice = @($games | Where-Object { $_.price_usd -ne $null }).Count
$withAch   = @($games | Where-Object { $_.achievements_total -gt 0 }).Count
Write-Host "[ok] Precio: $withPrice juegos | Logros: $withAch juegos" -ForegroundColor Green

$web = Join-Path $ScriptDir 'build_web.ps1'
if (Test-Path -LiteralPath $web) { & $web }
exit 0
