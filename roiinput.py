import json
import pandas as pd

# 读取 Excel
roi_df = pd.read_excel("roi.xlsx")  # 确保文件名正确
roi_dict = dict(zip(roi_df['id'], roi_df['roi']))

# 读取你的 furniture_templates.json
with open("furniture_templates.json", "r") as f:
    furniture_data = json.load(f)

# 插入 ROI
for item in furniture_data:
    item_id = item.get("id")
    if item_id in roi_dict:
        try:
            item["roi"] = float(roi_dict[item_id])
        except Exception as e:
            print(f"处理 ROI 时出错（ID: {item_id}）: {e}")
    else:
        print(f"未找到 ROI：{item_id}")

# 保存新版本 JSON
with open("furniture_templates.json", "w") as f:
    json.dump(furniture_data, f, indent=2)
