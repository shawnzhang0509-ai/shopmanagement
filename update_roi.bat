@echo off
chcp 65001 >nul
cd /d "%~dp0"
title ROI 同步到家具模板

echo.
echo ===== ROI 同步（weekly_sales.xlsx / roi.xlsx -^> furniture_templates.json）=====
echo   先运行 grab_sales.bat 抓取周销量，或手动维护 roi.xlsx
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 找不到 python
    pause
    exit /b 1
)

python scripts\update_roi.py
if errorlevel 1 (
    pause
    exit /b 1
)

echo.
echo 完成。可运行 start.bat 打开布局编辑器查看 ROI 着色。
pause
