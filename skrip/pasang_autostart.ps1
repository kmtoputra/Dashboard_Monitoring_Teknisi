param([switch]$Hapus)
$ErrorActionPreference = "Stop"
$Akar = Split-Path -Parent $PSScriptRoot
$User = "$env:USERDOMAIN\$env:USERNAME"
$Folder = "\GPI\"
$Nama = @("Bridge DOCS ke MySQL", "Dashboard Monitoring DOCS", "Backup Database Monitoring")

if ($Hapus) {
  foreach ($n in $Nama) { Unregister-ScheduledTask -TaskName $n -TaskPath $Folder -Confirm:$false -ErrorAction SilentlyContinue }
  Write-Host "Task GPI dihapus."
  exit 0
}

function Daftar($nama, $exe, $argumen, $trigger, $batasJam, $ulang) {
  $aksi = New-ScheduledTaskAction -Execute $exe -Argument $argumen -WorkingDirectory $Akar
  $set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
           -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::FromHours($batasJam))
  if ($ulang) { $set.RestartCount = 999; $set.RestartInterval = "PT1M" }
  $pr = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Limited
  Register-ScheduledTask -TaskName $nama -TaskPath $Folder -Action $aksi -Trigger $trigger -Settings $set -Principal $pr -Force | Out-Null
  Write-Host ("  OK  " + $nama)
}

Write-Host "Memasang task untuk user $User ..."
$t1 = New-ScheduledTaskTrigger -AtLogOn -User $User
Daftar $Nama[0] "cmd.exe" "/c `"$Akar\skrip\JALANKAN_BRIDGE.bat`"" $t1 0 $true
$t2 = New-ScheduledTaskTrigger -AtLogOn -User $User
$t2.Delay = "PT30S"
Daftar $Nama[1] "cmd.exe" "/c `"$Akar\skrip\JALANKAN_DASHBOARD.bat`"" $t2 0 $true
$t3 = New-ScheduledTaskTrigger -Daily -At "01:30"
Daftar $Nama[2] "powershell.exe" "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Akar\skrip\backup_harian.ps1`"" $t3 3 $false

$port = 8080
$ini = Get-Content (Join-Path $Akar "server\pengaturan_dashboard.ini") -Raw
if ($ini -match '\[server\][^\[]*?\bport\s*=\s*(\d+)') { $port = [int]$Matches[1] }
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($admin) {
  Remove-NetFirewallRule -DisplayName "GPI Dashboard Monitoring" -ErrorAction SilentlyContinue
  New-NetFirewallRule -DisplayName "GPI Dashboard Monitoring" -Direction Inbound -Protocol TCP -LocalPort $port `
    -Action Allow -Profile Private,Domain | Out-Null
  Write-Host "  OK  Firewall: port $port dibuka untuk jaringan Private/Domain (tidak untuk Public)"
} else {
  Write-Host ""
  Write-Host "  Firewall belum dibuka (perlu Administrator). Supaya PC/TV lain bisa membuka dashboard,"
  Write-Host "  jalankan di PowerShell Administrator:"
  Write-Host "  New-NetFirewallRule -DisplayName 'GPI Dashboard Monitoring' -Direction Inbound -Protocol TCP -LocalPort $port -Action Allow -Profile Private,Domain"
}
Write-Host ""
Write-Host "Selesai. Task berjalan otomatis saat user ini login. Pastikan Windows auto-login, sleep = Never, dan PC memakai UPS."
