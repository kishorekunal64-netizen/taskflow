@echo off
title RAGAI Editor V2
echo.
echo  ============================================
echo   RAGAI Editor V2 — Automated YouTube Studio
echo  ============================================
echo.

:: Check for virtual environment
if exist "venv\Scripts\activate.bat" (
    echo  Activating virtual environment...
    call venv\Scripts\activate.bat
) else (
    echo  [INFO] No venv found — using system Python
)

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found. Install Python 3.11+ and add to PATH.
    echo  Download: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Check editor.py exists
if not exist "editor.py" (
    echo  [ERROR] editor.py not found. Run from the RAGAI project folder.
    pause
    exit /b 1
)

:: Check FFmpeg
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    if exist "ffmpeg-8.1-essentials_build\bin\ffmpeg.exe" (
        echo  [INFO] Using local FFmpeg build
        set PATH=%CD%\ffmpeg-8.1-essentials_build\bin;%PATH%
    ) else (
        echo  [WARN] FFmpeg not found — export will be disabled
        echo  Install: https://ffmpeg.org/download.html
    )
)

echo  Starting RAGAI Editor V2...
echo.
python editor.py

if errorlevel 1 (
    echo.
    echo  [ERROR] Editor exited with an error. Check logs\ folder for details.
    pause
)
