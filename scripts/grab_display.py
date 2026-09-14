#!/usr/bin/env python3
"""Main 抓数据：读 sql/ + grabber_config.json → 写入 data/display.xlsx

和库存项目一样：
  grab_display.bat  → 抓数据（本脚本）
  start_furniture_sim.bat → 可视化（furniture_sim.py 读 data/display.xlsx）
"""
from __future__ import annotations

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from display_lookup import grab_and_save, last_load_error, load_grabber_config, shop_stats
from region_config import SUPPORTED_REGIONS, get_active_region, merge_region_config


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Display 数据抓取")
    parser.add_argument(
        "--region",
        choices=list(SUPPORTED_REGIONS),
        help="国家/区域：nz / au / ca（默认 grabber_config.json 的 active_region）",
    )
    args = parser.parse_args()

    cfg = load_grabber_config()
    if args.region:
        cfg = {**cfg, "active_region": args.region}
    runtime = merge_region_config(cfg)
    region = get_active_region(cfg)

    print("=" * 50)
    print(f"Display 数据抓取 — {runtime.get('_region_label', region)}")
    print("=" * 50)
    print(f"目录: {os.getcwd()}")
    print(f"区域: {region} → {runtime.get('output_folder')}\n")

    try:
        items, excel_path = grab_and_save(cfg)
    except Exception as exc:
        print(f"抓取失败: {exc}")
        if last_load_error():
            print(last_load_error())
        print("\n请检查:")
        print("  1. grabber_config.json 是否存在且 database_url 正确（可从 main_gui 复制）")
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
    print("\n下一步: 运行 start_furniture_sim.bat 打开 Display 大库")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
