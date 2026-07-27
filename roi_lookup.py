"""从 roi.xlsx 按 product_family 查询 ROI。"""
from __future__ import annotations

import os

ROI_FILE = "roi.xlsx"
_roi_cache: dict[str, float] | None = None


def _normalize_key(value) -> str:
    return str(value).strip().lower()


def load_roi_map() -> dict[str, float]:
    global _roi_cache
    if _roi_cache is not None:
        return _roi_cache

    _roi_cache = {}
    if not os.path.isfile(ROI_FILE):
        return _roi_cache

    try:
        import pandas as pd

        df = pd.read_excel(ROI_FILE)
        family_col = None
        for col in ("product_family", "product family", "family", "id"):
            if col in df.columns:
                family_col = col
                break
        if family_col is None or "roi" not in df.columns:
            print(f"roi.xlsx 需要包含 product_family 和 roi 列")
            return _roi_cache

        for _, row in df.iterrows():
            key = _normalize_key(row[family_col])
            roi = row["roi"]
            if key and pd.notna(roi):
                _roi_cache[key] = float(roi)
    except Exception as exc:
        print(f"读取 ROI 表失败: {exc}")

    return _roi_cache


def lookup_roi(product_family: str) -> float:
    if not product_family:
        return 0.0
    return load_roi_map().get(_normalize_key(product_family), 0.0)


def reload_roi_map() -> dict[str, float]:
    global _roi_cache
    _roi_cache = None
    return load_roi_map()
