@echo off
cd /d "%~dp0"
"C:\Python314\python.exe" -B "%~dp0scripts\development\run.py" tasks --port 8766
exit /b %errorlevel%
