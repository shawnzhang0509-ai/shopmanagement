#!/usr/bin/env python3
"""从 roi.xlsx / weekly_sales.xlsx 同步 ROI 到 furniture_templates.json。

模板 id 多为 SKU（如 830-029），会先映射到 ProductFamily 再查 ROI。
"""
from __future__ import annotations

import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from roi_lookup import lookup_roi, reload_roi_map
from sales_lookup import reload_weekly_sales, resolve_product_family

reload_roi_map()
reload_weekly_sales()

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

print(f"ROI 已更新：{updated} 个有值，{missing} 个为 0")
