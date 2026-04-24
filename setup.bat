@echo off
setlocal enabledelayedexpansion

echo ============================================
echo   Job360 - Setup (Windows)
echo ============================================
echo.

REM Pick a Python launcher: prefer py -3, fall back to python
set "PYTHON_CMD="
where py >nul 2>&1 && set "PYTHON_CMD=py -3"
if "%PYTHON_CMD%"=="" (
    where python >nul 2>&1 && set "PYTHON_CMD=python"
)
if "%PYTHON_CMD%"=="" (
    echo ERROR: Python not found. Install Python 3.9+ from https://python.org
    exit /b 1
)

REM Check Python 3.9+
%PYTHON_CMD% -c "import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)" || (
    echo ERROR: Python 3.9+ required.
    %PYTHON_CMD% --version
    exit /b 1
)
for /f "tokens=*" %%v in ('%PYTHON_CMD% -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"') do set "PYVER=%%v"
echo [1/4] Python !PYVER! detected

REM Create virtual environment
if not exist "venv" (
    echo [2/4] Creating virtual environment...
    %PYTHON_CMD% -m venv venv || ( echo ERROR: venv creation failed. & exit /b 1 )
) else (
    echo [2/4] Virtual environment already exists
)

REM Activate + install deps (phase-1 moved deps to backend/pyproject.toml)
echo [3/4] Installing dependencies...
call "venv\Scripts\activate.bat" || ( echo ERROR: venv activation failed. & exit /b 1 )
python -m pip install --upgrade pip || ( echo ERROR: pip upgrade failed. & exit /b 1 )

if exist "requirements.txt" (
    pip install -r requirements.txt || ( echo ERROR: dependency install failed. & exit /b 1 )
) else if exist "backend\pyproject.toml" (
    pip install -e "backend" || ( echo ERROR: dependency install failed. & exit /b 1 )
) else (
    echo ERROR: No requirements.txt or backend\pyproject.toml found.
    exit /b 1
)

REM Data dirs (backend-local, matching phase-1 layout)
if not exist "backend\data\exports" md "backend\data\exports"
if not exist "backend\data\reports" md "backend\data\reports"
if not exist "backend\data\logs"    md "backend\data\logs"

REM .env from template
if not exist ".env.example" (
    echo WARNING: .env.example not found, skipping .env creation
) else if not exist ".env" (
    echo [4/4] Creating .env from template...
    copy ".env.example" ".env" >nul
    echo.
    echo   IMPORTANT: Edit .env with your API keys!
    echo   Required for full functionality:
    echo     - REED_API_KEY (https://www.reed.co.uk/developers/jobseeker)
    echo     - ADZUNA_APP_ID + ADZUNA_APP_KEY (https://developer.adzuna.com/)
    echo     - JSEARCH_API_KEY (https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch)
    echo     - SMTP_EMAIL + SMTP_PASSWORD (Gmail app password)
    echo     - NOTIFY_EMAIL (your email address)
    echo.
) else (
    echo [4/4] .env already exists
)

echo.
echo ============================================
echo   Setup complete!
echo ============================================
echo.
echo   Next steps:
echo     1. Edit .env with your API keys
echo     2. Activate venv: venv\Scripts\activate
echo     3. cd backend
echo     4. Run pipeline: python -m src.cli run
echo     5. Start API:    python -m src.cli api  (then run the Next.js frontend)
echo.

endlocal
exit /b 0
