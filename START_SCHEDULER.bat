@echo off
title RAGAI Scheduler
echo.
echo  ============================================
echo   RAGAI Scheduler - Automated Video Factory
echo  ============================================
echo.

if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found.
    pause & exit /b 1
)

if not exist "scheduler.py" (
    echo  [ERROR] scheduler.py not found.
    pause & exit /b 1
)

if not exist "topics_queue.json" (
    echo  [ERROR] topics_queue.json not found. Create it with one topic per line.
    pause & exit /b 1
)

if exist "ffmpeg-8.1-essentials_build\bin\ffmpeg.exe" (
    set PATH=%CD%\ffmpeg-8.1-essentials_build\bin;%PATH%
)

echo  Starting scheduler (Ctrl+C to stop)...
echo  Logs: logs\job_manager.log
echo.
python scheduler.py --interval 300 %*

if errorlevel 1 (
    echo.
    echo  [ERROR] Scheduler exited with error. Check logs\job_manager.log
    pause
)