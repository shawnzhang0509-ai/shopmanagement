@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 坪效布局编辑器

echo.
echo ===== 坪效布局编辑器 启动 =====
echo 目录: %CD%
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 找不到 python，请先安装 Python 3.12 或 3.14
    pause
    exit /b 1
)

python -c "import pygame" >nul 2>&1
if errorlevel 1 (
    echo [提示] 未检测到 pygame，正在安装 pygame-ce ...
    python -m pip install --upgrade pip
    python -m pip uninstall pygame -y 2>nul
    python -m pip install pygame-ce
    if errorlevel 1 (
        echo [错误] pygame-ce 安装失败
        pause
        exit /b 1
    )
)

if not exist "furniture_templates.json" (
    echo [错误] 找不到 furniture_templates.json
    echo 请确认在项目目录下运行，当前目录: %CD%
    pause
    exit /b 1
)

echo 正在启动 layout.py ...
echo.
python layout.py
if errorlevel 1 (
    echo.
    echo [程序异常退出] 运行诊断: python check_env.py
    pause
)
