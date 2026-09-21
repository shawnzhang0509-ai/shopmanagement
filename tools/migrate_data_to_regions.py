#!/usr/bin/env python3
"""把旧版扁平 data/ 文件搬到 data/nz/（一次性迁移，不删原文件）。"""
from __future__ import annotations

import os
import shutil

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(SCRIPT_DIR, "data")
TARGET = os.path.join(DATA, "nz")

FILES = (
    "display.xlsx",
    "weekly_sales.xlsx",
    "product_stock_price.xlsx",
    "display_cache.json",
    "display_blacklist.csv",
    "display_blacklist.example.csv",
)


def main() -> int:
    os.makedirs(os.path.join(TARGET, "layouts"), exist_ok=True)
    moved = 0
    for name in FILES:
        src = os.path.join(DATA, name)
        dst = os.path.join(TARGET, name)
        if os.path.isfile(src) and not os.path.isfile(dst):
            shutil.copy2(src, dst)
            print(f"复制: {name} → data/nz/")
            moved += 1
    layouts_src = os.path.join(DATA, "layouts")
    layouts_dst = os.path.join(TARGET, "layouts")
    if os.path.isdir(layouts_src):
        for name in os.listdir(layouts_src):
            s = os.path.join(layouts_src, name)
            d = os.path.join(layouts_dst, name)
            if os.path.isfile(s) and not os.path.exists(d):
                shutil.copy2(s, d)
                print(f"复制布局: layouts/{name} → data/nz/layouts/")
                moved += 1
    if moved:
        print(f"\n完成，共复制 {moved} 项。请在 grabber_config.json 里把 NZ 输出目录设为 data/nz。")
    else:
        print("没有需要迁移的文件（可能已在 data/nz/）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
