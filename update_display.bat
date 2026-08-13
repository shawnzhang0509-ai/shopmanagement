@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 更新 Display 库

echo.
echo ========================================
echo   更新 Display 库 (display.xlsx)
echo ========================================
echo.
echo 1. 打开 SSMS，执行本目录下的 display.sql
echo.
echo 2. 查询结果网格中右键
echo    - 将结果另存为...
echo    - 保存类型: Excel
echo    - 文件名: display.xlsx
echo    - 保存到: %CD%
echo.
echo 3. 运行 start_template.bat，点 Display 库里的「刷新」
echo.

if exist "display.xlsx" (
    echo [OK] 已找到 display.xlsx
    python -c "from display_lookup import load_from_excel; items=load_from_excel(); print(f'     共 {len(items)} 款 Display 产品')" 2>nul
    if errorlevel 1 (
        echo [提示] 若解析失败请: pip install openpyxl pandas
    )
) else (
    echo [缺少] display.xlsx — 请按上面步骤从 SQL 导出
)

echo.
echo SQL 文件: %CD%\display.sql
echo.
pause
