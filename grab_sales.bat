@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 周销量数据抓取

echo.
echo ===== 周销量抓取（Branch + ProductFamily）=====
echo   与 grab_display.bat 独立，共用 grabber_config.json
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 找不到 python
    pause
    exit /b 1
)

python -c "import pandas, openpyxl, sqlalchemy, pymssql" >nul 2>&1
if errorlevel 1 (
    echo [提示] 正在安装依赖 ...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖安装失败，请先运行 install.bat 或 启动.bat
        pause
        exit /b 1
    )
)

python scripts\grab_sales.py
if errorlevel 1 pause
