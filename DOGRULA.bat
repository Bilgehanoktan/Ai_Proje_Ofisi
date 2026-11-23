@echo off
cd /d "%~dp0"
"C:\Python314\python.exe" -B "%~dp0scripts\development\run.py" verify
exit /b %errorlevel%
