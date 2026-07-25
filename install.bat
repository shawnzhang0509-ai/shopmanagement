@echo off
cd /d "%~dp0"
python -m pip install --upgrade pip
python -m pip uninstall pygame -y 2>nul
python -m pip install -r requirements.txt
python -c "import pygame; print('pygame-ce OK:', pygame.version.ver)"
echo.
echo 启动主程序: python layout.py
pause
