#!/usr/bin/env python3
"""产品库存 + 价格抓取：sql/product_stock_price.sql → data/product_stock_price.xlsx"""
from __future__ import annotations

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from display_lookup import grab_sql_to_excel, last_load_error, load_grabber_config
from stock_price_lookup import DEFAULT_EXCEL, STOCK_PRICE_SQL, reload_stock_prices


def main() -> int:
    print("=" * 50)
    print("产品库存 + UnitPrice / SalePrice 抓取")
    print("=" * 50)
    print(f"目录: {os.getcwd()}\n")

    base = load_grabber_config()
    cfg = {
        **base,
        "sql_file": base.get("stock_price_sql_file") or STOCK_PRICE_SQL,
        "output_excel": base.get("stock_price_output_excel") or DEFAULT_EXCEL,
    }

    try:
        rows, excel_path = grab_sql_to_excel(cfg)
    except Exception as exc:
        print(f"抓取失败: {exc}")
        if last_load_error():
            print(last_load_error())
        print("\n请检查 grabber_config.json 与 sql/product_stock_price.sql")
        return 1

    cache = reload_stock_prices(excel_path)
    promo_n = sum(1 for r in cache.values() if r.on_promotion)
    print(f"已写入: {excel_path}")
    print(f"共 {len(rows)} 行 · {len(cache)} 个 SKU · 促销中 {promo_n} 个")
    print("\n下一步:")
    print("  python layout.py    # 侧栏家具模板会显示价格/库存")
    print("  SSMS 里改 @SkuFilter 可只查某个系列")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
