@echo off
title GPI - Dashboard Monitoring DOCS (jangan ditutup)
chcp 65001 >nul
cd /d "%~dp0..\server"
:ulang
echo.
echo [%date% %time%] Menjalankan server dashboard...
python app.py
if "%errorlevel%"=="3" goto sudah_ada
echo.
echo [%date% %time%] Server berhenti (kode %errorlevel%). Dijalankan ulang dalam 15 detik.
echo Tekan Ctrl+C lalu Y untuk benar-benar berhenti. Detail ada di server\log\dashboard.log
timeout /t 15 /nobreak >nul
goto ulang

:sudah_ada
echo.
echo ============================================================================
echo  Server dashboard lain masih berjalan, jadi jendela ini tidak dijalankan.
echo  Untuk memakai versi terbaru: tutup jendela ini lalu klik RESTART_DASHBOARD.bat
echo ============================================================================
pause
