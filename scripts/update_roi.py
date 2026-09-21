#!/usr/bin/env python3
"""从 roi.xlsx / weekly_sales.xlsx 同步 ROI 到 furniture_templates.json 与门店布局。

模板 id 多为 SKU（如 830-029），会先映射到 ProductFamily 再查 ROI。
画布上已摆放的家具 ROI 保存在 data/layouts/*.json，本脚本会一并更新。
"""
from __future__ import annotations

import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from roi_lookup import lookup_roi, reload_roi_map, resolve_furniture_roi
from sales_lookup import reload_weekly_sales, resolve_product_family

LAYOUTS_DIR = os.path.join(SCRIPT_DIR, "data", "layouts")


def update_templates() -> tuple[int, int]:
    with open("furniture_templates.json", "r", encoding="utf-8") as f:
        furniture_data = json.load(f)

    updated = 0
    missing = 0
    for item in furniture_data:
        raw = (item.get("product_family") or item.get("id") or "").strip()
        family = resolve_product_family(raw)
        item["product_family"] = family
        roi = lookup_roi(family or raw)
        item["roi"] = round(float(roi), 2)
        if roi > 0:
            updated += 1
        else:
            missing += 1
            print(f"未找到 ROI：{raw}" + (f" → {family}" if family != raw else ""))

    with open("furniture_templates.json", "w", encoding="utf-8") as f:
        json.dump(furniture_data, f, ensure_ascii=False, indent=2)

    return updated, missing


def update_layout_files() -> tuple[int, int]:
    if not os.path.isdir(LAYOUTS_DIR):
        return 0, 0

    layout_updated = 0
    layout_missing = 0
    for fname in sorted(os.listdir(LAYOUTS_DIR)):
        if not fname.endswith(".json") or fname.startswith("_"):
            continue
        path = os.path.join(LAYOUTS_DIR, fname)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        furnitures = data.get("furnitures") or []
        if not furnitures:
            continue

        store_slug = data.get("store_slug") or os.path.splitext(fname)[0]
        changed = False
        for item in furnitures:
            name = (item.get("name") or "").strip()
            family, roi = resolve_furniture_roi(
                name,
                item.get("product_family", "") or "",
                store_slug,
            )
            if family:
                item["product_family"] = family
            new_roi = round(float(roi), 2)
            if item.get("roi") != new_roi:
                changed = True
            item["roi"] = new_roi
            if new_roi > 0:
                layout_updated += 1
            else:
                layout_missing += 1
                print(f"布局 {fname} 未找到 ROI：{name}" + (f" → {family}" if family != name else ""))

        if changed:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    return layout_updated, layout_missing


def main() -> int:
    reload_roi_map()
    reload_weekly_sales()

    tpl_ok, tpl_miss = update_templates()
    print(f"模板 ROI：{tpl_ok} 个有值，{tpl_miss} 个为 0")

    lay_ok, lay_miss = update_layout_files()
    if lay_ok or lay_miss:
        print(f"布局 ROI：{lay_ok} 个有值，{lay_miss} 个为 0")

    print("ROI 同步完成。请重启 layout.py 查看颜色。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
