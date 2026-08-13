@echo off
setlocal
cd /d "%~dp0"

set "PYTHON=.venv\Scripts\python.exe"
set "APP_STAGE=build\installer-app"
if not exist "%PYTHON%" (
  echo [ERROR] Chua co .venv. Hay chay START_REPORT.bat --check truoc.
  pause
  exit /b 1
)

where pnpm >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Khong tim thay pnpm de build giao dien web.
  pause
  exit /b 1
)

echo [1/4] Cai dependencies production va PyInstaller...
"%PYTHON%" -m pip install --disable-pip-version-check -r requirements-api.txt "pyinstaller==6.21.0"
if errorlevel 1 goto :error

echo [2/4] Build Next.js static web app...
call pnpm --dir web install --frozen-lockfile
if errorlevel 1 goto :error
call pnpm --dir web build
if errorlevel 1 goto :error
if not exist "web\out\index.html" goto :missing_web

echo [3/4] Dong goi AffiliateReport.exe...
if exist "dist\AffiliateReport.exe" del /q "dist\AffiliateReport.exe"
"%PYTHON%" -m PyInstaller --noconfirm --clean --onedir --windowed --name AffiliateReport --specpath build --distpath "%APP_STAGE%" --workpath build\pyinstaller-work --icon "%CD%\packaging\app.ico" --add-data "%CD%\packaging\app.ico;packaging" --add-data "%CD%\web\out;web" --add-data "%CD%\affiliate_report\migrations.py;affiliate_report" --collect-all openpyxl --collect-submodules uvicorn --copy-metadata uvicorn --hidden-import h11 --hidden-import python_multipart --hidden-import pystray._win32 --hidden-import sqlalchemy.dialects.sqlite --hidden-import sqlalchemy.dialects.postgresql.psycopg --hidden-import affiliate_report.auth --hidden-import affiliate_report.api --hidden-import affiliate_report.db --hidden-import affiliate_report.migrations --hidden-import segno --hidden-import affiliate_report.pairing --hidden-import affiliate_report.parser --hidden-import affiliate_report.reports --hidden-import affiliate_report.updater --hidden-import affiliate_report.version desktop_launcher.py
if errorlevel 1 goto :error

echo [4/4] Kiem tra khong nhung database nguoi dung...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "packaging\assert_no_embedded_database.ps1" -Path "%APP_STAGE%\AffiliateReport"
if errorlevel 1 goto :error

echo.
echo DONE: runtime staging da san sang cho installer.
exit /b 0

:missing_web
echo [ERROR] Next.js build khong tao web\out\index.html. Kiem tra next.config.ts output export.
goto :error

:error
echo.
echo [ERROR] Dong goi that bai.
pause
exit /b 1
