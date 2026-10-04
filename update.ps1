<#
.SYNOPSIS
  Ejecuta fetch_steam.ps1 (que a su vez regenera la web) y guarda el resultado
  en steam-tracker.log. Pensado para el Programador de tareas.
#>
$ErrorActionPreference = 'Continue'
$dir = if ($PSScriptRoot) { $PSScriptRoot }
       elseif ($MyInvocation.MyCommand.Path) { Split-Path -Parent $MyInvocation.MyCommand.Path }
       else { (Get-Location).Path }
$log = Join-Path $dir 'steam-tracker.log'
$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'

"===== $stamp inicio =====" | Out-File -FilePath $log -Append -Encoding UTF8
try {
    & (Join-Path $dir 'fetch_steam.ps1') *>&1 | Out-File -FilePath $log -Append -Encoding UTF8
    "----- $stamp OK -----" | Out-File -FilePath $log -Append -Encoding UTF8
} catch {
    "----- $stamp ERROR: $($_.Exception.Message) -----" | Out-File -FilePath $log -Append -Encoding UTF8
}
