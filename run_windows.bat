@echo off
REM SlipSurfaceIQ LE - Windows: creates/updates the virtual environment and starts the app.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo Creating virtual environment...
    py -3 -m venv .venv 2>nul || python -m venv .venv
    .venv\Scripts\python.exe -m pip install --upgrade pip
)
REM Reinstall packages if requirements.txt changed (new release)
fc /b requirements.txt .venv\requirements.stamp >nul 2>&1
if errorlevel 1 (
    echo Installing / updating required packages...
    .venv\Scripts\python.exe -m pip install -r requirements.txt && copy /y requirements.txt .venv\requirements.stamp >nul
)
.venv\Scripts\python.exe -c "import slipsurface, os; print('SlipSurfaceIQ LE', slipsurface.__version__, '-', os.path.dirname(slipsurface.__file__))"
.venv\Scripts\python.exe main.py %*
if errorlevel 1 pause
