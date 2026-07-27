@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 家具模板编辑器

echo.
echo ===== 家具模板编辑器 =====
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

python -c "import pygame" >nul 2>&1
if errorlevel 1 (
    echo [提示] 正在安装 pygame-ce ...
    python -m pip install pygame-ce
)

echo 正在启动 ...
python furniture_sim.py
echo.
if errorlevel 1 (
    echo [启动失败] 请运行: python check_env.py
    pause
)
