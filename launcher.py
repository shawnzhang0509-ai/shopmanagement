#!/usr/bin/env python3
"""坪效管理 — 统一启动入口（数据抓取 / 家具测绘 / 门店布局）。"""
from __future__ import annotations

import os
import subprocess
import sys

import tkinter as tk
from tkinter import messagebox, ttk

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from deps_check import (
    check_dependencies,
    ensure_dependencies,
    install_dependencies,
    missing_summary,
)

APP_TITLE = "坪效管理工具"
APP_VERSION = "2.2.0"

BG = "#f4f6f8"
CARD = "#ffffff"
TEXT = "#2c3e50"
MUTED = "#7f8c8d"
ACCENT = "#3498db"
ACCENT_DARK = "#2980b9"
OK = "#27ae60"
WARN = "#e67e22"


class LauncherApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title(f"{APP_TITLE} v{APP_VERSION}")
        self.root.geometry("720x520")
        self.root.minsize(640, 480)
        self.root.configure(bg=BG)

        self._build_ui()
        self.refresh_status()

    def _build_ui(self) -> None:
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=20, pady=(18, 8))
        tk.Label(header, text=APP_TITLE, font=("Microsoft YaHei UI", 20, "bold"), bg=BG, fg=TEXT).pack(
            anchor="w"
        )
        tk.Label(
            header,
            text="一个入口 · 数据抓取 · 家具测绘 · 门店坪效布局",
            font=("Microsoft YaHei UI", 11),
            bg=BG,
            fg=MUTED,
        ).pack(anchor="w", pady=(4, 0))

        status_row = tk.Frame(self.root, bg=BG)
        status_row.pack(fill="x", padx=20, pady=(0, 10))
        self.status_var = tk.StringVar(value="检查环境中…")
        tk.Label(status_row, textvariable=self.status_var, font=("Microsoft YaHei UI", 10), bg=BG, fg=TEXT).pack(
            side="left"
        )
        ttk.Button(status_row, text="一键安装依赖", command=self.on_install).pack(side="right", padx=(6, 0))
        ttk.Button(status_row, text="环境检查", command=self.on_check_env).pack(side="right")

        cards = tk.Frame(self.root, bg=BG)
        cards.pack(fill="both", expand=True, padx=20, pady=8)
        for col in range(3):
            cards.columnconfigure(col, weight=1)

        self._card(
            cards,
            0,
            "① 数据抓取",
            "Display 库存 · 周销量 · ROI 同步",
            ACCENT,
            self.show_data_menu,
        )
        self._card(
            cards,
            1,
            "② 家具测绘",
            "Display 大库 · 编辑家具模板轮廓",
            "#8e44ad",
            lambda: self.launch("furniture_sim.py", "家具测绘"),
        )
        self._card(
            cards,
            2,
            "③ 坪效布局",
            "门店平面图 · 家具摆放 · 坪效热力图",
            "#16a085",
            lambda: self.launch("layout.py", "坪效布局"),
        )

        data_frame = ttk.LabelFrame(self.root, text="数据抓取（常用）", padding=12)
        data_frame.pack(fill="x", padx=20, pady=(0, 12))
        row = tk.Frame(data_frame)
        row.pack(fill="x")
        ttk.Button(row, text="Display 数据抓取", command=lambda: self.launch("grab_display_gui.py", "Display")).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(row, text="周销量抓取", command=lambda: self.launch_script("scripts/grab_sales.py", "周销量")).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(row, text="同步 ROI 到模板", command=lambda: self.launch_script("scripts/update_roi.py", "ROI")).pack(
            side="left", padx=(0, 8)
        )
        tk.Label(
            data_frame,
            text="Display 抓取默认同时导出周销量；ROI 同步可在抓取工具里勾选，或点「同步 ROI 到模板」",
            font=("Microsoft YaHei UI", 9),
            fg=MUTED,
        ).pack(anchor="w", pady=(8, 0))

        foot = tk.Label(
            self.root,
            text=f"项目目录: {SCRIPT_DIR}  |  v{APP_VERSION}",
            font=("Microsoft YaHei UI", 9),
            bg=BG,
            fg=MUTED,
        )
        foot.pack(side="bottom", anchor="w", padx=20, pady=10)

    def _card(self, parent, col: int, title: str, subtitle: str, color: str, command) -> None:
        frame = tk.Frame(parent, bg=CARD, highlightbackground="#dfe6e9", highlightthickness=1)
        frame.grid(row=0, column=col, sticky="nsew", padx=6, pady=6)
        inner = tk.Frame(frame, bg=CARD)
        inner.pack(fill="both", expand=True, padx=16, pady=18)
        tk.Label(inner, text=title, font=("Microsoft YaHei UI", 15, "bold"), bg=CARD, fg=color).pack(anchor="w")
        tk.Label(inner, text=subtitle, font=("Microsoft YaHei UI", 10), bg=CARD, fg=MUTED, wraplength=180, justify="left").pack(
            anchor="w", pady=(10, 16)
        )
        btn = tk.Button(
            inner,
            text="打开",
            font=("Microsoft YaHei UI", 11, "bold"),
            bg=color,
            fg="white",
            activebackground=ACCENT_DARK,
            activeforeground="white",
            relief="flat",
            padx=18,
            pady=8,
            cursor="hand2",
            command=command,
        )
        btn.pack(anchor="w")

    def refresh_status(self) -> None:
        missing = check_dependencies()
        if not missing:
            self.status_var.set(f"✅ 环境就绪  ·  Python {sys.version.split()[0]}")
        else:
            self.status_var.set(f"⚠️  {missing_summary()}  —  请先点「一键安装依赖」")

    def on_install(self) -> None:
        if install_dependencies(log=self._log_dialog):
            messagebox.showinfo("完成", "依赖已安装。可以打开各模块了。", parent=self.root)
            self.refresh_status()
        else:
            messagebox.showerror(
                "安装失败",
                "请确认已安装 Python 3.11+，并在项目目录运行。\n也可手动执行: install.bat",
                parent=self.root,
            )

    def on_check_env(self) -> None:
        self.launch_script("check_env.py", "环境检查", wait=True)

    def _log_dialog(self, msg: str) -> None:
        self.status_var.set(str(msg))

    def _require_deps(self, modules: list[str] | None = None) -> bool:
        missing = check_dependencies()
        if modules:
            missing = [m for m in missing if m[0] in modules]
        if not missing:
            return True
        names = ", ".join(pip for _, pip, _ in missing)
        if messagebox.askyesno(
            "缺少依赖",
            f"缺少: {names}\n\n是否现在自动安装？",
            parent=self.root,
        ):
            if install_dependencies(log=self._log_dialog):
                self.refresh_status()
                return not check_dependencies()
        return False

    def launch(self, filename: str, label: str) -> None:
        path = os.path.join(SCRIPT_DIR, filename)
        if not os.path.isfile(path):
            messagebox.showerror("找不到文件", path, parent=self.root)
            return
        need = ["pygame"] if filename in ("layout.py", "furniture_sim.py") else []
        if filename == "grab_display_gui.py":
            need = ["pymssql", "sqlalchemy", "pandas", "openpyxl"]
        if need and not self._require_deps(need):
            return
        if filename == "layout.py" and not os.path.isfile("furniture_templates.json"):
            messagebox.showwarning(
                "缺少模板",
                "未找到 furniture_templates.json。\n请先运行「家具测绘」或从仓库拉取模板文件。",
                parent=self.root,
            )
            return
        self._spawn([sys.executable, path], label)

    def launch_script(self, rel_path: str, label: str, *, wait: bool = False) -> None:
        path = os.path.join(SCRIPT_DIR, rel_path)
        if not os.path.isfile(path):
            messagebox.showerror("找不到文件", path, parent=self.root)
            return
        if "grab_sales" in rel_path or "grab_display" in rel_path or "update_roi" in rel_path:
            if not self._require_deps(["pymssql", "sqlalchemy", "pandas", "openpyxl"]):
                return
        cmd = [sys.executable, path]
        if wait:
            subprocess.run(cmd, cwd=SCRIPT_DIR)
            self.refresh_status()
        else:
            self._spawn(cmd, label)

    def _spawn(self, cmd: list[str], label: str) -> None:
        try:
            if sys.platform == "win32":
                subprocess.Popen(
                    cmd,
                    cwd=SCRIPT_DIR,
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
            else:
                subprocess.Popen(cmd, cwd=SCRIPT_DIR)
            self.status_var.set(f"已启动: {label}")
        except Exception as exc:
            messagebox.showerror("启动失败", str(exc), parent=self.root)

    def show_data_menu(self) -> None:
        self.launch("grab_display_gui.py", "Display 数据抓取")

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    if not ensure_dependencies(auto_install=False):
        pass
    app = LauncherApp()
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
