# Create a Foundry 3D Canvas scene from a generated model, in one command.
#   .\make-scene.ps1 -Model "..\foundry-3d\out\Act 2 Road to Bridgehollow\Ossuary Exchange\ossuary_forge.glb" -Name "Brokka's Forge"
# Reads <model>.scene.json (size + LIGHTS, written by foundry-3d/blender/run.py), copies the Ossuary Market scene's 3D settings
# (skybox, padding table), makes the scene EMPTY first and then adds the model tile and lights one by one (Scene.create with embedded
# documents duplicated them). Tile x,y is its centre; rotation 0 = plan north is canvas up (verified). The scene is not activated.
param([Parameter(Mandatory)][string]$Model, [Parameter(Mandatory)][string]$Name, [string]$Playlist = '', [string]$PlaylistSound = '',
      [int]$Pad = 4, [double]$Rotation = 0, [switch]$DisableAnim)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$bridge = Join-Path $PSScriptRoot 'bridge.ps1'
function Clone($o) { $o | ConvertTo-Json -Depth 30 | ConvertFrom-Json }
function Call($op, $obj) { & $bridge $op -Args ($obj | ConvertTo-Json -Depth 40 -Compress) }

$meta = Get-Content -LiteralPath ([IO.Path]::ChangeExtension((Resolve-Path $Model).Path, '.scene.json')) -Raw | ConvertFrom-Json
$m = & $bridge get -Args '{"uuid":"Scene.q8ifAtUP2duXgbfY"}' | ConvertFrom-Json          # Ossuary Market: settings to copy
$tplTile = $m.tiles | ? { $_.flags.'levels-3d-preview'.model3d -match 'patio' } | Select -First 1
$tplLight = $m.lights[0]

$K = 100 / 1.524; $FT = 3.281
$sx, $sy, $sz = [double]$meta.size_m[0], [double]$meta.size_m[1], [double]$meta.size_m[2]
$W = [int]([math]::Ceiling(($sx / 1.524 + 2 * $Pad)) * 100); $H = [int]([math]::Ceiling(($sy / 1.524 + 2 * $Pad)) * 100)
$sceneX = [math]::Ceiling($W * 0.25 / 100) * 100; $sceneY = [math]::Ceiling($H * 0.25 / 100) * 100
$cx = $sceneX + $W / 2; $cy = $sceneY + $H / 2

$scene = [ordered]@{
  name = $Name; folder = $m.folder; width = $W; height = $H; padding = $m.padding; shiftX = 0; shiftY = 0
  grid = $m.grid; tokenVision = $m.tokenVision; fog = $m.fog; environment = $m.environment; levels = $m.levels
  initialLevel = $m.initialLevel; navigation = $false; flags = $m.flags
}
if ($Playlist) { $scene.playlist = $Playlist; if ($PlaylistSound) { $scene.playlistSound = $PlaylistSound } }
$uuid = (Call create @{ documentName = 'Scene'; data = $scene } | ConvertFrom-Json).uuid
"scene $Name = $uuid  (${W}x${H}, centre $cx,$cy)"

$rel = ($meta.folder -replace '\\', '/')
$t = Clone $tplTile; $t.PSObject.Properties.Remove('_id')
$t.width = [math]::Round($sx * $K); $t.height = [math]::Round($sy * $K); $t.x = $cx; $t.y = $cy; $t.rotation = $Rotation; $t.elevation = 0.0995
$f = $t.flags.'levels-3d-preview'
$f.model3d = "assets/varrenmoor-3d/$rel/$($meta.name).glb"; $f.depth = [math]::Round($sz * $K); $f.randomSeed = ($meta.name -replace '[^a-z0-9]', '').Substring(0, [math]::Min(7, ($meta.name -replace '[^a-z0-9]', '').Length))
$f.autoGround = $true; $f.collision = $true; $f.sight = $true
if ($DisableAnim) { $f.enableAnim = $false }
Call create @{ documentName = 'Tile'; parentUuid = $uuid; data = $t } | Out-Null
"tile: $($f.model3d)  $($t.width)x$($t.height) depth $($f.depth)"

foreach ($l in $meta.lights) {
  $d = Clone $tplLight; $d.PSObject.Properties.Remove('_id')
  $d.x = [math]::Round($cx + $l.x * $K); $d.y = [math]::Round($cy - $l.y * $K); $d.elevation = [math]::Round(([double]$l.z - 0.1) * $FT, 1)
  $d.config.dim = [double]$l.dim; $d.config.bright = [double]$l.bright; $d.config.color = [string]$l.color
  if ($l.anim) { $d.config.animation.type = [string]$l.anim; $d.config.animation.speed = 3; $d.config.animation.intensity = 3 }
  if ($l.emitter) { $d.flags.'levels-3d-preview' = [pscustomobject]@{ enableParticle = $true; ParticleType = 'torch'; ParticleIntensity = 0.8; ParticleScale = 0.5; ParticleEmitterSizeMultiplier = [double]$l.emitter } }
  Call create @{ documentName = 'AmbientLight'; parentUuid = $uuid; data = $d } | Out-Null
}
"lights: $(@($meta.lights).Count)"
$uuid
