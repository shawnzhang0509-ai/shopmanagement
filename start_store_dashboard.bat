@echo off
cd /d "%~dp0"
python store_dashboard.py
if errorlevel 1 pause
