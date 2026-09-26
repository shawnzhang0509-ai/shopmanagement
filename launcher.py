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
APP_VERSION = "2.4.3"

BG = "#f4f6f8"
CARD = "#ffffff"
TEXT = "#2c3e50"
MUTED = "#7f8c8d"
ACCENT = "#3498db"
ACCENT_DARK = "#2980b9"
OK = "#27ae60"
WARN = "#e67e22"


class DataGrabDialog(tk.Toplevel):
    """勾选地区 + 抓取内容，一次执行（布局：底部按钮固定可见）。"""

    def __init__(self, parent: tk.Misc, *, on_status=None) -> None:
        super().__init__(parent)
        self.title("数据抓取 — 选择要更新的内容")
        self.geometry("640x780")
        self.minsize(580, 680)
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()
        self._on_status = on_status
        self._running = False

        from display_lookup import build_runtime_config, load_grabber_config, save_grabber_config, test_database_connection
        from region_config import SUPPORTED_REGIONS, config_for_region, merge_region_config, region_database_url, region_labels

        self._save_grabber_config = save_grabber_config
        self._test_database_connection = test_database_connection
        self._config_for_region = config_for_region

        cfg = load_grabber_config()
        self._base_cfg = cfg
        self._region_fields: dict[str, dict[str, str]] = {}
        self._edit_region_var = tk.StringVar(value="nz")
        run_list = cfg.get("run_regions") or [cfg.get("active_region", "nz")]
        self._run_vars: dict[str, tk.BooleanVar] = {
            rid: tk.BooleanVar(value=(rid in run_list)) for rid in SUPPORTED_REGIONS
        }

        # 底部按钮先 pack，避免被日志区挤出屏幕外
        btn_row = tk.Frame(self, bg=BG)
        btn_row.pack(side="bottom", fill="x", padx=16, pady=(8, 14))
        self.run_btn = tk.Button(
            btn_row,
            text="开始抓取",
            font=("Microsoft YaHei UI", 11, "bold"),
            bg=ACCENT,
            fg="white",
            activebackground=ACCENT_DARK,
            activeforeground="white",
            relief="flat",
            padx=20,
            pady=8,
            cursor="hand2",
            command=self._start_grab,
        )
        self.run_btn.pack(side="left")
        ttk.Button(btn_row, text="保存连接配置", command=self._save_region_config).pack(side="left", padx=(10, 0))
        ttk.Button(btn_row, text="关闭", command=self.destroy).pack(side="right")

        body = tk.Frame(self, bg=BG)
        body.pack(side="top", fill="both", expand=True)

        intro = tk.Label(
            body,
            text="勾选地区与 Excel 类型，点下方「开始抓取」。周销量较慢时可只勾 Display。",
            font=("Microsoft YaHei UI", 10),
            bg=BG,
            fg=TEXT,
            wraplength=560,
            justify="left",
        )
        intro.pack(anchor="w", padx=16, pady=(14, 8))

        region_frame = ttk.LabelFrame(body, text="本次要跑的地区（可多选）", padding=10)
        region_frame.pack(fill="x", padx=16, pady=(0, 6))
        region_checks = tk.Frame(region_frame)
        region_checks.pack(anchor="w")
        for rid, label in region_labels():
            ttk.Checkbutton(
                region_checks,
                text=label,
                variable=self._run_vars[rid],
                command=self._refresh_path_hints,
            ).pack(side="left", padx=(0, 16))

        cfg_frame = ttk.LabelFrame(
            body,
            text="地区连接（NZ / AU / CA 各自 database_url · 保存到 grabber_config.json）",
            padding=8,
        )
        cfg_frame.pack(fill="x", padx=16, pady=(0, 6))
        ttk.Label(cfg_frame, text="正在编辑").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        edit_values = [f"{rid.upper()} {label}" for rid, label in region_labels()]
        self._edit_combo = ttk.Combobox(cfg_frame, values=edit_values, state="readonly", width=16)
        self._edit_combo.grid(row=0, column=1, sticky="w", padx=6, pady=4)
        self._edit_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_edit_region_changed())

        ttk.Label(cfg_frame, text="数据库连接").grid(row=1, column=0, sticky="nw", padx=6, pady=4)
        db_wrap = ttk.Frame(cfg_frame)
        db_wrap.grid(row=1, column=1, columnspan=2, sticky="ew", padx=6, pady=4)
        self.db_entry = tk.Text(db_wrap, height=2, width=72, wrap="word")
        self.db_entry.pack(fill="x", expand=True)
        ttk.Button(db_wrap, text="测试连接", command=self._test_region_connection).pack(anchor="e", pady=(4, 0))

        ttk.Label(cfg_frame, text="SQL 目录").grid(row=2, column=0, sticky="w", padx=6, pady=4)
        self.sql_folder_var = tk.StringVar(value="sql/nz")
        ttk.Entry(cfg_frame, textvariable=self.sql_folder_var, width=52).grid(
            row=2, column=1, sticky="ew", padx=6, pady=4
        )
        ttk.Label(cfg_frame, text="输出目录").grid(row=3, column=0, sticky="w", padx=6, pady=4)
        self.output_folder_var = tk.StringVar(value="data/nz")
        ttk.Entry(cfg_frame, textvariable=self.output_folder_var, width=52).grid(
            row=3, column=1, sticky="ew", padx=6, pady=4
        )
        tk.Label(
            cfg_frame,
            text="完整定时调度请用下方「Display 高级/定时」。切换上方地区后分别填写并保存。",
            font=("Microsoft YaHei UI", 9),
            fg=MUTED,
        ).grid(row=4, column=0, columnspan=3, sticky="w", padx=6, pady=(0, 4))
        cfg_frame.columnconfigure(1, weight=1)
        self._load_region_fields_from_cfg(cfg)
        active = cfg.get("active_region") or "nz"
        self._set_edit_region(str(active).lower())

        opts = ttk.LabelFrame(body, text="抓取内容", padding=12)
        opts.pack(fill="x", padx=16, pady=6)

        self.var_display = tk.BooleanVar(value=True)
        self.var_sales = tk.BooleanVar(value=bool(cfg.get("grab_sales_with_display", False)))
        self.var_stock = tk.BooleanVar(value=False)
        self.var_roi = tk.BooleanVar(value=bool(cfg.get("sync_roi_after_grab", False)))

        runtime = build_runtime_config(cfg)
        out_folder = runtime.get("output_folder") or "data/nz"
        self.display_path_var = tk.StringVar(
            value=f"Display 大库 → {out_folder}/display.xlsx"
        )
        self.sales_path_var = tk.StringVar(
            value=f"周销量 → {out_folder}/weekly_sales.xlsx（较慢）"
        )
        self.stock_path_var = tk.StringVar(
            value=f"仓库库存/价格 → {out_folder}/product_stock_price.xlsx"
        )
        self.sql_hint_var = tk.StringVar(
            value=f"SQL 目录: {runtime.get('sql_folder', 'sql/nz')}/"
        )

        ttk.Checkbutton(opts, textvariable=self.display_path_var, variable=self.var_display).pack(anchor="w")
        ttk.Checkbutton(opts, textvariable=self.sales_path_var, variable=self.var_sales).pack(
            anchor="w", pady=(6, 0)
        )
        ttk.Checkbutton(opts, textvariable=self.stock_path_var, variable=self.var_stock).pack(
            anchor="w", pady=(6, 0)
        )
        ttk.Checkbutton(
            opts,
            text="同步 ROI 到 furniture_templates.json 与门店布局",
            variable=self.var_roi,
        ).pack(anchor="w", pady=(6, 0))
        tk.Label(
            opts,
            textvariable=self.sql_hint_var,
            font=("Microsoft YaHei UI", 9),
            fg=MUTED,
        ).pack(anchor="w", pady=(8, 0))

        log_frame = ttk.LabelFrame(body, text="执行日志", padding=8)
        log_frame.pack(fill="both", expand=True, padx=16, pady=(6, 8))
        self.log_text = scrolledtext.ScrolledText(
            log_frame, height=6, bg="#111827", fg="#e5e7eb", font=("Consolas", 9)
        )
        self.log_text.pack(fill="both", expand=True)

        self._refresh_path_hints()

    def _edit_region_id(self) -> str:
        text = self._edit_combo.get().strip()
        return text.split()[0].lower() if text else "nz"

    def _set_edit_region(self, region_id: str) -> None:
        from region_config import REGION_LABELS

        label = REGION_LABELS.get(region_id, region_id.upper())
        self._edit_combo.set(f"{region_id.upper()} {label}")
        self._edit_region_var.set(region_id)
        self._load_editor(region_id)

    def _flush_editor(self) -> None:
        rid = self._edit_region_id()
        self._region_fields[rid] = {
            "database_url": self.db_entry.get("1.0", "end").strip(),
            "sql_folder": self.sql_folder_var.get().strip(),
            "output_folder": self.output_folder_var.get().strip(),
        }

    def _load_editor(self, region_id: str) -> None:
        from region_config import merge_region_config, region_database_url

        fields = self._region_fields.get(region_id, {})
        runtime = merge_region_config({**self._base_cfg, "active_region": region_id}, region_id)
        self.db_entry.delete("1.0", "end")
        db = fields.get("database_url") or region_database_url(self._base_cfg, region_id)
        if db:
            self.db_entry.insert("1.0", db)
        self.sql_folder_var.set(fields.get("sql_folder") or runtime.get("sql_folder") or f"sql/{region_id}")
        self.output_folder_var.set(
            fields.get("output_folder") or runtime.get("output_folder") or f"data/{region_id}"
        )

    def _load_region_fields_from_cfg(self, cfg: dict) -> None:
        from region_config import SUPPORTED_REGIONS, merge_region_config, region_database_url

        regions = cfg.get("regions") or {}
        for rid in SUPPORTED_REGIONS:
            section = dict(regions.get(rid) or {})
            runtime = merge_region_config({**cfg, "active_region": rid}, rid)
            db_url = str(section.get("database_url") or runtime.get("database_url") or "").strip()
            if not db_url and rid == "nz":
                db_url = str(cfg.get("database_url") or "").strip()
            self._region_fields[rid] = {
                "database_url": db_url,
                "sql_folder": section.get("sql_folder") or runtime.get("sql_folder", f"sql/{rid}"),
                "output_folder": section.get("output_folder") or runtime.get("output_folder", f"data/{rid}"),
            }

    def _on_edit_region_changed(self) -> None:
        self._flush_editor()
        self._set_edit_region(self._edit_region_id())

    def _merge_region_config_into_base(self) -> dict:
        from display_lookup import reload_shops
        from region_config import SUPPORTED_REGIONS

        self._flush_editor()
        cfg = dict(self._base_cfg)
        regions: dict[str, dict] = dict(cfg.get("regions") or {})
        for rid in SUPPORTED_REGIONS:
            fields = self._region_fields.get(rid, {})
            section = dict(regions.get(rid) or {})
            for key in ("database_url", "sql_folder", "output_folder"):
                val = str(fields.get(key) or "").strip()
                if val:
                    section[key] = val
            regions[rid] = section
        selected = self._selected_regions()
        active = selected[0] if selected else self._edit_region_id()
        cfg.update(
            {
                "active_region": active,
                "run_regions": selected or [active],
                "regions": regions,
                "grab_sales_with_display": bool(self.var_sales.get()),
                "sync_roi_after_grab": bool(self.var_roi.get()),
            }
        )
        reload_shops(cfg)
        self._base_cfg = cfg
        return cfg

    def _save_region_config(self) -> None:
        cfg = self._merge_region_config_into_base()
        self._save_grabber_config(cfg)
        self._log("已保存各地区 database_url / SQL / 输出目录 → grabber_config.json")
        messagebox.showinfo("已保存", "连接配置已写入 grabber_config.json", parent=self)

    def _test_region_connection(self) -> None:
        self._flush_editor()
        rid = self._edit_region_id()
        cfg = self._merge_region_config_into_base()
        region_cfg = self._config_for_region(cfg, rid)
        self._log(f"测试 {rid.upper()} 数据库连接…")

        def worker() -> None:
            ok, msg = self._test_database_connection(region_cfg)
            title = f"{rid.upper()} 连接测试"

            def done() -> None:
                self._log(msg if ok else f"失败: {msg}")
                if ok:
                    messagebox.showinfo(title, msg, parent=self)
                else:
                    messagebox.showerror(title, msg, parent=self)

            self.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def _selected_regions(self) -> list[str]:
        from region_config import SUPPORTED_REGIONS

        return [rid for rid in SUPPORTED_REGIONS if self._run_vars[rid].get()]

    def _refresh_path_hints(self) -> None:
        from region_config import merge_region_config

        selected = self._selected_regions()
        rid = selected[0] if selected else "nz"
        runtime = merge_region_config({**self._base_cfg, "active_region": rid}, rid)
        out_folder = runtime.get("output_folder") or f"data/{rid}"
        label = runtime.get("_region_label") or rid
        suffix = f"（当前预览: {label}）" if len(selected) <= 1 else f"（预览 {label}，已选 {len(selected)} 个地区）"
        self.display_path_var.set(f"Display 大库 → {out_folder}/display.xlsx {suffix}")
        self.sales_path_var.set(f"周销量 → {out_folder}/weekly_sales.xlsx（较慢）")
        self.stock_path_var.set(f"仓库库存/价格 → {out_folder}/product_stock_price.xlsx")
        sql_folder = runtime.get("sql_folder") or f"sql/{rid}"
        sql_file = runtime.get("sql_file") or f"{sql_folder}/display.sql"
        self.sql_hint_var.set(f"SQL: {sql_file}  （支持 .sql / .txt，缺失时自动回退）")

    def _grab_cfg(self) -> dict:
        return self._merge_region_config_into_base()

    def _log(self, msg: str) -> None:
        """后台线程安全：通过 after 回到主线程写日志。"""

        def append() -> None:
            self.log_text.insert("end", msg + "\n")
            self.log_text.see("end")
            if self._on_status:
                self._on_status(msg)

        try:
            self.after(0, append)
        except tk.TclError:
            append()

    def _start_grab(self) -> None:
        if self._running:
            return
        if not self._selected_regions():
            messagebox.showwarning("未选择", "请至少勾选一个地区（新西兰/澳洲/加拿大）。", parent=self)
            return
        if not any(
            (
                self.var_display.get(),
                self.var_sales.get(),
                self.var_stock.get(),
                self.var_roi.get(),
            )
        ):
            messagebox.showwarning("未选择", "请至少勾选一项抓取内容。", parent=self)
            return
        self._save_grabber_config(self._merge_region_config_into_base())
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
                run_grab_pipeline,
            )
            from region_config import config_for_region
            from stock_price_lookup import STOCK_PRICE_SQL, reload_stock_prices

            base_cfg = self._grab_cfg()
            regions = self._selected_regions()

            for idx, region_id in enumerate(regions):
                cfg = config_for_region(base_cfg, region_id)
                label = cfg.get("_region_label", region_id)
                self._log(f"════ {label} ({region_id.upper()}) ════")
                runtime = build_runtime_config(cfg)
                self._log(f"SQL: {runtime.get('sql_folder')} → 输出: {runtime.get('output_folder')}")

                if self.var_display.get() or self.var_sales.get() or (self.var_roi.get() and idx == 0):
                    self._log("── Display / 周销量 / ROI ──")
                    results = run_grab_pipeline(
                        cfg,
                        display=self.var_display.get(),
                        sales=self.var_sales.get(),
                        sync_roi=self.var_roi.get() and idx == 0,
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
                    self._log("── 仓库库存/价格 ──")
                    stock_out = cfg.get("stock_price_output_excel") or os.path.join(
                        runtime.get("output_folder") or f"data/{region_id}",
                        "product_stock_price.xlsx",
                    )
                    stock_cfg = {
                        **cfg,
                        "sql_file": cfg.get("stock_price_sql_file") or STOCK_PRICE_SQL,
                        "output_excel": stock_out,
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
            text="「选择抓取内容」内可填 NZ/AU/CA 连接串；定时调度用「Display 高级/定时」。",
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
        pygame_apps = ("layout.py", "furniture_sim.py", "store_dashboard.py")
        need = ["pygame"] if filename in pygame_apps else []
        if filename == "grab_display_gui.py":
            need = ["pymssql", "sqlalchemy", "pandas", "openpyxl"]
        if need and not self._require_deps(need):
            return
        if filename == "layout.py":
            try:
                from display_lookup import load_grabber_config
                from region_config import get_active_region, resolve_furniture_templates_path

                cfg = load_grabber_config()
                tpl = resolve_furniture_templates_path(cfg, get_active_region(cfg))
                region = get_active_region(cfg)
                if not os.path.isfile(tpl) and region != "nz":
                    messagebox.showinfo(
                        "澳洲/加拿大首次使用",
                        f"当前区域 {region.upper()} 尚无本地测绘模板。\n"
                        f"路径：{tpl}\n\n"
                        "请配置 regions.*.database_url 后运行 grab_display，再打开家具测绘。",
                        parent=self.root,
                    )
                elif not os.path.isfile(tpl) and region == "nz":
                    messagebox.showwarning(
                        "缺少模板",
                        "未找到 furniture_templates.json / data/nz/furniture_templates.json。\n"
                        "请先运行「家具测绘」或从仓库拉取模板文件。",
                        parent=self.root,
                    )
                    return
            except Exception:
                pass
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
        DataGrabDialog(self.root, on_status=lambda msg: self.status_var.set(msg))

    def _quick_grab(self, *, sales_only: bool = False, stock_only: bool = False) -> None:
        if not self._require_deps(["pymssql", "sqlalchemy", "pandas", "openpyxl"]):
            return
        dlg = DataGrabDialog(self.root, on_status=lambda msg: self.status_var.set(msg))
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
