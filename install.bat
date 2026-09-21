@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo ===== 安装依赖 =====
python -m pip install --upgrade pip
python -m pip uninstall pygame -y 2>nul
python -m pip install -r requirements.txt
python -c "import pygame; print('pygame-ce OK:', pygame.version.ver)"
echo.
echo 安装完成。推荐启动方式:
echo   启动.bat                  统一入口（数据 / 测绘 / 布局）
echo   start.bat                 坪效布局编辑器 (layout.py)
echo   start_furniture_sim.bat   家具模板 / Display 大库
echo   grab_display.bat          抓取 Display 数据
echo   grab_sales.bat            抓取周销量（ROI 源数据）
echo   update_roi.bat            同步 ROI 到家具模板
pause
