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
  # FOLDER = "Act 2 Road to Bridgehollow/Ossuary Exchange" in the generator mirrors the 2026 Campaign layout.
  $folder = ''
  $m = Select-String -Path $g.FullName -Pattern '^FOLDER\s*=\s*"([^"]*)"' | Select-Object -First 1
  if ($m) { $folder = $m.Matches[0].Groups[1].Value -replace '/', '\' }
  $suffix = if ($Seed) { "_s$Seed" } else { '' }
  $base = "$($g.BaseName)$suffix"
  $outDir = if ($folder) { Join-Path "$root\out" $folder } else { "$root\out" }
  New-Item -ItemType Directory -Force $outDir | Out-Null
  $out = Join-Path $outDir "$base.glb"
  $blend = Join-Path $outDir "$base.blend"
  Write-Host "Building $base..."
  & $blender --background --factory-startup --python "$root\blender\run.py" -- $g.FullName $out $Seed $blend |
    Where-Object { $_ -match '\[foundry-3d\]|Error|Traceback|File "' } | ForEach-Object { Write-Host "  $_" }
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path $out)) { throw "Blender failed on $($g.Name)" }

  $dest = $cfg['FOUNDRY_ASSETS_DIR']
  if ($dest) {
    if (Test-Path $dest) {
      $target = if ($folder) { Join-Path $dest $folder } else { $dest }
      New-Item -ItemType Directory -Force $target | Out-Null
      Copy-Item $out, $blend $target -Force
      Write-Host "  copied .glb and .blend to $target"
    } else { Write-Warning "FOUNDRY_ASSETS_DIR '$dest' not reachable; model left in $outDir" }
  }
}
Write-Host 'Done. In Foundry: on a 3D Canvas scene, create a Tile and set its 3D model to assets/varrenmoor-3d/<folder>/<name>.glb'
