<#
Resume the Varrenmoor swarm's local Claude sessions on Arcturus after a reboot.
Usage:  powershell -File swarm\resume-swarm.ps1 [-Only "3D pipeline","DND Swarm Coordinator"] [-DryRun]
Each session opens in its own terminal window, resumed by name in the repo folder with Remote Control on
so cross-session messaging works. Close a window to stop that session (idle sessions cost no plan usage,
only RAM). Edit $Sessions to add or retire members.

NOT handled here (start these by hand):
 - Desktop operator: a Claude Desktop app session (open the app, resume "Desktop operator setup"), keep Chrome signed in to chatgpt.com and gemini.google.com.
 - Foundry bridge: runs on Vega, not Arcturus. Vega's relay starts from its Startup shortcut.
 - Illustrator: open Illustrator, then Window > Extensions > Varrenmoor Bridge.
#>
param([string[]]$Only, [switch]$DryRun)
$repo = Split-Path $PSScriptRoot -Parent
$Sessions = @(
  'DND Swarm Coordinator',
  '3D pipeline',
  'Illustrator bridge'   # only exists once the user has started it; skipped if resume fails
)
if ($Only) { $Sessions = $Sessions | Where-Object { $Only -contains $_ } }
Set-Location $repo
git pull --rebase 2>&1 | Out-Host
foreach ($name in $Sessions) {
  $cmd = "Set-Location '$repo'; `$host.UI.RawUI.WindowTitle = '$name'; claude --resume '$name' --remote-control '$name'; Read-Host 'Session ended. Press Enter to close'"
  if ($DryRun) { Write-Host "[dry run] $name -> $cmd"; continue }
  Start-Process powershell -ArgumentList '-NoExit','-Command',$cmd
  Write-Host "Started: $name"
  Start-Sleep -Seconds 3
}
