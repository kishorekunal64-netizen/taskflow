@echo off
setlocal

:: ─────────────────────────────────────────────────────────────────────────────
:: START_RAGAI.bat — Windows launcher for RAGAI Video Factory
:: Activates the Python virtual environment and launches the GUI.
:: ─────────────────────────────────────────────────────────────────────────────

set "SCRIPT_DIR=%~dp0"
set "VENV_ACTIVATE=%SCRIPT_DIR%venv\Scripts\activate.bat"
set "RAGAI_SCRIPT=%SCRIPT_DIR%ragai.py"

:: Check virtual environment exists
if not exist "%VENV_ACTIVATE%" (
    echo.
    echo  ERROR: Virtual environment not found.
    echo  Expected: %VENV_ACTIVATE%
    echo.
    echo  To create it, run:
    echo    python -m venv venv
    echo    venv\Scripts\activate
    echo    pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

:: Check ragai.py exists
if not exist "%RAGAI_SCRIPT%" (
    echo.
    echo  ERROR: ragai.py not found.
    echo  Expected: %RAGAI_SCRIPT%
    echo.
    echo  Make sure you are running this batch file from the RAGAI project folder.
    echo.
    pause
    exit /b 1
)

:: Activate venv and launch GUI
call "%VENV_ACTIVATE%"
echo  Installing/verifying dependencies...
python -m pip install pydub groq numpy edge-tts gTTS opencv-python python-dotenv requests Pillow --quiet
echo  Starting RAGAI Video Factory...
python "%RAGAI_SCRIPT%" --gui

if errorlevel 1 (
    echo.
    echo  RAGAI exited with an error. Check logs\ for details.
    pause
)

endlocal
