# Installs the panel into the CEP extensions folder. Does NOT touch the registry.
$ErrorActionPreference = 'Stop'
$src  = Join-Path $PSScriptRoot 'panel'
$jobs = Join-Path $PSScriptRoot 'jobs'
$dest = Join-Path $env:APPDATA 'Adobe\CEP\extensions\VarrenmoorBridge'
New-Item -ItemType Directory -Force (Split-Path $dest) | Out-Null
if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
try {
  New-Item -ItemType SymbolicLink -Path $dest -Target $src | Out-Null
  Write-Host "Symlinked $dest -> $src"
} catch {
  Copy-Item $src $dest -Recurse
  Write-Host "Symlink failed (needs admin or Developer Mode); copied instead. Re-run after editing panel/."
}
@{ jobsDir = $jobs } | ConvertTo-Json | Set-Content (Join-Path $dest 'config.json') -Encoding UTF8
Write-Host "Jobs folder: $jobs"
Write-Host "Next: run enable-debug.ps1 once (after you approve it), then restart Illustrator."
