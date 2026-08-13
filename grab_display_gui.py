#!/usr/bin/env python3
"""Display 数据自动抓取工具 — GUI（类似库存 main_gui）。"""
from __future__ import annotations

import json
import os
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
    grab_and_save,
    load_grabber_config,
    save_grabber_config,
    shop_stats,
)

ACCENT = "#3498db"
ACCENT_HOVER = "#2980b9"
BG = "#f4f6f8"
TEXT = "#2c3e50"
MUTED = "#7f8c8d"


class DisplayGrabberApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Display 数据自动抓取工具")
        self.root.geometry("820x640")
        self.root.minsize(720, 560)
        self.root.configure(bg=BG)

        self._running = False
        self._stop_flag = False
        self._schedule_after_id: str | None = None
        self._next_run: datetime | None = None

        self._build_ui()
        self._load_fields()
        self.log("应用程序已启动。点击「立即执行一次」手动运行，或设置频率后点击「开始自动调度」。")

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 6}
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Accent.TButton", foreground="white", background=ACCENT)
        style.map("Accent.TButton", background=[("active", ACCENT_HOVER)])

        # ── 基本配置 ──
        cfg_frame = ttk.LabelFrame(self.root, text="基本配置", padding=10)
        cfg_frame.pack(fill="x", padx=12, pady=(12, 6))

        ttk.Label(cfg_frame, text="数据库连接").grid(row=0, column=0, sticky="nw", **pad)
        self.db_var = tk.StringVar()
        self.db_entry = tk.Text(cfg_frame, height=2, width=80, wrap="word")
        self.db_entry.grid(row=0, column=1, columnspan=2, sticky="ew", padx=8, pady=6)

        ttk.Label(cfg_frame, text="SQL 文件夹").grid(row=1, column=0, sticky="w", **pad)
        self.sql_folder_var = tk.StringVar(value="sql")
        ttk.Entry(cfg_frame, textvariable=self.sql_folder_var, width=60).grid(
            row=1, column=1, sticky="ew", padx=8, pady=6
        )
        ttk.Button(cfg_frame, text="浏览...", command=self._browse_sql).grid(row=1, column=2, padx=4)

        ttk.Label(cfg_frame, text="输出文件夹").grid(row=2, column=0, sticky="w", **pad)
        self.output_folder_var = tk.StringVar(value="data")
        ttk.Entry(cfg_frame, textvariable=self.output_folder_var, width=60).grid(
            row=2, column=1, sticky="ew", padx=8, pady=6
        )
        ttk.Button(cfg_frame, text="浏览...", command=self._browse_output).grid(row=2, column=2, padx=4)
        cfg_frame.columnconfigure(1, weight=1)

        # ── 自动调度 ──
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

        # ── 控制按钮 ──
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

        # ── 进度 ──
        prog_frame = ttk.Frame(self.root, padding=(12, 4))
        prog_frame.pack(fill="x")
        ttk.Label(prog_frame, text="总进度").pack(anchor="w")
        self.progress = ttk.Progressbar(prog_frame, maximum=100)
        self.progress.pack(fill="x", pady=4)
        self.sku_var = tk.StringVar(value="Display: -")
        ttk.Label(prog_frame, textvariable=self.sku_var, foreground=MUTED).pack(anchor="w")

        # ── 日志 ──
        log_frame = ttk.LabelFrame(self.root, text="执行日志", padding=8)
        log_frame.pack(fill="both", expand=True, padx=12, pady=(6, 12))
        self.log_text = scrolledtext.ScrolledText(
            log_frame, height=14, bg="#111827", fg="#e5e7eb", insertbackground="white", font=("Consolas", 10)
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

    def _load_fields(self) -> None:
        cfg = load_grabber_config()
        self.db_entry.delete("1.0", "end")
        self.db_entry.insert("1.0", cfg.get("database_url", ""))
        self.sql_folder_var.set(cfg.get("sql_folder", "sql"))
        self.output_folder_var.set(cfg.get("output_folder", "data"))
        self.interval_var.set(int(cfg.get("schedule_interval", 30)))
        self.unit_var.set(cfg.get("schedule_unit", "分钟"))
        self.tray_var.set(bool(cfg.get("minimize_to_tray", False)))

    def _collect_config(self) -> dict:
        return {
            "database_url": self.db_entry.get("1.0", "end").strip(),
            "sql_folder": self.sql_folder_var.get().strip() or "sql",
            "output_folder": self.output_folder_var.get().strip() or "data",
            "schedule_interval": int(self.interval_var.get()),
            "schedule_unit": self.unit_var.get(),
            "minimize_to_tray": bool(self.tray_var.get()),
        }

    def save_config(self) -> None:
        cfg = self._collect_config()
        runtime = build_runtime_config(cfg)
        save_cfg = {
            **cfg,
            "sql_file": os.path.relpath(runtime["sql_file"], SCRIPT_DIR),
            "output_excel": os.path.relpath(runtime["output_excel"], SCRIPT_DIR),
            "output_json": os.path.relpath(runtime["output_json"], SCRIPT_DIR),
        }
        save_grabber_config(save_cfg)
        self.log(f"配置已保存 → {GRABBER_CONFIG}")
        messagebox.showinfo("保存成功", "配置已保存")

    def _browse_sql(self) -> None:
        path = filedialog.askdirectory(initialdir=SCRIPT_DIR, title="选择 SQL 文件夹")
        if path:
            rel = os.path.relpath(path, SCRIPT_DIR)
            self.sql_folder_var.set(rel if not rel.startswith("..") else path)

    def _browse_output(self) -> None:
        path = filedialog.askdirectory(initialdir=SCRIPT_DIR, title="选择输出文件夹")
        if path:
            rel = os.path.relpath(path, SCRIPT_DIR)
            self.output_folder_var.set(rel if not rel.startswith("..") else path)

    def _set_status(self, text: str, color: str = "#27ae60") -> None:
        self.status_var.set(text)
        # ttk Label doesn't easily change color; ok for now

    def _interval_seconds(self) -> int:
        n = max(1, int(self.interval_var.get()))
        if self.unit_var.get() == "小时":
            return n * 3600
        return n * 60

    def run_once(self) -> None:
        if self._running:
            messagebox.showwarning("忙碌", "任务正在执行中")
            return
        self.save_config()
        threading.Thread(target=self._run_job, daemon=True).start()

    def _run_job(self) -> None:
        self._running = True
        self._stop_flag = False
        self.root.after(0, lambda: self.stop_btn.configure(state="normal"))
        self.root.after(0, lambda: self._set_status("● 执行中", "#e67e22"))
        self.root.after(0, lambda: self.progress.configure(value=10))
        self.log("开始抓取 Display 数据...")

        try:
            cfg = self._collect_config()
            runtime = build_runtime_config(cfg)
            self.log(f"SQL: {runtime['sql_file']}")
            self.root.after(0, lambda: self.progress.configure(value=35))
            if self._stop_flag:
                raise InterruptedError("用户停止")

            items, excel_path = grab_and_save(cfg)
            self.root.after(0, lambda: self.progress.configure(value=90))
            stats = shop_stats(items, [])
            total = stats.get("all", {}).get("total", len(items))
            self.log(f"完成: {total} 款 → {excel_path}")
            self.root.after(0, lambda: self.sku_var.set(f"Display: {total} 款"))
            self.root.after(0, lambda: self.progress.configure(value=100))
            self.root.after(0, lambda: self._set_status("● 就绪"))
        except InterruptedError as exc:
            self.log(str(exc))
            self.root.after(0, lambda: self._set_status("● 已停止"))
        except Exception as exc:
            self.log(f"失败: {exc}")
            self.log(traceback.format_exc())
            self.root.after(0, lambda: self._set_status("● 失败", "#e74c3c"))
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
            self.run_once()
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


def main() -> int:
    try:
        DisplayGrabberApp().run()
    except Exception as exc:
        print(exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
