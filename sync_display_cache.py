#!/usr/bin/env python3
"""可选：从 MSSQL 直连拉取 Display 并写入 display_cache.json。

推荐工作流（更简单）：
  1. 在 SSMS 运行 display.sql
  2. 结果 → 另存为 display.xlsx
  3. 启动 start_template，程序自动读 Excel

本脚本仅在你想跳过 Excel、程序直连数据库时用。
"""
from __future__ import annotations

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

from display_lookup import grab_and_save, last_load_error, shop_stats


def main() -> int:
    try:
        items, excel_path = grab_and_save()
    except Exception as exc:
        print(f"同步失败: {exc}")
        if last_load_error():
            print(last_load_error())
        print("\n请配置 grabber_config.json 并运行 grab_display.bat")
        return 1

    stats = shop_stats(items, [])
    print(f"已写入 {excel_path}，共 {len(items)} 个 Display 产品")
    for sid, s in stats.items():
        if sid == "all":
            continue
        if s["total"]:
            print(f"  {sid}: {s['total']} 款")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
