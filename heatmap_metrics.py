"""坪效热力图：按近 N 周销量计算 元/㎡（每平方米销售额）。"""
from __future__ import annotations

import re
from typing import Any

from sales_lookup import (
    DEFAULT_EXCEL,
    _normalize_key,
    load_weekly_sales,
    resolve_product_family,
)

_week_keys_cache: dict[tuple[str | None, int], set[str]] = {}
_amount_cache: dict[tuple[str, str, str | None, int], float] = {}


def _week_key(period: str) -> str:
    text = str(period or "")
    match = re.match(r"(\d{4}-W\d{2})", text)
    return match.group(1) if match else ""


def clear_heatmap_cache() -> None:
    global _week_keys_cache, _amount_cache
    _week_keys_cache = {}
    _amount_cache = {}


def list_recent_week_keys(shop_id: str | None = None, num_weeks: int = 4) -> list[str]:
    num_weeks = max(1, int(num_weeks or 1))
    cache_key = (shop_id, num_weeks)
    if cache_key in _week_keys_cache:
        return sorted(_week_keys_cache[cache_key])

    weeks: set[str] = set()
    for row in load_weekly_sales():
        if shop_id and shop_id not in ("all", "") and row.shop_id != shop_id:
            continue
        wk = _week_key(row.year_week_period)
        if wk:
            weeks.add(wk)
    chosen = sorted(weeks)[-num_weeks:]
    _week_keys_cache[cache_key] = set(chosen)
    return chosen


def lookup_sales_amount(
    sku: str,
    product_family: str = "",
    *,
    shop_id: str | None = None,
    num_weeks: int = 4,
) -> float:
    sku = str(sku or "").strip()
    family = str(product_family or "").strip()
    cache_key = (_normalize_key(sku), _normalize_key(family), shop_id, max(1, int(num_weeks)))
    if cache_key in _amount_cache:
        return _amount_cache[cache_key]

    allowed = set(list_recent_week_keys(shop_id, num_weeks))
    if not allowed:
        _amount_cache[cache_key] = 0.0
        return 0.0

    sku_n = _normalize_key(sku)
    amount = 0.0
    matched_sku = False
    for row in load_weekly_sales():
        if shop_id and shop_id not in ("all", "") and row.shop_id != shop_id:
            continue
        if _week_key(row.year_week_period) not in allowed:
            continue
        if sku_n and _normalize_key(row.sku) == sku_n:
            amount += row.total_amount
            matched_sku = True

    if not matched_sku:
        fam = resolve_product_family(family or sku) or family or sku
        fam_n = _normalize_key(fam)
        for row in load_weekly_sales():
            if shop_id and shop_id not in ("all", "") and row.shop_id != shop_id:
                continue
            if _week_key(row.year_week_period) not in allowed:
                continue
            if fam_n and _normalize_key(row.product_family) == fam_n:
                amount += row.total_amount

    _amount_cache[cache_key] = amount
    return amount


def furniture_area_sqm(area_mm2: float) -> float:
    return max(0.0, float(area_mm2)) / 1_000_000.0


def revenue_per_sqm(
    sales_amount: float,
    area_mm2: float,
) -> float:
    area_sqm = furniture_area_sqm(area_mm2)
    if area_sqm <= 0:
        return 0.0
    return max(0.0, float(sales_amount)) / area_sqm


def format_revenue_per_sqm(value: float) -> str:
    if value <= 0:
        return "—"
    if value >= 1000:
        return f"${value:,.0f}/㎡"
    if value >= 100:
        return f"${value:.0f}/㎡"
    return f"${value:.1f}/㎡"


def revenue_per_sqm_to_color(value: float, vmin: float, vmax: float) -> tuple[int, int, int]:
    """浅 → 深热力色（元/㎡）。"""
    if value <= 0:
        return (245, 245, 245)
    if vmax <= vmin:
        t = 0.65
    else:
        t = (value - vmin) / (vmax - vmin)
    t = max(0.0, min(1.0, t))
    stops = (
        (255, 247, 235),
        (254, 215, 164),
        (251, 146, 60),
        (220, 38, 38),
        (127, 29, 29),
    )
    seg = t * (len(stops) - 1)
    idx = int(seg)
    if idx >= len(stops) - 1:
        return stops[-1]
    frac = seg - idx
    a, b = stops[idx], stops[idx + 1]
    return tuple(int(a[i] + (b[i] - a[i]) * frac) for i in range(3))


def sales_data_ready() -> bool:
    import os

    return os.path.isfile(DEFAULT_EXCEL) and os.path.getsize(DEFAULT_EXCEL) > 0
