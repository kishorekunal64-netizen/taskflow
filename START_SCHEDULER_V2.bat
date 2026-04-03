@echo off
title RAGAI Scheduler v2 — Overnight Queue
cd /d "%~dp0"
call venv\Scripts\activate
echo.
echo ============================================================
echo  RAGAI Scheduler v2 — Overnight Batch Queue
echo ============================================================
echo  Fetches trends every hour
echo  Generates videos until daily quota exhausted
echo  Sleeps until midnight IST, then resumes
echo  Press Ctrl+C to stop
echo ============================================================
echo.
python scheduler_v2.py
pause
