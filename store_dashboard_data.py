"""多店汇总 / 系列对比 — 数据层。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from heatmap_metrics import _week_key
from sales_lookup import load_weekly_sales, sales_data_available

# 与 layout.py STORE_CATALOG + LAYOUT_SLUG_TO_SALES_SHOP 对齐
STORE_ENTRIES: tuple[dict[str, str], ...] = (
    {"name": "Onehunga店", "slug": "onehunga", "shop_id": "onehunga"},
    {"name": "Hamilton店", "slug": "hamilton", "shop_id": "hamilton"},
    {"name": "Westgate店", "slug": "westgate", "shop_id": "westgate"},
    {"name": "基督城 Colombo店", "slug": "christchurch_colombo", "shop_id": "chch"},
    {"name": "基督城 Bleiham店", "slug": "christchurch_bleiham", "shop_id": "chch"},
)

WEEK_OPTIONS: tuple[tuple[str, int], ...] = (
    ("4 周", 4),
    ("8 周", 8),
    ("12 周", 12),
)

# 各店区分色（柱状图 / 图例）
STORE_COLORS: tuple[tuple[int, int, int], ...] = (
    (52, 152, 219),
    (46, 204, 113),
    (155, 89, 182),
    (230, 126, 34),
    (231, 76, 60),
)


@dataclass
class StoreOverview:
    shop_id: str
    name: str
    slug: str
    total_amount: float = 0.0
    total_qty: float = 0.0
    top_families: list[tuple[str, float]] = field(default_factory=list)


@dataclass
class FamilyCompareRow:
    family: str
    by_store: dict[str, float] = field(default_factory=dict)
    total: float = 0.0


def list_recent_week_keys_global(num_weeks: int = 4) -> list[str]:
    """全部门店最近 N 个自然周（升序）。"""
    weeks: set[str] = set()
    for row in load_weekly_sales():
        wk = _week_key(row.year_week_period)
        if wk:
            weeks.add(wk)
    n = max(1, int(num_weeks or 1))
    return sorted(weeks)[-n:]


def week_range_label(week_keys: list[str]) -> str:
    if not week_keys:
        return "无周数据"
    if len(week_keys) == 1:
        return week_keys[0]
    return f"{week_keys[0]} ~ {week_keys[-1]}"


def _family_label(raw: str) -> str:
    text = str(raw or "").strip()
    return text or "未分类"


def aggregate_store_overviews(
    shop_ids: list[str],
    week_keys: list[str],
    *,
    top_n: int = 5,
) -> list[StoreOverview]:
    allowed = set(week_keys)
    by_shop: dict[str, StoreOverview] = {}
    fam_totals: dict[str, dict[str, float]] = {}

    id_to_entry = {e["shop_id"]: e for e in STORE_ENTRIES}
    slug_by_shop: dict[str, str] = {}
    for e in STORE_ENTRIES:
        slug_by_shop.setdefault(e["shop_id"], e["slug"])

    for sid in shop_ids:
        entry = id_to_entry.get(sid)
        if not entry:
            continue
        by_shop[sid] = StoreOverview(
            shop_id=sid,
            name=entry["name"],
            slug=entry["slug"],
        )
        fam_totals[sid] = {}

    for row in load_weekly_sales():
        if row.shop_id not in by_shop:
            continue
        if _week_key(row.year_week_period) not in allowed:
            continue
        ov = by_shop[row.shop_id]
        ov.total_amount += row.total_amount
        ov.total_qty += row.total_qty
        fam = _family_label(row.product_family)
        fam_totals[row.shop_id][fam] = fam_totals[row.shop_id].get(fam, 0.0) + row.total_amount

    for sid, ov in by_shop.items():
        ranked = sorted(fam_totals.get(sid, {}).items(), key=lambda x: -x[1])
        ov.top_families = ranked[:top_n]

    order = {e["shop_id"]: i for i, e in enumerate(STORE_ENTRIES)}
    return sorted(by_shop.values(), key=lambda o: order.get(o.shop_id, 99))


def aggregate_family_comparison(
    shop_ids: list[str],
    week_keys: list[str],
    *,
    top_n: int = 20,
) -> list[FamilyCompareRow]:
    allowed = set(week_keys)
    shop_set = set(shop_ids)
    matrix: dict[str, dict[str, float]] = {}

    for row in load_weekly_sales():
        if row.shop_id not in shop_set:
            continue
        if _week_key(row.year_week_period) not in allowed:
            continue
        fam = _family_label(row.product_family)
        matrix.setdefault(fam, {})
        matrix[fam][row.shop_id] = matrix[fam].get(row.shop_id, 0.0) + row.total_amount

    rows: list[FamilyCompareRow] = []
    for fam, stores in matrix.items():
        total = sum(stores.values())
        rows.append(FamilyCompareRow(family=fam, by_store=dict(stores), total=total))

    rows.sort(key=lambda r: -r.total)
    return rows[:top_n]


def unique_shop_ids_from_entries(selected_slugs: set[str] | None = None) -> list[str]:
    """去重 shop_id（基督城两店共用 chch）。"""
    seen: set[str] = set()
    out: list[str] = []
    for e in STORE_ENTRIES:
        if selected_slugs is not None and e["slug"] not in selected_slugs:
            continue
        sid = e["shop_id"]
        if sid not in seen:
            seen.add(sid)
            out.append(sid)
    return out


def entries_for_ui() -> list[dict[str, str]]:
    return list(STORE_ENTRIES)
