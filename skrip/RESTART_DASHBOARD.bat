@echo off
title GPI - Restart Dashboard
chcp 65001 >nul
echo Menutup semua server dashboard yang masih berjalan...
taskkill /FI "WINDOWTITLE eq GPI - Dashboard*" /T /F >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -match 'app\.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host ('  ditutup: python PID ' + $_.ProcessId) }"
echo Menunggu port dilepas...
timeout /t 3 /nobreak >nul
start "GPI Dashboard" "%~dp0JALANKAN_DASHBOARD.bat"
echo.
echo Dashboard dijalankan ulang di jendela baru. Di browser tekan Ctrl+F5.
timeout /t 6 >nul
