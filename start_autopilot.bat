@echo off
title XAUUSD AutoPilot Launcher
echo ==========================================
echo   XAUUSD AutoPilot - Starting Services
echo ==========================================

:: Start the Python live server in background
echo [1/2] Starting Live Server on port 5000...
start /min "AutoPilot-Server" cmd /c "cd /d %~dp0 && python live_server.py"

:: Wait for server to boot
timeout /t 5 /nobreak >nul

:: Start ngrok tunnel
echo [2/2] Starting ngrok tunnel...
start /min "AutoPilot-Ngrok" cmd /c "ngrok http 5000 --log=stdout"

:: Wait and fetch the ngrok URL
timeout /t 5 /nobreak >nul
echo.
echo ==========================================
echo   Fetching your public URL...
echo ==========================================
powershell -Command "(Invoke-RestMethod http://localhost:4040/api/tunnels).tunnels[0].public_url"
echo.
echo ==========================================
echo   Open the URL above on your phone!
echo   Both windows are running minimized.
echo   Close this window - services keep running.
echo ==========================================
pause
