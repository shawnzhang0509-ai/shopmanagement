"""环境检查脚本 — 在启动 layout.py 前运行: python check_env.py"""
from __future__ import annotations

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

REQUIRED_FILES = ["layout.py", "furniture_templates.json", "furniture_sim.py", "ui_common.py"]
OPTIONAL_FILES = ["start.bat", "start_furniture_sim.bat", "grab_display.bat", "install.bat"]


def ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def main() -> int:
    print("=" * 50)
    print("坪效布局编辑器 - 环境检查")
    print("=" * 50)
    errors = 0

    print(f"\nPython: {sys.version}")
    print(f"工作目录: {os.getcwd()}")

    print("\n--- 依赖检查 ---")
    try:
        import pygame  # noqa: F401
        import pygame as pg
        ok(f"pygame / pygame-ce  {getattr(pg, 'version', None) and pg.version.ver}")
    except ModuleNotFoundError:
        fail("未安装 pygame-ce")
        print("       修复: python -m pip install pygame-ce")
        errors += 1

    try:
        import tkinter  # noqa: F401
        ok("tkinter")
    except ModuleNotFoundError:
        fail("未安装 tkinter（重装 Python 时勾选 tcl/tk）")
        errors += 1

    for label, mod in [
        ("pandas", "pandas"),
        ("openpyxl", "openpyxl"),
        ("Pillow", "PIL"),
        ("sqlalchemy", "sqlalchemy"),
        ("pymssql", "pymssql"),
    ]:
        try:
            __import__(mod)
            ok(label)
        except ModuleNotFoundError:
            fail(f"未安装 {label}（数据抓取需要）")
            print("       修复: python -m pip install -r requirements.txt")
            errors += 1

    print("\n--- 文件检查 ---")
    for name in REQUIRED_FILES:
        if os.path.isfile(name):
            ok(name)
        else:
            fail(f"缺少文件: {name}")
            errors += 1
    for name in OPTIONAL_FILES:
        if os.path.isfile(name):
            ok(f"{name} (可选)")

    print("\n--- 模板数据 ---")
    if os.path.isfile("furniture_templates.json"):
        try:
            import json
            data = json.load(open("furniture_templates.json", encoding="utf-8"))
            ok(f"furniture_templates.json  共 {len(data)} 个模板")
        except Exception as e:
            fail(f"furniture_templates.json 解析失败: {e}")
            errors += 1

    print("\n--- Display 库 (模板编辑器) ---")
    if os.path.isfile("display_lookup.py"):
        ok("display_lookup.py")
        try:
            from display_lookup import load_from_excel, last_load_error, resolve_display_excel_paths
            paths = resolve_display_excel_paths()
            found = next((p for p in paths if os.path.isfile(p)), None)
            if found:
                items = load_from_excel()
                if items:
                    ok(f"{os.path.basename(found)}  共 {len(items)} 款 Display")
                else:
                    fail(last_load_error() or "display.xlsx 无有效数据")
                    errors += 1
            else:
                print("  [提示] 未找到 Display 数据 — 先运行 grab_display.bat")
        except Exception as e:
            fail(f"display_lookup 异常: {e}")
            errors += 1
    if os.path.isfile("sql/display.sql"):
        ok("sql/display.sql")
    if os.path.isfile("grabber_config.json"):
        ok("grabber_config.json")
    elif os.path.isfile("grabber_config.example.json"):
        print("  [提示] 复制 grabber_config.example.json → grabber_config.json")

    print("\n--- 模块导入测试 ---")
    if errors == 0:
        try:
            import pygame
            pygame.init()
            import ui_common
            if not hasattr(ui_common, "init_fonts"):
                fail("ui_common.py 版本过旧，请 git pull 更新")
                errors += 1
            else:
                ui_common.init_fonts()
                ok(f"ui_common v{getattr(ui_common, '__version__', '?')} 加载成功")
            pygame.quit()
        except Exception as e:
            fail(f"ui_common 加载异常: {e}")
            errors += 1

    print("\n--- 显示测试 ---")
    if errors == 0:
        try:
            import pygame
            pygame.init()
            pygame.display.set_mode((1, 1))
            pygame.quit()
            ok("pygame 窗口可以创建")
        except Exception as e:
            fail(f"无法创建窗口: {e}")
            errors += 1

    print("\n" + "=" * 50)
    if errors:
        print(f"检查未通过，共 {errors} 项问题。请按上面提示修复。")
        return 1
    print("全部通过！推荐入口:")
    print("  启动.bat                   (统一入口 — 数据 / 测绘 / 布局)")
    print("  start.bat                  (坪效布局编辑器 layout.py)")
    print("  start_furniture_sim.bat    (家具模板 / Display 大库)")
    print("  grab_display.bat           (抓取 Display 数据)")
    return 0


if __name__ == "__main__":
    code = main()
    if sys.platform == "win32":
        input("\n按 Enter 退出...")
    raise SystemExit(code)
