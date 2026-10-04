# Build one or all generators into Foundry-ready .glb files.
#   .\make.ps1                      # every generator in .\generators
#   .\make.ps1 ossuary_stall        # just one
#   .\make.ps1 ossuary_stall -Seed 3
# Settings come from .\.env (created by setup.ps1): BLENDER_PATH, FOUNDRY_ASSETS_DIR (optional).
param([string]$Name = '', [int]$Seed = 0)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

$cfg = @{}
if (Test-Path "$root\.env") {
  foreach ($l in Get-Content "$root\.env") { if ($l -match '^\s*([A-Z_]+)\s*=\s*(.*?)\s*$') { $cfg[$Matches[1]] = $Matches[2] } }
}
$blender = $cfg['BLENDER_PATH']
if (-not $blender -or -not (Test-Path $blender)) { throw 'BLENDER_PATH not set or missing. Run .\setup.ps1 first.' }

$gens = if ($Name) { @(Get-Item "$root\generators\$Name.py") } else { @(Get-ChildItem "$root\generators\*.py") }
New-Item -ItemType Directory -Force "$root\out" | Out-Null

foreach ($g in $gens) {
  $out = "$root\out\$($g.BaseName).glb"
  Write-Host "Building $($g.BaseName)..."
  & $blender --background --factory-startup --python "$root\blender\run.py" -- $g.FullName $out $Seed |
    Where-Object { $_ -match '\[foundry-3d\]|Error|Traceback|File "' } | ForEach-Object { Write-Host "  $_" }
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path $out)) { throw "Blender failed on $($g.Name)" }

  $dest = $cfg['FOUNDRY_ASSETS_DIR']
  if ($dest) {
    if (Test-Path $dest) { Copy-Item $out $dest -Force; Write-Host "  copied to $dest" }
    else { Write-Warning "FOUNDRY_ASSETS_DIR '$dest' not reachable; model left in .\out" }
  }
}
Write-Host 'Done. In Foundry: create a Tile on a 3D Canvas scene and set its 3D model to the .glb (assets/varrenmoor-3d/...).'
