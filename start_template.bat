@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 家具模板编辑器

echo.
echo ===== 家具模板编辑器 / Display 大库 =====
echo 目录: %CD%
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 找不到 python
    pause
    exit /b 1
)

if not exist "ui_common.py" (
    echo [错误] 缺少 ui_common.py，请 git pull 更新项目
    pause
    exit /b 1
)

if not exist "furniture_sim.py" (
    echo [错误] 缺少 furniture_sim.py
    pause
    exit /b 1
)

if not exist "display_lookup.py" (
    echo [错误] 缺少 display_lookup.py，请 git pull 更新项目
    pause
    exit /b 1
)

python -c "import pygame" >nul 2>&1
if errorlevel 1 (
    echo [提示] 正在安装 pygame-ce ...
    python -m pip install pygame-ce
)

python -c "import openpyxl" >nul 2>&1
if errorlevel 1 (
    echo [提示] 正在安装 openpyxl ...
    python -m pip install openpyxl pandas
)

if not exist "display.xlsx" (
    echo.
    echo [提示] 未找到 display.xlsx
    echo        请在 SSMS 执行 display.sql，导出 Excel 到本目录
    echo        或运行 update_display.bat 查看步骤
    echo.
)

echo 正在启动 Display 大库 ...
python furniture_sim.py
echo.
if errorlevel 1 (
    echo [启动失败] 请运行: python check_env.py
    pause
)
