@echo off
cd /d "%~dp0"
rem Turn off console QuickEdit/selection mode: a stray click in this window would otherwise freeze the relay
rem (console output blocks while text is selected) until Esc is pressed.
powershell -NoProfile -Command "Add-Type -Namespace W -Name K -MemberDefinition '[DllImport(\"kernel32.dll\")] public static extern System.IntPtr GetStdHandle(int h); [DllImport(\"kernel32.dll\")] public static extern bool GetConsoleMode(System.IntPtr h, out uint m); [DllImport(\"kernel32.dll\")] public static extern bool SetConsoleMode(System.IntPtr h, uint m);'; $h=[W.K]::GetStdHandle(-10); $m=0; [void][W.K]::GetConsoleMode($h,[ref]$m); [void][W.K]::SetConsoleMode($h, (($m -bor 0x80) -band (-bnot 0x40)))" >nul 2>&1
node start.mjs
pause
