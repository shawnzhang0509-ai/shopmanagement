@echo off
cd /d "%~dp0.."
python tools\migrate_data_to_regions.py
pause
