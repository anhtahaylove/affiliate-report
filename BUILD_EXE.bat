@echo off
setlocal
cd /d "%~dp0"

set "PYTHON=.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
  echo [ERROR] Chua co .venv. Hay chay START_REPORT.bat --check truoc.
  pause
  exit /b 1
)

echo [1/2] Cai PyInstaller 6.21.0...
"%PYTHON%" -m pip install --disable-pip-version-check "pyinstaller==6.21.0"
if errorlevel 1 goto :error

echo [2/2] Dong goi TikTokAffiliateReport.exe...
"%PYTHON%" -m PyInstaller --noconfirm --clean --onefile --windowed --name TikTokAffiliateReport --icon "packaging\app.ico" --add-data "streamlit_app.py;." --add-data ".streamlit;.streamlit" --add-data "tiktok_affiliate_report\migrations.py;tiktok_affiliate_report" --collect-all streamlit --collect-all altair --collect-all openpyxl --copy-metadata streamlit --hidden-import sqlalchemy.dialects.sqlite --hidden-import tiktok_affiliate_report.db --hidden-import tiktok_affiliate_report.migrations --hidden-import tiktok_affiliate_report.parser --hidden-import tiktok_affiliate_report.reports desktop_launcher.py
if errorlevel 1 goto :error

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "packaging\assert_no_embedded_database.ps1" -Path "dist\TikTokAffiliateReport.exe"
if errorlevel 1 goto :error

echo.
echo DONE: %CD%\dist\TikTokAffiliateReport.exe
exit /b 0

:error
echo.
echo [ERROR] Dong goi that bai.
pause
exit /b 1
