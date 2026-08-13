@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Display 数据抓取

echo.
echo ===== Display 数据抓取 (Main) =====
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 找不到 python
    pause
    exit /b 1
)

if not exist "grabber_config.json" (
    echo [提示] 未找到 grabber_config.json
    echo        请复制 grabber_config.example.json 并填入数据库密码
    echo.
    if exist "grabber_config.example.json" (
        echo 示例文件: grabber_config.example.json
    )
    pause
    exit /b 1
)

python -c "import sqlalchemy" >nul 2>&1
if errorlevel 1 (
    echo [提示] 正在安装 sqlalchemy pymssql ...
    python -m pip install sqlalchemy pymssql openpyxl pandas
)

python scripts\grab_display.py
echo.
pause
