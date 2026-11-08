# Call the Foundry bridge from a Claude Code session or a terminal, with no manual token setup.
#   .\bridge.ps1 ping
#   .\bridge.ps1 list -Args '{"collection":"Scene"}'
#   .\bridge.ps1 get  -Args '{"uuid":"Scene.abc123"}'
#   .\bridge.ps1 create -Args '{"documentName":"Scene","data":{...}}'
# Settings are found, in order: -Config <file>, env FOUNDRY_BRIDGE_URL + FOUNDRY_BRIDGE_TOKEN, env FOUNDRY_BRIDGE_CONFIG,
# then client.json that start.mjs / publish-client.mjs writes on the Foundry PC (<dataPath>\bridge\client.json), read
# over the network at \\<host>\C\FoundryVTT resources\bridge\client.json. <host> is env FOUNDRY_BRIDGE_HOST, else the host of FOUNDRY_ASSETS_DIR in
# foundry-3d\.env; no host is built in. env FOUNDRY_BRIDGE_SHARE overrides the whole share path ({host} is replaced). The Illustrator panel (Bridge > Advanced) shows which file is used.
param([Parameter(Mandatory)][string]$Op, [string]$Args = '{}', [string]$Config = '', [string]$ArgsFile = '')
$ErrorActionPreference = 'Stop'

function Find-Config {
  if ($Config) { return $Config }
  if ($env:FOUNDRY_BRIDGE_CONFIG) { return $env:FOUNDRY_BRIDGE_CONFIG }
  $local = Join-Path $PSScriptRoot 'client.json'     # written by start.mjs when the relay runs on this PC
  if (Test-Path $local) { return $local }
  $hostName = $env:FOUNDRY_BRIDGE_HOST
  $envFile = Join-Path $PSScriptRoot '..\foundry-3d\.env'
  if (-not $hostName -and (Test-Path $envFile)) {
    foreach ($l in Get-Content $envFile) { if ($l -match '^\s*FOUNDRY_ASSETS_DIR\s*=\s*\\\\([^\\]+)\\') { $hostName = $Matches[1] } }
  }
  $cands = @()
  if ($hostName) {
    $tmpl = if ($env:FOUNDRY_BRIDGE_SHARE) { $env:FOUNDRY_BRIDGE_SHARE } else { '\\{host}\C\FoundryVTT resources\bridge\client.json' }
    $cands += $tmpl.Replace('{host}', $hostName)
  }
  if ($env:LOCALAPPDATA) {
    $opt = Join-Path $env:LOCALAPPDATA 'FoundryVTT\Config\options.json'
    if (Test-Path $opt) { $cands += (Join-Path ((Get-Content $opt -Raw | ConvertFrom-Json).dataPath) 'bridge\client.json') }
  }
  foreach ($c in $cands) { if (Test-Path -LiteralPath $c) { return $c } }
  throw "No bridge settings found. Set FOUNDRY_BRIDGE_HOST (the relay PC) or FOUNDRY_BRIDGE_CONFIG (a client.json), or on the relay PC run: node foundry-bridge\publish-client.mjs (or restart start.bat). Looked for: $($cands -join '; ')"
}

if ($env:FOUNDRY_BRIDGE_URL -and $env:FOUNDRY_BRIDGE_TOKEN) {
  $url = $env:FOUNDRY_BRIDGE_URL; $token = $env:FOUNDRY_BRIDGE_TOKEN
} else {
  $cfg = Get-Content -LiteralPath (Find-Config) -Raw | ConvertFrom-Json
  $url = $cfg.url; $token = $cfg.token
}
if ($ArgsFile) { $Args = [IO.File]::ReadAllText($ArgsFile, [Text.Encoding]::UTF8) }   # large payloads: pass a JSON file instead of a command-line string
$body = '{"op":' + ($Op | ConvertTo-Json -Compress) + ',"args":' + $Args + '}'
# The module's socket can drop and reconnect (tab sleep, tunnel blip): retry 503s and timeouts a few times.
for ($try = 1; $try -le 5; $try++) {
  try {
    $r = Invoke-RestMethod -Method Post -Uri ($url.TrimEnd('/') + '/rpc') -Headers @{ Authorization = "Bearer $token" } `
          -ContentType 'application/json' -Body ([Text.Encoding]::UTF8.GetBytes($body)) -TimeoutSec 60
    $r.result | ConvertTo-Json -Depth 30
    break
  } catch {
    $msg = $_.ErrorDetails.Message; if (-not $msg) { $msg = $_.Exception.Message }
    if (-not $msg -or $msg -match '^The remote server returned an error') {   # Windows PowerShell 5.1 leaves ErrorDetails empty: read the response body ({"error": "..."}) ourselves
      try { $sr = New-Object IO.StreamReader($_.Exception.Response.GetResponseStream()); $body = $sr.ReadToEnd(); if ($body) { $msg = $body } } catch { }
    }
    $transient = $msg -match '503|not connected|timed out|timeout'
    if ($transient -and $try -lt 5) { Start-Sleep -Seconds 4; continue }
    Write-Error "bridge $Op failed: $msg"
    break
  }
}
