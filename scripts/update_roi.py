#!/usr/bin/env python3
"""从 roi.xlsx 同步 ROI 到 furniture_templates.json。运行: python scripts/update_roi.py"""
from __future__ import annotations

import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from roi_lookup import lookup_roi, reload_roi_map

reload_roi_map()

with open("furniture_templates.json", "r", encoding="utf-8") as f:
    furniture_data = json.load(f)

for item in furniture_data:
    family = item.get("product_family") or item.get("id", "")
    item["product_family"] = family
    roi = lookup_roi(family)
    if roi:
        item["roi"] = roi
    else:
        print(f"未找到 ROI：{family}")

with open("furniture_templates.json", "w", encoding="utf-8") as f:
    json.dump(furniture_data, f, ensure_ascii=False, indent=2)

print("ROI 已按 product_family 更新完成")
