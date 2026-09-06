#!/usr/bin/env python3
"""坪效管理 — 统一启动入口（数据抓取 / 家具测绘 / 门店布局）。"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import traceback

import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

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
APP_VERSION = "2.4.0"

BG = "#f4f6f8"
CARD = "#ffffff"
TEXT = "#2c3e50"
MUTED = "#7f8c8d"
ACCENT = "#3498db"
ACCENT_DARK = "#2980b9"
OK = "#27ae60"
WARN = "#e67e22"


class DataGrabDialog(tk.Toplevel):
    """勾选要抓取的数据类型，一次执行。"""

    def __init__(self, parent: tk.Misc, *, on_status=None) -> None:
        super().__init__(parent)
        self.title("数据抓取 — 选择要更新的内容")
        self.geometry("560x480")
        self.minsize(480, 420)
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()
        self._on_status = on_status
        self._running = False

        from display_lookup import build_runtime_config, load_grabber_config

        cfg = load_grabber_config()
        runtime = build_runtime_config(cfg)

        intro = tk.Label(
            self,
            text="勾选需要的 Excel，点「开始抓取」。Display 与周销量可分开，避免周销量超时拖垮 Display。",
            font=("Microsoft YaHei UI", 10),
            bg=BG,
            fg=TEXT,
            wraplength=520,
            justify="left",
        )
        intro.pack(anchor="w", padx=16, pady=(14, 8))

        opts = ttk.LabelFrame(self, text="抓取内容", padding=12)
        opts.pack(fill="x", padx=16, pady=6)

        self.var_display = tk.BooleanVar(value=True)
        self.var_sales = tk.BooleanVar(value=bool(cfg.get("grab_sales_with_display", False)))
        self.var_stock = tk.BooleanVar(value=False)
        self.var_roi = tk.BooleanVar(value=bool(cfg.get("sync_roi_after_grab", False)))

        ttk.Checkbutton(
            opts,
            text="Display 大库 → data/display.xlsx（含 ImageUrl、停产 Demo）",
            variable=self.var_display,
        ).pack(anchor="w")
        ttk.Checkbutton(
            opts,
            text="周销量 → data/weekly_sales.xlsx（较慢，可单独勾选）",
            variable=self.var_sales,
        ).pack(anchor="w", pady=(6, 0))
        ttk.Checkbutton(
            opts,
            text="仓库库存/价格 → data/product_stock_price.xlsx",
            variable=self.var_stock,
        ).pack(anchor="w", pady=(6, 0))
        ttk.Checkbutton(
            opts,
            text="同步 ROI 到 furniture_templates.json 与门店布局",
            variable=self.var_roi,
        ).pack(anchor="w", pady=(6, 0))

        sql_label = os.path.relpath(runtime["sql_file"], SCRIPT_DIR)
        tk.Label(
            opts,
            text=f"Display SQL: {sql_label}",
            font=("Microsoft YaHei UI", 9),
            fg=MUTED,
        ).pack(anchor="w", pady=(10, 0))

        log_frame = ttk.LabelFrame(self, text="执行日志", padding=8)
        log_frame.pack(fill="both", expand=True, padx=16, pady=6)
        self.log_text = scrolledtext.ScrolledText(
            log_frame, height=10, bg="#111827", fg="#e5e7eb", font=("Consolas", 9)
        )
        self.log_text.pack(fill="both", expand=True)

        btn_row = tk.Frame(self, bg=BG)
        btn_row.pack(fill="x", padx=16, pady=(0, 14))
        self.run_btn = ttk.Button(btn_row, text="开始抓取", command=self._start_grab)
        self.run_btn.pack(side="left")
        ttk.Button(btn_row, text="关闭", command=self.destroy).pack(side="right")

    def _log(self, msg: str) -> None:
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        if self._on_status:
            self._on_status.set(msg)

    def _start_grab(self) -> None:
        if self._running:
            return
        if not any(
            (
                self.var_display.get(),
                self.var_sales.get(),
                self.var_stock.get(),
                self.var_roi.get(),
            )
        ):
            messagebox.showwarning("未选择", "请至少勾选一项。", parent=self)
            return
        self._running = True
        self.run_btn.config(state="disabled")
        self.log_text.delete("1.0", "end")
        threading.Thread(target=self._grab_worker, daemon=True).start()

    def _grab_worker(self) -> None:
        ok = True
        try:
            from display_lookup import (
                build_runtime_config,
                grab_sql_to_excel,
                last_sql_file,
                load_grabber_config,
                run_grab_pipeline,
            )
            from stock_price_lookup import DEFAULT_EXCEL, STOCK_PRICE_SQL, reload_stock_prices

            cfg = load_grabber_config()

            if self.var_display.get() or self.var_sales.get() or self.var_roi.get():
                self._log("── 开始 Display / 周销量 / ROI ──")
                results = run_grab_pipeline(
                    cfg,
                    display=self.var_display.get(),
                    sales=self.var_sales.get(),
                    sync_roi=self.var_roi.get(),
                    log=self._log,
                )
                if self.var_display.get():
                    disp = results.get("display", {})
                    self._log(f"Display: {disp.get('count', 0)} 款")
                    sql_used = last_sql_file()
                    if sql_used:
                        self._log(f"实际 SQL: {os.path.basename(sql_used)}")
                if self.var_sales.get() and "sales" not in results:
                    ok = False

            if self.var_stock.get():
                self._log("── 开始仓库库存/价格 ──")
                runtime = build_runtime_config(cfg)
                stock_cfg = {
                    **cfg,
                    "sql_file": cfg.get("stock_price_sql_file") or STOCK_PRICE_SQL,
                    "output_excel": cfg.get("stock_price_output_excel") or DEFAULT_EXCEL,
                }
                rows, excel_path = grab_sql_to_excel(stock_cfg)
                cache = reload_stock_prices(excel_path)
                self._log(f"库存/价格: {len(rows)} 行 · {len(cache)} SKU → {excel_path}")

            self._log("── 全部完成 ──")
        except Exception as exc:
            ok = False
            self._log(f"失败: {exc}")
            self._log(traceback.format_exc())

        def finish() -> None:
            self._running = False
            self.run_btn.config(state="normal")
            if ok:
                messagebox.showinfo("抓取完成", "所选数据已更新，详见日志。", parent=self)
            else:
                messagebox.showerror("抓取失败", "部分任务失败，请查看日志。", parent=self)

        self.after(0, finish)


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
            text="一个入口 · 数据抓取 · 家具测绘 · 门店坪效 · 多店对比",
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
        for col in range(4):
            cards.columnconfigure(col, weight=1)

        self._card(
            cards,
            0,
            "① 数据抓取",
            "Display 库存 · 周销量 · 仓库库存/价格 · ROI 同步",
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
        self._card(
            cards,
            3,
            "④ 多店对比",
            "多店一屏 · 系列横向柱图 · 4/8/12 周",
            "#e67e22",
            lambda: self.launch("store_dashboard.py", "多店对比"),
        )

        data_frame = ttk.LabelFrame(self.root, text="数据抓取（常用）", padding=12)
        data_frame.pack(fill="x", padx=20, pady=(0, 12))
        row = tk.Frame(data_frame)
        row.pack(fill="x")
        ttk.Button(row, text="选择抓取内容…", command=self.show_grab_wizard).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Display 高级/定时", command=lambda: self.launch("grab_display_gui.py", "Display 抓取工具", gui=True)).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(row, text="仅周销量", command=lambda: self._quick_grab(sales_only=True)).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="仅库存/价格", command=lambda: self._quick_grab(stock_only=True)).pack(side="left", padx=(0, 8))
        tk.Label(
            data_frame,
            text="推荐点「选择抓取内容」勾选 Display / 周销量 / 库存价格 / ROI；周销量较慢时可只勾 Display。",
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

    def launch(self, filename: str, label: str, *, gui: bool = False) -> None:
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
        self._spawn([sys.executable, path], label, new_console=not gui)

    def launch_script(self, rel_path: str, label: str, *, wait: bool = False) -> None:
        path = os.path.join(SCRIPT_DIR, rel_path)
        if not os.path.isfile(path):
            messagebox.showerror("找不到文件", path, parent=self.root)
            return
        if "grab_sales" in rel_path or "grab_display" in rel_path or "grab_stock_price" in rel_path or "update_roi" in rel_path:
            if not self._require_deps(["pymssql", "sqlalchemy", "pandas", "openpyxl"]):
                return
        cmd = [sys.executable, path]
        if wait:
            subprocess.run(cmd, cwd=SCRIPT_DIR)
            self.refresh_status()
        else:
            self._spawn(cmd, label)

    def _spawn(self, cmd: list[str], label: str, *, new_console: bool = True) -> None:
        try:
            kwargs: dict = {"cwd": SCRIPT_DIR}
            if sys.platform == "win32" and new_console:
                kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
            subprocess.Popen(cmd, **kwargs)
            self.status_var.set(f"已启动: {label}")
        except Exception as exc:
            messagebox.showerror("启动失败", str(exc), parent=self.root)

    def show_grab_wizard(self) -> None:
        if not self._require_deps(["pymssql", "sqlalchemy", "pandas", "openpyxl"]):
            return
        DataGrabDialog(self.root, on_status=self.status_var.set)

    def _quick_grab(self, *, sales_only: bool = False, stock_only: bool = False) -> None:
        if not self._require_deps(["pymssql", "sqlalchemy", "pandas", "openpyxl"]):
            return
        dlg = DataGrabDialog(self.root, on_status=self.status_var.set)
        dlg.var_display.set(False)
        dlg.var_sales.set(sales_only)
        dlg.var_stock.set(stock_only)
        dlg.var_roi.set(False)

    def show_data_menu(self) -> None:
        self.show_grab_wizard()

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
