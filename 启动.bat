@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 坪效管理工具

echo.
echo ===== 坪效管理工具（统一入口）=====
echo 目录: %CD%
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python。请先安装 Python 3.11 或 3.12
    echo 下载: https://www.python.org/downloads/
    echo 安装时勾选 "Add Python to PATH"
    pause
    exit /b 1
)

python launcher.py
if errorlevel 1 (
    echo.
    echo 启动失败。首次使用请先运行 install.bat 安装依赖。
    pause
)
