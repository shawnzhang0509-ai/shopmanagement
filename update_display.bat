@echo off
chcp 65001 >nul
cd /d "%~dp0"
REM 更新 Display 数据 = 运行抓取程序（等同 grab_display.bat）
call grab_display.bat
