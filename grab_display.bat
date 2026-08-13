@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Display 数据自动抓取工具

echo.
echo ===== Display 数据自动抓取工具 (GUI) =====
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 找不到 python
    pause
    exit /b 1
)

python -c "import sqlalchemy" >nul 2>&1
if errorlevel 1 (
    echo [提示] 正在安装依赖 ...
    python -m pip install sqlalchemy pymssql openpyxl pandas
)

python grab_display_gui.py
if errorlevel 1 pause
