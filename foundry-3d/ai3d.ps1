# Image -> Foundry-ready textured GLB. Engines: sf3d (Stable Fast 3D, default) or hunyuan (Hunyuan3D-2mini shape + projected texture).
#   .\ai3d.ps1 -Image "ossuary clerk.png" -Name ossuary_clerk -Folder "Act 2 Road to Bridgehollow/Ossuary Exchange"
param([Parameter(Mandatory)][string]$Image, [Parameter(Mandatory)][string]$Name, [string]$Folder = '',
      [ValidateSet('sf3d','hunyuan')][string]$Engine = 'sf3d', [int]$Tris = 30000, [double]$Height = 1.8)
$ErrorActionPreference = 'Continue'  # native stderr (progress/download notices) must not abort; exit codes are checked
$root = $PSScriptRoot
$cfg = @{}
if (Test-Path "$root\.env") {
  foreach ($l in Get-Content "$root\.env") { if ($l -match '^\s*([A-Z_]+)\s*=\s*(.*?)\s*$') { $cfg[$Matches[1]] = $Matches[2] } }
}
$blender = $cfg['BLENDER_PATH']
if (-not $blender -or -not (Test-Path $blender)) { throw 'BLENDER_PATH not set or missing. Run .\setup.ps1 first.' }
$py = "$root\ai\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw 'AI venv missing. See AI-SETUP.md.' }
$Image = (Resolve-Path -LiteralPath $Image).ProviderPath

$rel = $Folder -replace '/', '\'
$outDir = if ($rel) { Join-Path "$root\out" $rel } else { "$root\out" }
New-Item -ItemType Directory -Force $outDir | Out-Null
$raw = Join-Path $env:TEMP "$Name.shape.glb"
$out = Join-Path $outDir "$Name.glb"; $blend = Join-Path $outDir "$Name.blend"

if ($Engine -eq 'sf3d') {
  # Stable Fast 3D: textured mesh in one pass (better texture; ~8 GB peak VRAM).
  Write-Host "Stable Fast 3D..."
  $sfOut = Join-Path $env:TEMP "$Name.sf3d"
  Remove-Item $sfOut -Recurse -Force -ErrorAction SilentlyContinue
  Push-Location "$root\ai\sf3d"; $env:PYTHONPATH = '.'
  & $py run.py $Image --output-dir $sfOut --texture-resolution 2048
  Pop-Location
  $raw = Join-Path $sfOut '0\mesh.glb'
  if (-not (Test-Path $raw)) { throw 'Stable Fast 3D failed' }
  $tex = '-'
} else {
  Write-Host "Shape stage (Hunyuan3D-2mini)..."
  & $py "$root\ai\shape.py" $Image $raw
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path $raw)) { throw 'Shape stage failed' }
  $tex = $Image
}
Write-Host "Clean-up in Blender..."
& $blender --background --factory-startup --python "$root\ai\cleanup.py" -- $raw $tex $out $blend $Tris $Height |
  Where-Object { $_ -match '\[foundry-3d\]|Error|Traceback|File "' } | ForEach-Object { Write-Host "  $_" }
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $out)) { throw 'Blender clean-up failed' }

$dest = $cfg['FOUNDRY_ASSETS_DIR']
if ($dest -and (Test-Path $dest)) {
  $target = if ($rel) { Join-Path $dest $rel } else { $dest }
  New-Item -ItemType Directory -Force $target | Out-Null
  Copy-Item $out, $blend $target -Force
  Write-Host "  copied .glb and .blend to $target"
} elseif ($dest) { Write-Warning "FOUNDRY_ASSETS_DIR '$dest' not reachable; model left in $outDir" }
Write-Host "Done: $out"
