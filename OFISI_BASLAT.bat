@echo off
chcp 65001 >nul
cd /d "%~dp0"
title AI Proje Ofisi
"C:\Python314\python.exe" -B "%~dp0scripts\operations\start_office_local.py" %*
if errorlevel 1 (
    echo.
    echo [HATA] AI Proje Ofisi baslatilirken bir sorun olustu.
    pause
)
exit /b %errorlevel%
