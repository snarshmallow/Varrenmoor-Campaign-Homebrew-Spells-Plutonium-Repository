# Hosts the relay in a VISIBLE console window that cannot freeze. Started by bridgectl.mjs (never needed by hand).
#   powershell -File relay-window.ps1 -Node <node.exe> -Daemon <daemon.mjs> -EnvFile <.env> -State <dir> [-Title ..] [-Mode window|wt]
# Why this wrapper exists: in a plain cmd/conhost window, clicking in the window starts "QuickEdit" text selection, and the console then
# blocks the program's output (and the relay's work with it) until you press Esc/Enter. This script switches QuickEdit off for this window
# (clear ENABLE_QUICK_EDIT_MODE 0x40, set ENABLE_EXTENDED_FLAGS 0x80), gives it a clear title and a long scrollback, then runs the relay
# with --console so logs scroll live (and are also written to run/relay.log). Windows Terminal (wt.exe) has no such freeze at all; bridgectl
# prefers it when it is installed and uses this same script inside it.
param([Parameter(Mandatory)][string]$Node, [Parameter(Mandatory)][string]$Daemon, [Parameter(Mandatory)][string]$EnvFile, [Parameter(Mandatory)][string]$State,
      [string]$Title = 'Varrenmoor Bridge relay (close = stop relay)', [string]$Mode = 'window')
$ErrorActionPreference = 'Continue'
try { $Host.UI.RawUI.WindowTitle = $Title } catch { }
try {
  Add-Type -Namespace VB -Name K -MemberDefinition '[DllImport("kernel32.dll")] public static extern System.IntPtr GetStdHandle(int h); [DllImport("kernel32.dll")] public static extern bool GetConsoleMode(System.IntPtr h, out uint m); [DllImport("kernel32.dll")] public static extern bool SetConsoleMode(System.IntPtr h, uint m);'
  $h = [VB.K]::GetStdHandle(-10); $m = 0
  if ([VB.K]::GetConsoleMode($h, [ref]$m)) { [void][VB.K]::SetConsoleMode($h, (($m -bor 0x80) -band (-bnot 0x40))); [void][VB.K]::GetConsoleMode($h, [ref]$m); $qe = if ($m -band 0x40) { 'ON (!)' } else { 'off' } }
  else { $qe = 'n/a (not a console, e.g. Windows Terminal)' }
  Add-Content -Path (Join-Path $State 'relay.log') -Value ("$([DateTime]::UtcNow.ToString('o')) relay window: console QuickEdit $qe") -ErrorAction SilentlyContinue
} catch { }
try { $s = $Host.UI.RawUI.BufferSize; if ($s.Height -lt 5000) { $Host.UI.RawUI.BufferSize = New-Object System.Management.Automation.Host.Size($s.Width, 5000) } } catch { }
Write-Host "Varrenmoor Bridge relay window. QuickEdit is OFF: clicking here cannot pause the relay." -ForegroundColor Cyan
Write-Host "Log file: $State\relay.log      Close this window or press Ctrl+C to stop the relay." -ForegroundColor DarkGray
& $Node $Daemon --env $EnvFile --state $State --console --mode $Mode
$code = $LASTEXITCODE
$marker = Join-Path $State 'relay.stop'
if (Test-Path $marker) { Remove-Item $marker -Force -ErrorAction SilentlyContinue; exit 0 }   # stopped on purpose (Stop in the panel): just close
Write-Host ""
Write-Host "The relay exited (code $code). Read the lines above, then press any key to close this window." -ForegroundColor Yellow
try { [void][Console]::ReadKey($true) } catch { Start-Sleep -Seconds 30 }
