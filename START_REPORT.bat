@echo off
setlocal
cd /d "%~dp0"

set "PYTHON=.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo [1/3] Dang tao moi truong Python local...
    where py >nul 2>&1
    if not errorlevel 1 (
        py -3 -m venv .venv
    ) else (
        where python >nul 2>&1
        if errorlevel 1 goto :python_missing
        python -m venv .venv
    )
    if errorlevel 1 goto :failed
)

"%PYTHON%" -c "import authlib, fastapi, httpx, openpyxl, pandas, psycopg, python_multipart, sqlalchemy, uvicorn" >nul 2>&1
if errorlevel 1 (
    echo [2/3] Dang cai thu vien backend...
    "%PYTHON%" -m pip install -r requirements-api.txt
    if errorlevel 1 goto :failed
)

if not exist "web\out\index.html" (
    echo [3/3] Dang build giao dien web lan dau...
    where pnpm >nul 2>&1
    if errorlevel 1 goto :node_missing
    call pnpm --dir web install --frozen-lockfile
    if errorlevel 1 goto :failed
    call pnpm --dir web build
    if errorlevel 1 goto :failed
)

if /i "%~1"=="--check" (
    "%PYTHON%" -c "from pathlib import Path; from affiliate_report.db import get_engine, init_db; init_db(get_engine('sqlite:///:memory:')); assert Path('web/out/index.html').is_file(); print('Local web app check OK')"
    exit /b %errorlevel%
)

echo Dang mo Affiliate Report trong trinh duyet...
"%PYTHON%" desktop_launcher.py
exit /b %errorlevel%

:python_missing
echo Khong tim thay Python. Hay cai Python 3.11 tro len tu https://www.python.org/downloads/
pause
exit /b 1

:node_missing
echo Khong tim thay pnpm de build source web. Ban cai dat tu GitHub Release se khong can Node.js hoac pnpm.
pause
exit /b 1

:failed
echo Khong khoi dong duoc ung dung. Xem loi o tren de xu ly.
pause
exit /b 1
