#!/usr/bin/env python3
"""周销量抓取：读 sql/weekly_sales.sql + grabber_config.json → data/weekly_sales.xlsx

与 grab_display 共用数据库连接，但输出独立 Excel，供 ROI / 坪效使用。
"""
from __future__ import annotations

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from display_lookup import grab_sql_to_excel, last_load_error, load_grabber_config, sales_runtime_config
from region_config import SUPPORTED_REGIONS, get_active_region
from sales_lookup import reload_weekly_sales


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="周销量数据抓取")
    parser.add_argument(
        "--region",
        choices=list(SUPPORTED_REGIONS),
        help="国家/区域：nz / au / ca",
    )
    args = parser.parse_args()

    base = load_grabber_config()
    if args.region:
        base = {**base, "active_region": args.region}
    cfg = sales_runtime_config(base)
    region = get_active_region(base)

    print("=" * 50)
    print(f"周销量数据抓取 — {cfg.get('_region_label', region)}")
    print("=" * 50)
    print(f"目录: {os.getcwd()}")
    print(f"区域: {region} → {cfg.get('output_excel')}\n")

    try:
        rows, excel_path = grab_sql_to_excel(cfg)
    except Exception as exc:
        print(f"抓取失败: {exc}")
        if last_load_error():
            print(last_load_error())
        print("\n请检查:")
        print("  1. grabber_config.json 中 database_url 是否正确")
        print("  2. sql/weekly_sales.sql 表名/列名是否与线上一致")
        print("  3. pip install sqlalchemy pymssql openpyxl pandas")
        return 1

    reload_weekly_sales(excel_path)
    loaded = reload_weekly_sales(excel_path)
    families = {r.product_family for r in loaded if r.product_family}
    branches = {r.branch_name for r in loaded if r.branch_name}
    print(f"已写入: {excel_path}")
    print(f"共 {len(rows)} 行 · {len(branches)} 门店 · {len(families)} 个 ProductFamily")
    print("\n下一步:")
    print("  python scripts/update_roi.py   # 把销量 ROI 同步到 furniture_templates.json")
    print("  python layout.py               # 布局编辑器按 ROI 着色")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
