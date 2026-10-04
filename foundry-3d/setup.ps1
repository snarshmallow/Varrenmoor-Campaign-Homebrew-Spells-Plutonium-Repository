# One-time setup on the GPU PC: finds Blender, records settings in .\.env, builds a test model.
#   .\setup.ps1
#   .\setup.ps1 -FoundryAssetsDir '\\SERVER-PC\FoundryData\assets\varrenmoor-3d'
param([string]$FoundryAssetsDir = '')
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

$blender = Get-ChildItem 'C:\Program Files\Blender Foundation\*\blender.exe', "$env:ProgramFiles\Steam\steamapps\common\Blender\blender.exe", 'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe' -ErrorAction SilentlyContinue |
  Sort-Object { $_.Directory.Name } -Descending | Select-Object -First 1
if (-not $blender) { throw 'blender.exe not found. Install Blender 4.x, or add BLENDER_PATH=... to foundry-3d\.env by hand.' }
$ver = (& $blender.FullName --version | Select-Object -First 1)
Write-Host "Blender: $($blender.FullName)  ($ver)"

$lines = @("BLENDER_PATH=$($blender.FullName)")
if ($FoundryAssetsDir) { $lines += "FOUNDRY_ASSETS_DIR=$FoundryAssetsDir" }
Set-Content -Path "$root\.env" -Value $lines -Encoding utf8
Write-Host "Wrote $root\.env"

$gpu = (Get-CimInstance Win32_VideoController | Where-Object Name -match 'NVIDIA|RTX|GeForce' | Select-Object -First 1).Name
Write-Host "GPU: $gpu"

& "$root\make.ps1" ossuary_stall
