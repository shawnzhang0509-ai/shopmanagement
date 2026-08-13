@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 家具模板编辑器 v18

echo.
echo ===== 家具模板编辑器 (furniture_sim) =====
echo 目录: %CD%
echo.
echo [工作流] grab_display.bat 抓数据 ^| 本程序看 Display 大库 / 编辑模板
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 找不到 python，请先安装 Python 3.12 或 3.14
    pause
    exit /b 1
)

if not exist "furniture_sim.py" (
    echo [错误] 缺少 furniture_sim.py
    pause
    exit /b 1
)

if not exist "ui_common.py" (
    echo [错误] 缺少 ui_common.py，请 git pull 更新项目
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

if not exist "data\display.xlsx" (
    echo [提示] 未找到 data\display.xlsx — 可先运行 grab_display.bat 抓取 Display 数据
    echo.
)

echo 正在启动 ...
python furniture_sim.py
if errorlevel 1 (
    echo.
    echo [启动失败] 请运行: python check_env.py
    pause
)
