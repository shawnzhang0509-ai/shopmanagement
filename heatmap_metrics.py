"""坪效热力图：按近 N 周销量计算 元/㎡（每平方米销售额）。"""
from __future__ import annotations

import math
import os
import re
from typing import Any

from sales_lookup import (
    DEFAULT_EXCEL,
    _normalize_key,
    load_weekly_sales,
    resolve_product_family,
)

_week_keys_cache: dict[tuple[str | None, int], set[str]] = {}
_amount_cache: dict[tuple, float] = {}
_sales_index_path: str | None = None
_sales_index_mtime: float = 0.0
_weeks_by_shop: dict[str, set[str]] = {}
_week_period_labels: dict[tuple[str, str], str] = {}
_index_product: dict[tuple[str, str, str], float] = {}
_index_family: dict[tuple[str, str, str], float] = {}
_index_prefix: dict[tuple[str, str, str], float] = {}

# 9 档实色渐变：低坪效(红) → 中(黄) → 高坪效(绿)
# 深红 → 中红 → 浅红 → 深黄 → 中黄 → 浅黄 → 浅绿 → 中绿 → 深绿
HEATMAP_PALETTE: tuple[tuple[int, int, int], ...] = (
    (153, 27, 27),
    (220, 53, 53),
    (252, 165, 165),
    (202, 138, 4),
    (234, 179, 8),
    (254, 240, 138),
    (134, 239, 172),
    (34, 197, 94),
    (21, 128, 61),
)
HEATMAP_ZERO = HEATMAP_PALETTE[0]  # 0 坪效 = 最差，深红报警
HEATMAP_TOP = HEATMAP_PALETTE[-1]  # 封顶坪效 = 最好，深绿
HEATMAP_COLOR_CAP = 1000.0  # 色阶上限：>$1000/㎡·周 一律最好绿，避免离群值压扁色阶
HEATMAP_BLINK_IDLE = (210, 214, 218)

# 坪效销量聚合：product=单品 SKU，prefix=SKU 前三位，family=Product Family
SALES_LEVELS: tuple[str, ...] = ("product", "prefix", "family")
SALES_LEVEL_LABELS: dict[str, str] = {
    "product": "单品",
    "prefix": "前三位",
    "family": "系列",
}


def normalize_sales_level(level: str | None) -> str:
    key = str(level or "product").strip().lower()
    if key in SALES_LEVEL_LABELS:
        return key
    return "product"


def sales_level_label(level: str | None) -> str:
    return SALES_LEVEL_LABELS.get(normalize_sales_level(level), "单品")


def next_sales_level(level: str | None) -> str:
    cur = normalize_sales_level(level)
    idx = SALES_LEVELS.index(cur)
    return SALES_LEVELS[(idx + 1) % len(SALES_LEVELS)]


def sku_prefix(sku: str) -> str:
    """SKU 前三位分组键，如 830-002 → 830，172-307 → 172。"""
    text = str(sku or "").strip()
    if not text:
        return ""
    if "-" in text:
        head = text.split("-", 1)[0].strip()
        if head:
            return head[:3] if len(head) >= 3 else head
    compact = re.sub(r"[^a-zA-Z0-9]", "", text)
    token = compact[:3] if compact else text[:3]
    return token.upper()


def sales_group_key(sku: str, product_family: str = "", *, level: str = "product") -> str:
    """布局上用于合并坪效的组键。"""
    lvl = normalize_sales_level(level)
    if lvl == "family":
        fam = resolve_product_family(product_family or sku) or product_family or sku
        return _normalize_key(fam)
    if lvl == "prefix":
        return _normalize_key(sku_prefix(sku))
    return _normalize_key(sku)


def _week_key(period: str) -> str:
    text = str(period or "")
    match = re.match(r"(\d{4}-W\d{2})", text)
    return match.group(1) if match else ""


def clear_heatmap_cache() -> None:
    global _week_keys_cache, _amount_cache
    global _sales_index_path, _sales_index_mtime
    global _weeks_by_shop, _week_period_labels
    global _index_product, _index_family, _index_prefix
    _week_keys_cache = {}
    _amount_cache = {}
    _sales_index_path = None
    _sales_index_mtime = 0.0
    _weeks_by_shop = {}
    _week_period_labels = {}
    _index_product = {}
    _index_family = {}
    _index_prefix = {}


def _ensure_sales_index() -> None:
    """一次扫描 weekly_sales，供周次列表与坪效查询复用（避免每件家具全表遍历）。"""
    global _sales_index_path, _sales_index_mtime
    global _weeks_by_shop, _week_period_labels
    global _index_product, _index_family, _index_prefix

    from sales_lookup import load_weekly_sales, resolve_weekly_sales_path

    path = resolve_weekly_sales_path()
    try:
        mtime = os.path.getmtime(path) if os.path.isfile(path) else 0.0
    except OSError:
        mtime = 0.0
    if _sales_index_path == path and mtime == _sales_index_mtime and _weeks_by_shop:
        return

    _weeks_by_shop = {}
    _week_period_labels = {}
    _index_product = {}
    _index_family = {}
    _index_prefix = {}
    _sales_index_path = path
    _sales_index_mtime = mtime

    for row in load_weekly_sales():
        wk = _week_key(row.year_week_period)
        if not wk:
            continue
        sid = row.shop_id or "other"
        _weeks_by_shop.setdefault(sid, set()).add(wk)
        label_key = (sid, wk)
        if label_key not in _week_period_labels:
            _week_period_labels[label_key] = str(row.year_week_period or wk)
        amt = float(row.total_amount or 0)
        if amt == 0:
            continue
        sku_n = _normalize_key(row.sku)
        fam_n = _normalize_key(row.product_family)
        pref_n = _normalize_key(sku_prefix(row.sku))
        if sku_n:
            pk = (sid, wk, sku_n)
            _index_product[pk] = _index_product.get(pk, 0.0) + amt
        if fam_n:
            fk = (sid, wk, fam_n)
            _index_family[fk] = _index_family.get(fk, 0.0) + amt
        if pref_n:
            rk = (sid, wk, pref_n)
            _index_prefix[rk] = _index_prefix.get(rk, 0.0) + amt


def list_all_week_keys(shop_id: str | None = None) -> list[str]:
    """门店全部有数据的自然周（升序）。"""
    _ensure_sales_index()
    if shop_id and shop_id not in ("all", ""):
        return sorted(_weeks_by_shop.get(shop_id, set()))
    all_w: set[str] = set()
    for ws in _weeks_by_shop.values():
        all_w |= ws
    return sorted(all_w)


def week_period_display(shop_id: str | None, week_key: str) -> str:
    _ensure_sales_index()
    sid = shop_id or ""
    if sid:
        label = _week_period_labels.get((sid, week_key))
        if label:
            return label
    for (s, wk), label in _week_period_labels.items():
        if wk == week_key and (not sid or s == sid):
            return label
    return week_key


def list_recent_week_keys(shop_id: str | None = None, num_weeks: int = 4) -> list[str]:
    num_weeks = max(1, int(num_weeks or 1))
    cache_key = (shop_id, num_weeks)
    if cache_key in _week_keys_cache:
        return sorted(_week_keys_cache[cache_key])

    _ensure_sales_index()
    if shop_id and shop_id not in ("all", ""):
        weeks = _weeks_by_shop.get(shop_id, set())
    else:
        weeks = set()
        for ws in _weeks_by_shop.values():
            weeks |= ws
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
    level: str = "product",
) -> float:
    sku = str(sku or "").strip()
    family = str(product_family or "").strip()
    lvl = normalize_sales_level(level)
    wk_tuple = tuple(sorted(week_keys)) if week_keys else None
    cache_key = (
        _normalize_key(sku),
        _normalize_key(family),
        shop_id,
        wk_tuple,
        max(1, int(num_weeks)),
        lvl,
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

    # shop_id 为空时不汇总全公司销量（避免布局误用全局 Branch）
    if not shop_id:
        _amount_cache[cache_key] = 0.0
        return 0.0

    _ensure_sales_index()
    sku_n = _normalize_key(sku)
    fam = resolve_product_family(family or sku) or family or sku
    fam_n = _normalize_key(fam)
    prefix_n = _normalize_key(sku_prefix(sku))
    amount = 0.0
    sid = shop_id

    for wk in allowed:
        if lvl == "family":
            if fam_n:
                amount += _index_family.get((sid, wk, fam_n), 0.0)
            continue
        if lvl == "prefix":
            if prefix_n:
                amount += _index_prefix.get((sid, wk, prefix_n), 0.0)
            continue
        if sku_n:
            amount += _index_product.get((sid, wk, sku_n), 0.0)

    if lvl == "product" and amount <= 0 and fam_n:
        for wk in allowed:
            amount += _index_family.get((sid, wk, fam_n), 0.0)

    _amount_cache[cache_key] = amount
    return amount


def compute_grouped_revenue_per_sqm(
    members: list[Any],
    *,
    area_mm2_fn,
    shop_id: str | None = None,
    num_weeks: int = 4,
    week_keys: list[str] | None = None,
    week_divisor: int = 1,
    level: str = "product",
) -> float:
    """系列/前三位：组内共享同一周均坪效 = 组总销量 ÷ 组总面积。"""
    if not members:
        return 0.0
    rep = members[0]
    sku = getattr(rep, "name", "") or ""
    family = getattr(rep, "product_family", "") or ""
    total_area = sum(max(0.0, float(area_mm2_fn(item))) for item in members)
    if total_area <= 0:
        return 0.0
    amount = lookup_sales_amount(
        sku,
        family,
        shop_id=shop_id,
        num_weeks=num_weeks,
        week_keys=week_keys,
        level=level,
    )
    return revenue_per_sqm(amount, total_area, num_weeks=week_divisor)


def furniture_area_sqm(area_mm2: float) -> float:
    return max(0.0, float(area_mm2)) / 1_000_000.0


def revenue_per_sqm(
    sales_amount: float,
    area_mm2: float,
    *,
    num_weeks: int = 1,
) -> float:
    """元/㎡；多周汇总时 sales_amount 为各周合计，num_weeks 用于换算周均坪效。"""
    area_sqm = furniture_area_sqm(area_mm2)
    if area_sqm <= 0:
        return 0.0
    weeks = max(1, int(num_weeks or 1))
    return max(0.0, float(sales_amount)) / weeks / area_sqm


def format_revenue_per_sqm(value: float) -> str:
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "$0/㎡·周"
    value = float(value)
    if value <= 0:
        return "$0/㎡·周"
    if value >= 1000:
        return f"${value:,.0f}/㎡·周"
    if value >= 100:
        return f"${value:.0f}/㎡·周"
    return f"${value:.1f}/㎡·周"


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
    """把元/㎡ 映射到 0–1（0=低坪效/红，1=高坪效/绿）。"""
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
    return max(0.0, min(1.0, t))


def _lerp_palette(t: float) -> tuple[int, int, int]:
    stops = HEATMAP_PALETTE
    seg = t * (len(stops) - 1)
    idx = int(seg)
    if idx >= len(stops) - 1:
        return stops[-1]
    frac = seg - idx
    a, b = stops[idx], stops[idx + 1]
    return tuple(int(a[i] + (b[i] - a[i]) * frac) for i in range(3))


def heatmap_color_vrange(vmin: float, vmax: float) -> tuple[float, float]:
    """Clamp vmax used for color scale so one outlier does not wash out the floor."""
    lo = max(0.0, float(vmin))
    hi = max(0.0, float(vmax))
    if hi <= 0:
        return lo, 1.0
    capped = min(hi, HEATMAP_COLOR_CAP)
    if capped <= lo:
        capped = min(HEATMAP_COLOR_CAP, max(lo + 1.0, hi))
    return lo, capped


def revenue_per_sqm_to_color(
    value: float,
    vmin: float,
    vmax: float,
    *,
    step: float | None = None,
) -> tuple[int, int, int]:
    """实色 RGB：绿=高坪效，黄=中，红=低；0 坪效固定深红报警。"""
    if value <= 0:
        return HEATMAP_ZERO
    if value >= HEATMAP_COLOR_CAP:
        return HEATMAP_TOP
    cmin, cmax = heatmap_color_vrange(vmin, vmax)
    step = step or adaptive_color_step(cmin, cmax)
    t = heatmap_normalize_t(value, cmin, cmax, step=step)
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
    from sales_lookup import resolve_weekly_sales_path

    path = resolve_weekly_sales_path()
    return os.path.isfile(path) and os.path.getsize(path) > 0
