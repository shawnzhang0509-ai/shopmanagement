"""坪效热力图：按近 N 周销量计算 元/㎡（每平方米销售额）。"""
from __future__ import annotations

import math
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

# 9 档渐变色：蓝 → 青 → 绿 → 黄 → 橙 → 红（差几百块也能分清）
HEATMAP_PALETTE: tuple[tuple[int, int, int], ...] = (
    (235, 245, 255),
    (147, 197, 253),
    (56, 189, 248),
    (52, 211, 153),
    (250, 204, 21),
    (251, 146, 60),
    (248, 113, 113),
    (220, 38, 38),
    (88, 28, 28),
)


def _week_key(period: str) -> str:
    text = str(period or "")
    match = re.match(r"(\d{4}-W\d{2})", text)
    return match.group(1) if match else ""


def clear_heatmap_cache() -> None:
    global _week_keys_cache, _amount_cache
    _week_keys_cache = {}
    _amount_cache = {}


def list_all_week_keys(shop_id: str | None = None) -> list[str]:
    """门店全部有数据的自然周（升序）。"""
    weeks: set[str] = set()
    for row in load_weekly_sales():
        if shop_id and shop_id not in ("all", "") and row.shop_id != shop_id:
            continue
        wk = _week_key(row.year_week_period)
        if wk:
            weeks.add(wk)
    return sorted(weeks)


def week_period_display(shop_id: str | None, week_key: str) -> str:
    for row in load_weekly_sales():
        if shop_id and shop_id not in ("all", "") and row.shop_id != shop_id:
            continue
        if _week_key(row.year_week_period) == week_key:
            return str(row.year_week_period or week_key)
    return week_key


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
    week_keys: list[str] | None = None,
) -> float:
    sku = str(sku or "").strip()
    family = str(product_family or "").strip()
    wk_tuple = tuple(sorted(week_keys)) if week_keys else None
    cache_key = (
        _normalize_key(sku),
        _normalize_key(family),
        shop_id,
        wk_tuple,
        max(1, int(num_weeks)),
    )
    if cache_key in _amount_cache:
        return _amount_cache[cache_key]

    if week_keys:
        allowed = {_week_key(w) or w for w in week_keys}
    else:
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


def adaptive_color_step(vmin: float, vmax: float) -> float:
    """按坪效跨度自动选择分档步长（每档一种主色）。"""
    span = max(0.0, float(vmax) - float(vmin))
    if span <= 0:
        return 200.0
    if span <= 350:
        return 80.0
    if span <= 700:
        return 150.0
    if span <= 1400:
        return 200.0
    if span <= 3000:
        return 300.0
    return 500.0


def heatmap_normalize_t(
    value: float,
    vmin: float,
    vmax: float,
    *,
    step: float | None = None,
) -> float:
    """把元/㎡ 映射到 0–1；按金额分档 + 轻微 gamma，拉开几百块差距。"""
    if value <= 0:
        return 0.0
    if vmax <= vmin:
        return 0.65
    step = max(50.0, float(step or adaptive_color_step(vmin, vmax)))
    offset = max(0.0, float(value) - float(vmin))
    band_index = int(offset // step)
    max_band = max(1, math.ceil((float(vmax) - float(vmin)) / step))
    frac = (offset % step) / step
    t = min(band_index + frac, float(max_band)) / float(max_band)
    return max(0.0, min(1.0, t ** 0.72))


def _lerp_palette(t: float) -> tuple[int, int, int]:
    stops = HEATMAP_PALETTE
    seg = t * (len(stops) - 1)
    idx = int(seg)
    if idx >= len(stops) - 1:
        return stops[-1]
    frac = seg - idx
    a, b = stops[idx], stops[idx + 1]
    return tuple(int(a[i] + (b[i] - a[i]) * frac) for i in range(3))


def revenue_per_sqm_to_color(
    value: float,
    vmin: float,
    vmax: float,
    *,
    step: float | None = None,
) -> tuple[int, int, int]:
    """多档热力色（元/㎡）；坪效差几百块也会有不同色相。"""
    if value <= 0:
        return (235, 238, 242)
    step = step or adaptive_color_step(vmin, vmax)
    t = heatmap_normalize_t(value, vmin, vmax, step=step)
    return _lerp_palette(t)


def legend_tick_values(vmin: float, vmax: float, *, step: float | None = None) -> list[float]:
    """图例刻度：低、中、高 + 分档线。"""
    if vmax <= vmin:
        return [vmin]
    step = step or adaptive_color_step(vmin, vmax)
    ticks = [vmin]
    cursor = math.ceil(vmin / step) * step if vmin > 0 else step
    while cursor < vmax:
        ticks.append(cursor)
        cursor += step
    if ticks[-1] != vmax:
        ticks.append(vmax)
    return ticks[:6]


def sales_data_ready() -> bool:
    import os

    return os.path.isfile(DEFAULT_EXCEL) and os.path.getsize(DEFAULT_EXCEL) > 0
