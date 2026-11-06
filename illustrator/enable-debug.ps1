# Enables unsigned CEP extensions for the current user (HKCU only). Review, then run manually.
foreach ($v in 'CSXS.11','CSXS.12') {
  $k = "HKCU:\Software\Adobe\$v"
  if (-not (Test-Path $k)) { New-Item -Path $k -Force | Out-Null }
  New-ItemProperty -Path $k -Name PlayerDebugMode -Value '1' -PropertyType String -Force | Out-Null
  Write-Host "Set $k PlayerDebugMode=1"
}
