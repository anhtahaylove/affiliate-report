@echo off
setlocal
cd /d "%~dp0"

set "PYTHON=.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo [1/2] Dang tao moi truong Python local...
    where py >nul 2>&1
    if not errorlevel 1 (
        py -3 -m venv .venv
    ) else (
        where python >nul 2>&1
        if errorlevel 1 goto :python_missing
        python -m venv .venv
    )
    if errorlevel 1 goto :failed

    echo [2/2] Dang cai thu vien lan dau...
    "%PYTHON%" -m pip install -r requirements.txt
    if errorlevel 1 goto :failed
)

"%PYTHON%" -c "import streamlit, pandas, openpyxl, sqlalchemy" >nul 2>&1
if errorlevel 1 (
    echo Dang bo sung thu vien con thieu...
    "%PYTHON%" -m pip install -r requirements.txt
    if errorlevel 1 goto :failed
)

if /i "%~1"=="--check" (
    "%PYTHON%" -c "from tiktok_affiliate_report.db import get_engine, init_db; init_db(get_engine('sqlite:///:memory:')); print('Local check OK')"
    exit /b %errorlevel%
)

echo Dang mo TikTok Affiliate Report tai http://127.0.0.1:8501
"%PYTHON%" -m streamlit run streamlit_app.py --server.address 127.0.0.1 --server.port 8501 --server.headless false
exit /b %errorlevel%

:python_missing
echo Khong tim thay Python. Hay cai Python 3.11 tro len tu https://www.python.org/downloads/
pause
exit /b 1

:failed
echo Khong khoi dong duoc ung dung. Xem loi o tren de xu ly.
pause
exit /b 1
