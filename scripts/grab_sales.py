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

from display_lookup import grab_sql_to_excel, last_load_error, load_grabber_config
from sales_lookup import DEFAULT_EXCEL, SALES_SQL, reload_weekly_sales


def main() -> int:
    print("=" * 50)
    print("周销量数据抓取（Branch + ProductFamily）")
    print("=" * 50)
    print(f"目录: {os.getcwd()}\n")

    base = load_grabber_config()
    cfg = {
        **base,
        "sql_file": base.get("sales_sql_file") or SALES_SQL,
        "output_excel": base.get("sales_output_excel") or DEFAULT_EXCEL,
    }

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
