@echo off
title RAGAI Studio — Web UI
cd /d "%~dp0"
call venv\Scripts\activate
echo.
echo ============================================================
echo  RAGAI Studio — Web UI v9.0
echo ============================================================
echo  Starting Flask server...
echo  Open your browser at: http://localhost:5000
echo  On your phone (same WiFi): check console for IP address
echo ============================================================
echo.
python web_ui.py
pause
