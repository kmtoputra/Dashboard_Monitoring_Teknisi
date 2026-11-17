@echo off
start "GPI Bridge" "%~dp0JALANKAN_BRIDGE.bat"
timeout /t 3 /nobreak >nul
start "GPI Dashboard" "%~dp0JALANKAN_DASHBOARD.bat"
echo Bridge dan dashboard dijalankan. Buka http://localhost:8080 di browser.
timeout /t 5 >nul
