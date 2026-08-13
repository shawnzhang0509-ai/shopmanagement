#!/usr/bin/env python3
"""Main 抓数据：读 sql/ + grabber_config.json → 写入 data/display.xlsx

和库存项目一样：
  grab_display.bat  → 抓数据（本脚本）
  start_template.bat → 可视化（furniture_sim.py 读 data/display.xlsx）
"""
from __future__ import annotations

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from display_lookup import grab_and_save, last_load_error, shop_stats


def main() -> int:
    print("=" * 50)
    print("Display 数据抓取")
    print("=" * 50)
    print(f"目录: {os.getcwd()}\n")

    try:
        items, excel_path = grab_and_save()
    except Exception as exc:
        print(f"抓取失败: {exc}")
        if last_load_error():
            print(last_load_error())
        print("\n请检查:")
        print("  1. grabber_config.json 是否存在且 db_server/db_user/db_password/db_name 正确")
        print("  2. Azure SQL 防火墙是否放行你的 IP")
        print("  3. pip install sqlalchemy pymssql openpyxl pandas")
        return 1

    stats = shop_stats(items, [])
    print(f"已写入: {excel_path}")
    print(f"共 {len(items)} 款 Display 产品\n")
    for sid, s in stats.items():
        if sid == "all":
            print(f"  全部: {s['modeled']}/{s['total']} 已测绘")
            continue
        if s["total"]:
            print(f"  {sid}: {s['total']} 款")
    print("\n下一步: 运行 start_template.bat 打开 Display 大库")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
