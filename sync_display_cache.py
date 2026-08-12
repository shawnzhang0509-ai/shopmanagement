#!/usr/bin/env python3
"""从 MSSQL 拉取 Display 库存并写入 display_cache.json。"""
from __future__ import annotations

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

from display_lookup import CACHE_FILE, last_load_error, refresh_from_database, shop_stats


def main() -> int:
    try:
        items = refresh_from_database()
    except Exception as exc:
        print(f"同步失败: {exc}")
        if last_load_error():
            print(last_load_error())
        print("\n请配置 display_config.json（可复制 display_config.example.json）")
        print("或设置环境变量 DISPLAY_DB_URL")
        return 1

    stats = shop_stats(items, [])
    print(f"已写入 {CACHE_FILE}，共 {len(items)} 个 Display 产品")
    for sid, s in stats.items():
        if sid == "all":
            continue
        if s["total"]:
            print(f"  {sid}: {s['total']} 款")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
