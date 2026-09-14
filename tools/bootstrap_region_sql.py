#!/usr/bin/env python3
"""为 sql/nz、sql/au、sql/ca 补齐 display / weekly_sales / product_stock_price SQL 文件。

若某区域目录缺失，从 sql/nz/ 或根目录 sql/ 复制模板（不覆盖已有文件）。
程序也支持同名的 .txt（如 display.txt、weekly_sales.txt）。
"""
from __future__ import annotations

import os
import shutil

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQL_ROOT = os.path.join(SCRIPT_DIR, "sql")
REGIONS = ("nz", "au", "ca")
NAMES = (
    "display.sql",
    "display.minimal.sql",
    "weekly_sales.sql",
    "product_stock_price.sql",
)


def _first_source(name: str) -> str | None:
    candidates = [
        os.path.join(SQL_ROOT, "nz", name),
        os.path.join(SQL_ROOT, name),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def main() -> int:
    copied = 0
    for region in REGIONS:
        target_dir = os.path.join(SQL_ROOT, region)
        os.makedirs(target_dir, exist_ok=True)
        for name in NAMES:
            dst = os.path.join(target_dir, name)
            if os.path.isfile(dst):
                continue
            src = _first_source(name)
            if not src:
                print(f"跳过 {region}/{name}：找不到模板")
                continue
            shutil.copy2(src, dst)
            print(f"创建: sql/{region}/{name} ← {os.path.relpath(src, SCRIPT_DIR)}")
            copied += 1
    if copied:
        print(f"\n完成，新建 {copied} 个文件。加拿大/澳洲库存 SQL 中的仓库名可能仍需按当地 ERP 修改。")
    else:
        print("各区域 SQL 已齐全，无需复制。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
