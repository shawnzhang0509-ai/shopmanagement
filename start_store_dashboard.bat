@echo off
cd /d "%~dp0"
echo 正在启动多店对比...
python -c "from ui_common import load_font; print('load_font OK')" 2>&1
if errorlevel 1 (
  echo.
  echo [错误] ui_common 缺少 load_font，请 git pull 最新代码
  pause
  exit /b 1
)
python store_dashboard.py
if errorlevel 1 pause
