#!/usr/bin/env python3
"""Display / 周销量 多区域抓取工具 — GUI（参考供应链自动出数据界面）。"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import traceback
from datetime import datetime, timedelta
from tkinter import filedialog, messagebox, scrolledtext, ttk

import tkinter as tk

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from display_lookup import (
    GRABBER_CONFIG,
    build_runtime_config,
    last_sql_file,
    load_grabber_config,
    reload_shops,
    run_grab_pipeline,
    save_grabber_config,
    shop_stats,
    test_database_connection,
)
from region_config import (
    SUPPORTED_REGIONS,
    config_for_region,
    merge_region_config,
    region_database_url,
    region_labels,
)

ACCENT = "#3498db"
ACCENT_HOVER = "#2980b9"
BG = "#f4f6f8"
TEXT = "#2c3e50"
MUTED = "#7f8c8d"


def _region_combo_label(region_id: str) -> str:
    for rid, label in region_labels():
        if rid == region_id:
            return f"{rid.upper()} {label}"
    return region_id.upper()


def _open_folder(path: str) -> None:
    folder = os.path.abspath(path)
    if not os.path.isdir(folder):
        os.makedirs(folder, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(folder)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", folder], check=False)
    else:
        subprocess.run(["xdg-open", folder], check=False)


class DisplayGrabberApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Display / 周销量 — 多区域抓取")
        self.root.geometry("860x720")
        self.root.minsize(760, 640)
        self.root.configure(bg=BG)

        self._running = False
        self._stop_flag = False
        self._schedule_after_id: str | None = None
        self._next_run: datetime | None = None

        self._run_vars: dict[str, tk.BooleanVar] = {
            rid: tk.BooleanVar(value=(rid == "nz")) for rid in SUPPORTED_REGIONS
        }
        self._edit_region_var = tk.StringVar(value="nz")
        self._region_fields: dict[str, dict[str, str]] = {}

        self._build_ui()
        self._load_fields()
        self._log_region_paths()

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 6}
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Accent.TButton", foreground="white", background=ACCENT)
        style.map("Accent.TButton", background=[("active", ACCENT_HOVER)])

        run_frame = ttk.LabelFrame(
            self.root,
            text="本次要跑的地区（可多选，一次执行）",
            padding=10,
        )
        run_frame.pack(fill="x", padx=12, pady=(12, 6))
        row = ttk.Frame(run_frame)
        row.pack(anchor="w")
        for rid, label in region_labels():
            ttk.Checkbutton(row, text=label, variable=self._run_vars[rid]).pack(
                side="left", padx=(0, 18)
            )

        cfg_frame = ttk.LabelFrame(
            self.root,
            text="地区配置（每个地区独立连接串 / SQL 模板目录 / 输出目录）",
            padding=10,
        )
        cfg_frame.pack(fill="x", padx=12, pady=(0, 6))

        ttk.Label(cfg_frame, text="正在编辑").grid(row=0, column=0, sticky="w", **pad)
        edit_values = [_region_combo_label(rid) for rid in SUPPORTED_REGIONS]
        self._edit_combo = ttk.Combobox(
            cfg_frame,
            values=edit_values,
            state="readonly",
            width=18,
        )
        self._edit_combo.grid(row=0, column=1, sticky="w", padx=8, pady=6)
        self._edit_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_edit_region_changed())

        ttk.Label(cfg_frame, text="数据库连接").grid(row=1, column=0, sticky="nw", **pad)
        db_row = ttk.Frame(cfg_frame)
        db_row.grid(row=1, column=1, columnspan=2, sticky="ew", padx=8, pady=6)
        self.db_entry = tk.Text(db_row, height=2, width=80, wrap="word")
        self.db_entry.pack(fill="x", expand=True)
        ttk.Button(db_row, text="测试连接", command=self.test_connection).pack(anchor="e", pady=(6, 0))

        ttk.Label(cfg_frame, text="SQL 模板目录").grid(row=2, column=0, sticky="w", **pad)
        self.sql_folder_var = tk.StringVar(value="sql/nz")
        ttk.Entry(cfg_frame, textvariable=self.sql_folder_var, width=60).grid(
            row=2, column=1, sticky="ew", padx=8, pady=6
        )
        ttk.Button(cfg_frame, text="浏览...", command=self._browse_sql).grid(row=2, column=2, padx=4)

        ttk.Label(cfg_frame, text="输出文件夹").grid(row=3, column=0, sticky="w", **pad)
        self.output_folder_var = tk.StringVar(value="data/nz")
        ttk.Entry(cfg_frame, textvariable=self.output_folder_var, width=60).grid(
            row=3, column=1, sticky="ew", padx=8, pady=6
        )
        out_btns = ttk.Frame(cfg_frame)
        out_btns.grid(row=3, column=2, padx=4)
        ttk.Button(out_btns, text="浏览...", command=self._browse_output).pack(side="left")
        ttk.Button(out_btns, text="打开", command=self._open_output).pack(side="left", padx=(4, 0))

        hint = (
            "结构：sql/{region}/display.sql → data/{region}/display.xlsx；"
            "周销量 → data/{region}/weekly_sales.xlsx；布局 → data/{region}/layouts/。"
            "程序只认区域目录，请把旧 data/*.xlsx 移到 data/nz/ 等再抓取。"
        )
        ttk.Label(cfg_frame, text=hint, foreground=MUTED, wraplength=760).grid(
            row=4, column=0, columnspan=3, sticky="w", padx=10, pady=(0, 4)
        )
        cfg_frame.columnconfigure(1, weight=1)

        grab_opts = ttk.LabelFrame(self.root, text="抓取选项", padding=10)
        grab_opts.pack(fill="x", padx=12, pady=(0, 6))
        self.grab_sales_var = tk.BooleanVar(value=True)
        self.sync_roi_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            grab_opts,
            text="同时抓取周销量（weekly_sales.xlsx）",
            variable=self.grab_sales_var,
        ).pack(anchor="w")
        ttk.Checkbutton(
            grab_opts,
            text="抓取后同步 ROI 到家具模板与门店布局（较慢，建议按需勾选）",
            variable=self.sync_roi_var,
        ).pack(anchor="w", pady=(4, 0))

        sched_frame = ttk.LabelFrame(self.root, text="自动调度设置", padding=10)
        sched_frame.pack(fill="x", padx=12, pady=6)

        ttk.Label(sched_frame, text="执行频率").grid(row=0, column=0, sticky="w", padx=8)
        self.interval_var = tk.IntVar(value=30)
        ttk.Spinbox(sched_frame, from_=1, to=9999, textvariable=self.interval_var, width=8).grid(
            row=0, column=1, sticky="w", padx=4
        )
        self.unit_var = tk.StringVar(value="分钟")
        ttk.Combobox(
            sched_frame,
            textvariable=self.unit_var,
            values=["分钟", "小时"],
            state="readonly",
            width=8,
        ).grid(row=0, column=2, sticky="w", padx=4)

        self.next_run_var = tk.StringVar(value="下次执行: 未调度")
        ttk.Label(sched_frame, textvariable=self.next_run_var, foreground=MUTED).grid(
            row=0, column=3, sticky="w", padx=20
        )
        self.status_var = tk.StringVar(value="● 就绪")
        ttk.Label(sched_frame, textvariable=self.status_var, foreground="#27ae60").grid(
            row=0, column=4, sticky="e", padx=8
        )

        btn_frame = ttk.Frame(self.root, padding=(12, 4))
        btn_frame.pack(fill="x")
        ttk.Button(btn_frame, text="立即执行一次", style="Accent.TButton", command=self.run_once).pack(
            side="left", padx=4
        )
        ttk.Button(btn_frame, text="▶ 开始自动调度", style="Accent.TButton", command=self.start_schedule).pack(
            side="left", padx=4
        )
        self.stop_btn = ttk.Button(btn_frame, text="■ 停止当前任务", command=self.stop_task, state="disabled")
        self.stop_btn.pack(side="left", padx=4)
        ttk.Button(btn_frame, text="保存配置", command=self.save_config).pack(side="left", padx=4)
        self.tray_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(btn_frame, text="关闭时最小化到托盘", variable=self.tray_var).pack(side="right", padx=8)

        prog_frame = ttk.Frame(self.root, padding=(12, 4))
        prog_frame.pack(fill="x")
        ttk.Label(prog_frame, text="总进度").pack(anchor="w")
        self.progress = ttk.Progressbar(prog_frame, maximum=100)
        self.progress.pack(fill="x", pady=4)
        self.sku_var = tk.StringVar(value="Display: -")
        ttk.Label(prog_frame, textvariable=self.sku_var, foreground=MUTED).pack(anchor="w")

        log_frame = ttk.LabelFrame(self.root, text="执行日志", padding=8)
        log_frame.pack(fill="both", expand=True, padx=12, pady=(6, 12))
        self.log_text = scrolledtext.ScrolledText(
            log_frame, height=12, bg="#111827", fg="#e5e7eb", insertbackground="white", font=("Consolas", 10)
        )
        self.log_text.pack(fill="both", expand=True)
        log_btns = ttk.Frame(log_frame)
        log_btns.pack(fill="x", pady=(6, 0))
        ttk.Button(log_btns, text="清空日志", command=self.clear_log).pack(side="left", padx=4)
        ttk.Button(log_btns, text="导出日志", command=self.export_log).pack(side="left", padx=4)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def log(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"

        def append() -> None:
            self.log_text.insert("end", line)
            self.log_text.see("end")

        self.root.after(0, append)

    def _edit_region_id(self) -> str:
        text = self._edit_combo.get().strip()
        if not text:
            return "nz"
        return text.split()[0].lower()

    def _set_edit_region(self, region_id: str) -> None:
        self._edit_combo.set(_region_combo_label(region_id))
        self._edit_region_var.set(region_id)

    def _flush_editor(self) -> None:
        rid = self._edit_region_id()
        self._region_fields[rid] = {
            "database_url": self.db_entry.get("1.0", "end").strip(),
            "sql_folder": self.sql_folder_var.get().strip(),
            "output_folder": self.output_folder_var.get().strip(),
        }

    def _load_editor(self, region_id: str) -> None:
        fields = self._region_fields.get(region_id, {})
        runtime = merge_region_config(
            {"regions": {region_id: fields}, "active_region": region_id},
            region_id,
        )
        self.db_entry.delete("1.0", "end")
        db = fields.get("database_url") or region_database_url(
            {"regions": {region_id: fields}}, region_id
        )
        self.db_entry.insert("1.0", db)
        self.sql_folder_var.set(fields.get("sql_folder") or runtime.get("sql_folder") or f"sql/{region_id}")
        self.output_folder_var.set(
            fields.get("output_folder") or runtime.get("output_folder") or f"data/{region_id}"
        )

    def _on_edit_region_changed(self) -> None:
        self._flush_editor()
        rid = self._edit_region_id()
        self._set_edit_region(rid)
        self._load_editor(rid)

    def _load_region_fields_from_cfg(self, cfg: dict) -> None:
        regions = cfg.get("regions") or {}
        active = get_active_from_cfg(cfg)
        for rid in SUPPORTED_REGIONS:
            section = dict(regions.get(rid) or {})
            runtime = merge_region_config({**cfg, "active_region": rid}, rid)
            db_url = section.get("database_url") or ""
            if not db_url and rid == active:
                db_url = cfg.get("database_url", "")
            self._region_fields[rid] = {
                "database_url": db_url,
                "sql_folder": section.get("sql_folder") or runtime.get("sql_folder", f"sql/{rid}"),
                "output_folder": section.get("output_folder") or runtime.get("output_folder", f"data/{rid}"),
            }

        run_list = cfg.get("run_regions") or [get_active_from_cfg(cfg)]
        for rid in SUPPORTED_REGIONS:
            self._run_vars[rid].set(rid in run_list)

    def _load_fields(self) -> None:
        cfg = load_grabber_config()
        self._load_region_fields_from_cfg(cfg)
        edit_rid = get_active_from_cfg(cfg)
        self._set_edit_region(edit_rid)
        self._load_editor(edit_rid)
        self.interval_var.set(int(cfg.get("schedule_interval", 30)))
        self.unit_var.set(cfg.get("schedule_unit", "分钟"))
        self.tray_var.set(bool(cfg.get("minimize_to_tray", False)))
        self.grab_sales_var.set(bool(cfg.get("grab_sales_with_display", True)))
        self.sync_roi_var.set(bool(cfg.get("sync_roi_after_grab", False)))
        self.log("应用程序已启动。勾选地区后点「立即执行一次」，或设置频率后「开始自动调度」。")

    def _log_region_paths(self) -> None:
        cfg = self._collect_config(save_editor=False)
        for rid, label in region_labels():
            rt = merge_region_config(config_for_region(cfg, rid), rid)
            sql_dir = os.path.abspath(os.path.join(SCRIPT_DIR, rt.get("sql_folder", f"sql/{rid}")))
            out_dir = os.path.abspath(os.path.join(SCRIPT_DIR, rt.get("output_folder", f"data/{rid}")))
            self.log(f"{label} SQL 模板: {sql_dir}")
            self.log(f"{label} 输出目录: {out_dir}")

    def _selected_regions(self) -> list[str]:
        return [rid for rid in SUPPORTED_REGIONS if self._run_vars[rid].get()]

    def _collect_config(self, *, save_editor: bool = True) -> dict:
        if save_editor:
            self._flush_editor()
        cfg = load_grabber_config()
        regions: dict[str, dict] = dict(cfg.get("regions") or {})
        for rid in SUPPORTED_REGIONS:
            fields = self._region_fields.get(rid, {})
            section = dict(regions.get(rid) or {})
            for key in ("database_url", "sql_folder", "output_folder"):
                if fields.get(key):
                    section[key] = fields[key]
            regions[rid] = section

        active = self._edit_region_id()
        collected = {
            **cfg,
            "active_region": active,
            "run_regions": self._selected_regions() or [active],
            "regions": regions,
            "schedule_interval": int(self.interval_var.get()),
            "schedule_unit": self.unit_var.get(),
            "minimize_to_tray": bool(self.tray_var.get()),
            "grab_sales_with_display": bool(self.grab_sales_var.get()),
            "sync_roi_after_grab": bool(self.sync_roi_var.get()),
        }
        section = regions.get(active, {})
        if section.get("database_url"):
            collected["database_url"] = section["database_url"]
        if section.get("sql_folder"):
            collected["sql_folder"] = section["sql_folder"]
        if section.get("output_folder"):
            collected["output_folder"] = section["output_folder"]
        reload_shops(collected)
        return collected

    def test_connection(self) -> None:
        self._flush_editor()
        rid = self._edit_region_id()
        cfg = self._collect_config()
        region_cfg = config_for_region(cfg, rid)
        self.log(f"正在测试 {rid.upper()} 数据库连接...")
        threading.Thread(
            target=lambda: self._test_connection_job(region_cfg, rid),
            daemon=True,
        ).start()

    def _test_connection_job(self, cfg: dict, region_id: str) -> None:
        ok, msg = test_database_connection(cfg)
        title = f"{region_id.upper()} 连接测试"
        if ok:
            self.log(msg)
            self.root.after(0, lambda: messagebox.showinfo(title, msg))
        else:
            self.log(f"连接失败: {msg}")
            self.root.after(0, lambda: messagebox.showerror(title, msg))

    def save_config(self) -> None:
        cfg = self._collect_config()
        save_grabber_config(cfg)
        self.log(f"配置已保存 → {GRABBER_CONFIG}")
        messagebox.showinfo("保存成功", "各地区连接串与目录已保存")

    def _browse_sql(self) -> None:
        path = filedialog.askdirectory(initialdir=SCRIPT_DIR, title="选择 SQL 模板目录")
        if path:
            rel = os.path.relpath(path, SCRIPT_DIR)
            self.sql_folder_var.set(rel if not rel.startswith("..") else path)

    def _browse_output(self) -> None:
        path = filedialog.askdirectory(initialdir=SCRIPT_DIR, title="选择输出文件夹")
        if path:
            rel = os.path.relpath(path, SCRIPT_DIR)
            self.output_folder_var.set(rel if not rel.startswith("..") else path)

    def _open_output(self) -> None:
        folder = self.output_folder_var.get().strip()
        if not folder:
            return
        path = folder if os.path.isabs(folder) else os.path.join(SCRIPT_DIR, folder)
        try:
            _open_folder(path)
        except Exception as exc:
            messagebox.showerror("打开失败", str(exc))

    def _interval_seconds(self) -> int:
        n = max(1, int(self.interval_var.get()))
        if self.unit_var.get() == "小时":
            return n * 3600
        return n * 60

    def run_once(self) -> None:
        if self._running:
            messagebox.showwarning("忙碌", "任务正在执行中")
            return
        selected = self._selected_regions()
        if not selected:
            messagebox.showwarning("未选择", "请至少勾选一个地区。")
            return
        self.save_config()
        threading.Thread(target=self._run_job, args=(selected,), daemon=True).start()

    def _run_job(self, selected: list[str]) -> None:
        self._running = True
        self._stop_flag = False
        self.root.after(0, lambda: self.stop_btn.configure(state="normal"))
        self.root.after(0, lambda: self.status_var.set("● 执行中"))
        self.root.after(0, lambda: self.progress.configure(value=5))

        cfg = self._collect_config()
        total_regions = len(selected)
        summary: list[str] = []

        try:
            for idx, region_id in enumerate(selected):
                if self._stop_flag:
                    raise InterruptedError("用户停止")

                region_cfg = config_for_region(cfg, region_id)
                label = region_cfg.get("_region_label", region_id)
                self.log(f"════ {label} ({region_id.upper()}) ════")
                runtime = build_runtime_config(region_cfg)
                self.log(f"SQL 目录: {runtime.get('sql_folder')}")
                self.log(f"Display SQL: {runtime['sql_file']}")
                if cfg.get("grab_sales_with_display"):
                    self.log(f"周销量 SQL: {region_cfg.get('sales_sql_file')}")
                self.log(f"输出目录: {runtime.get('output_folder')}")

                base_progress = int(100 * idx / total_regions)
                self.root.after(0, lambda v=base_progress + 10: self.progress.configure(value=v))

                results = run_grab_pipeline(
                    region_cfg,
                    display=True,
                    sales=bool(cfg.get("grab_sales_with_display")),
                    sync_roi=bool(cfg.get("sync_roi_after_grab")) and idx == 0,
                    log=self.log,
                )

                display_result = results.get("display", {})
                items = display_result.get("items") or []
                excel_path = display_result.get("excel", runtime["output_excel"])
                used_sql = last_sql_file() or runtime["sql_file"]
                self.log(f"使用 SQL: {os.path.basename(used_sql)}")
                stats = shop_stats(items, [])
                total = stats.get("all", {}).get("total", len(items))
                self.log(f"Display 完成: {total} 款 → {excel_path}")

                sales_result = results.get("sales")
                if sales_result:
                    self.log(
                        f"周销量完成: {sales_result.get('count', 0)} 行 → {sales_result.get('excel')}"
                    )
                    summary.append(f"{region_id.upper()} 销量 {sales_result.get('count', 0)} 行")
                summary.insert(0, f"{region_id.upper()} Display {total} 款")

                self.root.after(
                    0,
                    lambda v=int(100 * (idx + 1) / total_regions): self.progress.configure(value=v),
                )

            self.root.after(0, lambda: self.progress.configure(value=100))
            self.root.after(0, lambda: self.status_var.set("● 就绪"))
            self.root.after(0, lambda: self.sku_var.set(" · ".join(summary)))
            self.log("全部地区抓取完成。")
        except InterruptedError as exc:
            self.log(str(exc))
            self.root.after(0, lambda: self.status_var.set("● 已停止"))
        except Exception as exc:
            self.log(f"失败: {exc}")
            self.log(traceback.format_exc())
            self.root.after(0, lambda: self.status_var.set("● 失败"))
            self.root.after(0, lambda: messagebox.showerror("抓取失败", str(exc)))
        finally:
            self._running = False
            self.root.after(0, lambda: self.stop_btn.configure(state="disabled"))
            self.root.after(0, lambda: self.progress.configure(value=0))

    def stop_task(self) -> None:
        self._stop_flag = True
        self.log("正在停止...")
        if self._schedule_after_id:
            self.root.after_cancel(self._schedule_after_id)
            self._schedule_after_id = None
            self._next_run = None
            self.next_run_var.set("下次执行: 未调度")

    def start_schedule(self) -> None:
        if self._schedule_after_id:
            messagebox.showinfo("提示", "自动调度已在运行")
            return
        if not self._selected_regions():
            messagebox.showwarning("未选择", "请至少勾选一个地区。")
            return
        self.save_config()
        self._schedule_next()
        self.log(f"自动调度已启动，每 {self.interval_var.get()} {self.unit_var.get()}")

    def _schedule_next(self) -> None:
        secs = self._interval_seconds()
        self._next_run = datetime.now() + timedelta(seconds=secs)
        self.next_run_var.set(f"下次执行: {self._next_run.strftime('%H:%M:%S')}")
        self._schedule_after_id = self.root.after(secs * 1000, self._scheduled_tick)

    def _scheduled_tick(self) -> None:
        self._schedule_after_id = None
        if not self._running:
            selected = self._selected_regions()
            if selected:
                threading.Thread(target=self._run_job, args=(selected,), daemon=True).start()
        self._schedule_next()

    def clear_log(self) -> None:
        self.log_text.delete("1.0", "end")

    def export_log(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("文本", "*.txt")],
            initialfile=f"display_grab_log_{datetime.now():%Y%m%d_%H%M%S}.txt",
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.log_text.get("1.0", "end"))
            self.log(f"日志已导出: {path}")

    def _on_close(self) -> None:
        if self.tray_var.get():
            self.root.withdraw()
            self.log("已最小化到后台（再次启动程序可恢复窗口）")
            return
        self.stop_task()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def get_active_from_cfg(cfg: dict) -> str:
    from region_config import get_active_region

    return get_active_region(cfg)


def main() -> int:
    try:
        DisplayGrabberApp().run()
    except Exception as exc:
        print(exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
