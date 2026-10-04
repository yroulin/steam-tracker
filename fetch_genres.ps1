<#
.SYNOPSIS
  Enriquece steam_games.json con genero (y fecha de lanzamiento) de cada juego
  usando store.steampowered.com/api/appdetails. Sin API key.

.DESCRIPTION
  - Guarda cache en genres_cache.json para no repetir consultas.
  - Respeta el rate limit con una pausa configurable entre llamadas.
  - Si un appid no tiene datos (demos, betas, retirados), queda sin genero.

.EXAMPLE
  .\fetch_genres.ps1
  .\fetch_genres.ps1 -SleepMs 300 -Refresh
#>
[CmdletBinding()]
param(
    [string]$JsonPath = '',
    [string]$CachePath = '',
    [int]$SleepMs = 1000,
    [string]$Lang = 'spanish',
    [switch]$Refresh
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$UA = @{ 'User-Agent' = 'steam-tracker/1.0 (+local)' }

$ScriptDir = if ($PSScriptRoot) { $PSScriptRoot }
             elseif ($MyInvocation.MyCommand.Path) { Split-Path -Parent $MyInvocation.MyCommand.Path }
             else { (Get-Location).Path }
if (-not $JsonPath) { $JsonPath = Join-Path $ScriptDir 'steam_games.json' }
if (-not $CachePath) { $CachePath = Join-Path $ScriptDir 'genres_cache.json' }

if (-not (Test-Path -LiteralPath $JsonPath)) { Write-Error "No existe $JsonPath."; exit 1 }

$data = Get-Content -LiteralPath $JsonPath -Raw -Encoding UTF8 | ConvertFrom-Json

# Cargar cache
$cache = @{}
if ((Test-Path -LiteralPath $CachePath) -and -not $Refresh) {
    $raw = Get-Content -LiteralPath $CachePath -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($p in $raw.PSObject.Properties) {
        $cache[$p.Name] = [pscustomobject]@{
            genres   = @($p.Value.genres)
            released = [string]$p.Value.released
        }
    }
}

$games = @($data.games)
$i = 0
$fetched = 0
foreach ($g in $games) {
    $i++
    $id = [string]$g.appid
    if ($cache.ContainsKey($id) -and -not $Refresh) { continue }
    $url = "https://store.steampowered.com/api/appdetails?appids=$id&l=$Lang"
    $ok = $false
    for ($attempt = 1; $attempt -le 3 -and -not $ok; $attempt++) {
        try {
            $resp = Invoke-RestMethod -Uri $url -Method Get -Headers $UA -TimeoutSec 20
            $entry = $resp.$id
            if ($entry -and $entry.success -and $entry.data) {
                $genres = @($entry.data.genres | ForEach-Object { $_.description })
                $released = ''
                if ($entry.data.release_date) { $released = [string]$entry.data.release_date.date }
                $cache[$id] = [pscustomobject]@{ genres = $genres; released = $released }
            } else {
                # appid sin datos de tienda (demo/beta/retirado): cachear vacio para no repetir
                $cache[$id] = [pscustomobject]@{ genres = @(); released = '' }
            }
            $ok = $true
        } catch {
            $msg = $_.Exception.Message
            if ($msg -match '429') {
                $wait = 5000 * $attempt
                Write-Host "    - $id ($($g.name)): 429, esperando $($wait/1000)s..." -ForegroundColor DarkYellow
                Start-Sleep -Milliseconds $wait
            } else {
                Write-Host "    - $id ($($g.name)): ERROR $msg" -ForegroundColor Yellow
                break
            }
        }
    }
    if (-not $ok -and -not $cache.ContainsKey($id)) {
        Write-Host "    - $id ($($g.name)): sin datos tras reintentos" -ForegroundColor Yellow
    }
    $fetched++
    if ($SleepMs -gt 0) { Start-Sleep -Milliseconds $SleepMs }
    if ($i % 50 -eq 0) { Write-Host "  ... $i / $($games.Count)" -ForegroundColor DarkGray }
}

# Volcar cache
$cacheObj = @{}
foreach ($k in $cache.Keys) { $cacheObj[$k] = $cache[$k] }
$utf8 = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($CachePath, ($cacheObj | ConvertTo-Json -Depth 5), $utf8)

# Enriquecer datos y reescribir steam_games.json
foreach ($g in $games) {
    $id = [string]$g.appid
    $c = $cache[$id]
    if ($c) {
        $g | Add-Member -NotePropertyName genres -NotePropertyValue @($c.genres) -Force
        $g | Add-Member -NotePropertyName released -NotePropertyValue ([string]$c.released) -Force
    } else {
        $g | Add-Member -NotePropertyName genres -NotePropertyValue @() -Force
        $g | Add-Member -NotePropertyName released -NotePropertyValue '' -Force
    }
}

$outObj = [pscustomobject]@{
    generated          = $data.generated
    source             = $data.source
    accounts           = $data.accounts
    total_unique_games = $games.Count
    total_hours        = $data.total_hours
    games              = $games
}
[System.IO.File]::WriteAllText($JsonPath, ($outObj | ConvertTo-Json -Depth 10), $utf8)

$withGenre = @($games | Where-Object { $_.genres.Count -gt 0 }).Count
Write-Host "[ok] Generos: $withGenre / $($games.Count) juegos ($fetched consultados, resto desde cache)" -ForegroundColor Green

# Regenerar la web si esta disponible
$web = Join-Path $ScriptDir 'build_web.ps1'
if (Test-Path -LiteralPath $web) { & $web }
exit 0
