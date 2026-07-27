@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 家具模板编辑器
python -c "import pygame" >nul 2>&1 || python -m pip install pygame-ce
python furniture_sim.py
if errorlevel 1 pause
