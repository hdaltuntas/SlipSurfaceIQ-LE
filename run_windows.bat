@echo off
REM SlipSurface LE - Windows: sanal ortami kurar (ilk seferde) ve programi baslatir.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo Sanal ortam olusturuluyor...
    py -3 -m venv .venv 2>nul || python -m venv .venv
    .venv\Scripts\python.exe -m pip install --upgrade pip
    .venv\Scripts\python.exe -m pip install -r requirements.txt
)
.venv\Scripts\python.exe main.py %*
if errorlevel 1 pause
