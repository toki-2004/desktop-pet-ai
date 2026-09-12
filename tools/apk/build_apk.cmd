@echo off
rem One-click wrapper: reads the chat page URL from the clipboard, writes the apk here.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_apk.ps1" %*
echo.
pause
