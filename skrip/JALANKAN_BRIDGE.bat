@echo off
title GPI - Bridge DOCSApp ke MySQL (jangan ditutup)
chcp 65001 >nul
cd /d "%~dp0..\bridge"
:ulang
echo.
echo [%date% %time%] Menjalankan bridge DOCSApp ke MySQL...
python docs_ke_mysql.py
echo.
echo [%date% %time%] Bridge berhenti (kode %errorlevel%). Dijalankan ulang dalam 15 detik.
echo Tekan Ctrl+C lalu Y untuk benar-benar berhenti. Detail ada di bridge\log
timeout /t 15 /nobreak >nul
goto ulang
