import json

import pandas as pd

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
