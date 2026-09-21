"""依赖检查与一键安装 — 各模块启动前共用。"""
from __future__ import annotations

import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# (import 名, pip 包名, 用途)
DEPENDENCIES: list[tuple[str, str, str]] = [
    ("pygame", "pygame-ce", "布局 / 测绘界面"),
    ("pymssql", "pymssql", "数据库抓取"),
    ("sqlalchemy", "sqlalchemy", "数据库连接"),
    ("pandas", "pandas", "Excel 数据处理"),
    ("openpyxl", "openpyxl", "Excel 读写"),
    ("PIL", "Pillow", "产品图片"),
]


def project_root() -> str:
    return SCRIPT_DIR


def chdir_project() -> None:
    os.chdir(SCRIPT_DIR)


def check_dependencies() -> list[tuple[str, str, str]]:
    missing: list[tuple[str, str, str]] = []
    for import_name, pip_name, purpose in DEPENDENCIES:
        try:
            __import__(import_name)
        except ImportError:
            missing.append((import_name, pip_name, purpose))
    return missing


def install_dependencies(*, log=print) -> bool:
    req = os.path.join(SCRIPT_DIR, "requirements.txt")
    if not os.path.isfile(req):
        log("未找到 requirements.txt")
        return False
    log("正在安装依赖（首次约 1–3 分钟）…")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
            cwd=SCRIPT_DIR,
            check=False,
        )
        subprocess.run(
            [sys.executable, "-m", "pip", "uninstall", "pygame", "-y"],
            cwd=SCRIPT_DIR,
            capture_output=True,
        )
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", req],
            cwd=SCRIPT_DIR,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            log(result.stderr or result.stdout or "pip install 失败")
            return False
        log("依赖安装完成。")
        return True
    except Exception as exc:
        log(f"安装失败: {exc}")
        return False


def ensure_dependencies(*, auto_install: bool = False, log=print) -> bool:
    missing = check_dependencies()
    if not missing:
        return True
    names = ", ".join(pip for _, pip, _ in missing)
    log(f"缺少依赖: {names}")
    if auto_install:
        return install_dependencies(log=log)
    return False


def missing_summary() -> str:
    missing = check_dependencies()
    if not missing:
        return "依赖已就绪"
    return "缺少: " + ", ".join(pip for _, pip, _ in missing)
