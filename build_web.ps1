<#
.SYNOPSIS
  Genera steam_games.html (web autocontenida con filtros) a partir de
  steam_games.json + web_template.html. No necesita servidor ni internet.

.EXAMPLE
  .\build_web.ps1
#>
[CmdletBinding()]
param(
    [string]$JsonPath = '',
    [string]$TemplatePath = '',
    [string]$OutPath = ''
)

$ErrorActionPreference = 'Stop'
$ScriptDir = if ($PSScriptRoot) { $PSScriptRoot }
             elseif ($MyInvocation.MyCommand.Path) { Split-Path -Parent $MyInvocation.MyCommand.Path }
             else { (Get-Location).Path }
if (-not $JsonPath) { $JsonPath = Join-Path $ScriptDir 'steam_games.json' }
if (-not $TemplatePath) { $TemplatePath = Join-Path $ScriptDir 'web_template.html' }
if (-not $OutPath) { $OutPath = Join-Path $ScriptDir 'steam_games.html' }

if (-not (Test-Path -LiteralPath $JsonPath)) {
    Write-Error "No existe $JsonPath. Corre fetch_steam.ps1 primero."
    exit 1
}
if (-not (Test-Path -LiteralPath $TemplatePath)) {
    Write-Error "No existe $TemplatePath."
    exit 1
}

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

# Leer SIEMPRE como UTF-8 explicito para no perder acentos ni flechas.
$dataText = [System.IO.File]::ReadAllText($JsonPath, [System.Text.Encoding]::UTF8)
$data = $dataText | ConvertFrom-Json
$compact = ($data | ConvertTo-Json -Depth 10 -Compress)
# Seguridad: evitar que un "</script>" cierre el <script> de la pagina.
$compact = $compact.Replace('</', '<\/')

$tpl = [System.IO.File]::ReadAllText($TemplatePath, [System.Text.Encoding]::UTF8)
if ($tpl.IndexOf('/*__STEAM_DATA__*/') -lt 0) {
    Write-Error "El template no contiene el marcador /*__STEAM_DATA__*/."
    exit 1
}
$html = $tpl.Replace('/*__STEAM_DATA__*/', $compact)

[System.IO.File]::WriteAllText($OutPath, $html, $utf8NoBom)
Write-Host "[ok] Web generada -> $OutPath ($([math]::Round((Get-Item $OutPath).Length/1KB,1)) KB)" -ForegroundColor Green
exit 0
