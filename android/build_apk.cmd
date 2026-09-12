@echo off
rem Build the chat-page APK and drop it in the project root.
rem Needs JDK 17 (in PATH), D:\gradle-8.7 and D:\android-sdk.
set GRADLE_USER_HOME=D:\android-gradle-home
cd /d %~dp0
call D:\gradle-8.7\bin\gradle.bat assembleDebug --no-daemon
if errorlevel 1 exit /b 1
copy /y app\build\outputs\apk\debug\app-debug.apk ..\desktop-pet-chat.apk
echo.
echo APK: %~dp0..\desktop-pet-chat.apk
