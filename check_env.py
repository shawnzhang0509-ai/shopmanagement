"""环境检查脚本 — 在启动 layout.py 前运行: python check_env.py"""
from __future__ import annotations

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

REQUIRED_FILES = ["layout.py", "furniture_templates.json", "furniture_sim.py", "ui_common.py"]
OPTIONAL_FILES = ["saved_layout.json", "start.bat", "start_template.bat"]


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

    print("\n--- 模块导入测试 ---")
    if errors == 0:
        try:
            import pygame
            pygame.init()
            from ui_common import init_fonts
            init_fonts()
            ok("ui_common 加载成功")
            pygame.quit()
        except Exception as e:
            fail(f"ui_common / furniture_sim 依赖异常: {e}")
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
    print("全部通过！可以运行:")
    print("  python layout.py")
    print("  python furniture_sim.py")
    return 0


if __name__ == "__main__":
    code = main()
    if sys.platform == "win32":
        input("\n按 Enter 退出...")
    raise SystemExit(code)
