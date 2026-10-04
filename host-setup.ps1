# Host (Foundry) PC setup. Run from the repo root in an ADMIN PowerShell:
#   Set-ExecutionPolicy -Scope Process Bypass; .\host-setup.ps1
# It:
#   1. pushes this branch to GitHub (a GitHub sign-in window may open)
#   2. creates Foundry's Data\assets\varrenmoor-3d folder for generated models
#   3. shares ONLY that folder on your network as \\<this-pc>\varrenmoor-3d (for your user only)
#   4. starts the Foundry bridge automatically when you log in to Windows
param([switch]$SkipPush, [switch]$SkipShare, [switch]$SkipStartup)
$ErrorActionPreference = 'Stop'
$repo = $PSScriptRoot
$branch = 'claude/adoring-shannon-yjixst'
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

function Step($t) { Write-Host "`n== $t" -ForegroundColor Cyan }

# 1. Push ----------------------------------------------------------------------
if (-not $SkipPush) {
  Step 'Pushing to GitHub'
  git -C $repo push origin $branch
  if ($LASTEXITCODE -ne 0) { Write-Warning "Push failed. Sign in to GitHub when prompted, or run: git push origin $branch" }
}

# 2. Foundry asset folder -----------------------------------------------------
Step 'Foundry asset folder'
$opts = Get-Content "$env:LOCALAPPDATA\FoundryVTT\Config\options.json" -Raw | ConvertFrom-Json
$assets = Join-Path $opts.dataPath 'Data\assets\varrenmoor-3d'
New-Item -ItemType Directory -Force $assets | Out-Null
Write-Host "Models folder: $assets  (in Foundry: assets/varrenmoor-3d/)"
# Show the same files inside the campaign folder (a junction, so there is one copy, served by Foundry).
$campaignLink = Join-Path $opts.dataPath '2026 Campaign\Generated 3D'
if ((Test-Path (Split-Path $campaignLink)) -and -not (Test-Path $campaignLink)) {
  New-Item -ItemType Junction -Path $campaignLink -Target $assets | Out-Null
  Write-Host "Linked $campaignLink -> $assets"
}

# 3. Network share for the GPU PC ---------------------------------------------
if (-not $SkipShare) {
  Step 'Network share'
  if (-not $isAdmin) {
    Write-Warning 'Not running as Administrator, so the share was skipped. Re-run from an admin PowerShell, or use -SkipShare.'
  } else {
    $user = "$env:USERDOMAIN\$env:USERNAME"
    if (-not (Get-SmbShare -Name 'varrenmoor-3d' -ErrorAction SilentlyContinue)) {
      New-SmbShare -Name 'varrenmoor-3d' -Path $assets -ChangeAccess $user | Out-Null
    }
    # Allow file sharing on Private (home) networks only.
    Get-NetFirewallRule -DisplayGroup 'File and Printer Sharing' -ErrorAction SilentlyContinue |
      Where-Object { $_.Profile -match 'Private' } | Enable-NetFirewallRule
    $cat = (Get-NetConnectionProfile | Select-Object -First 1).NetworkCategory
    if ($cat -ne 'Private') { Write-Warning "This network is set to '$cat'. Set it to Private in Windows Settings > Network so the GPU PC can reach the share." }
    Write-Host "Shared as \\$env:COMPUTERNAME\varrenmoor-3d for $user"
  }
}

# 4. Start the bridge at login ------------------------------------------------
if (-not $SkipStartup) {
  Step 'Bridge autostart'
  $node = (Get-Command node -ErrorAction Stop).Source
  $lnk = Join-Path ([Environment]::GetFolderPath('Startup')) 'Varrenmoor Bridge.lnk'
  $sh = New-Object -ComObject WScript.Shell
  $s = $sh.CreateShortcut($lnk)
  $s.TargetPath = $node
  $s.Arguments = 'start.mjs'
  $s.WorkingDirectory = Join-Path $repo 'foundry-bridge'
  $s.WindowStyle = 7   # minimized
  $s.Save()
  Write-Host "Added $lnk (runs the bridge minimized at login)."
  if (-not (Get-CimInstance Win32_Process -Filter "Name='node.exe'" | Where-Object CommandLine -match 'start\.mjs')) {
    Start-Process $node -ArgumentList 'start.mjs' -WorkingDirectory (Join-Path $repo 'foundry-bridge') -WindowStyle Minimized
    Write-Host 'Bridge started.'
  } else { Write-Host 'Bridge already running.' }
}

Step 'Next, on the GPU PC (PowerShell)'
Write-Host @"
  git clone https://github.com/snarshmallow/Varrenmoor-Campaign-Homebrew-Spells-Plutonium-Repository.git
  cd Varrenmoor-Campaign-Homebrew-Spells-Plutonium-Repository
  git checkout $branch
  cd foundry-3d
  Set-ExecutionPolicy -Scope Process Bypass
  .\setup.ps1 -FoundryAssetsDir '\\$env:COMPUTERNAME\varrenmoor-3d'
  (Windows may ask for this PC's username/password the first time it opens the share.)
"@
