"""多店汇总 / 系列对比 — 数据层。"""
from __future__ import annotations

import math
import os

from heatmap_metrics import _week_key
from layout_family_lookup import families_in_layouts, layout_families_by_store
from region_config import store_entries
from sales_lookup import load_weekly_sales, sales_data_available
from ui_common import sanitize_display_text

# 与 config/regions/*.json + layout.py 对齐
STORE_ENTRIES: tuple[dict[str, str], ...] = store_entries()

WEEK_OPTIONS: tuple[tuple[str, int], ...] = (
    ("4 周", 4),
    ("8 周", 8),
    ("12 周", 12),
)

FILTER_ALL = "all"
FILTER_LAYOUT = "layout"

# 系列跨店方差：均值过低时不判（避免小样本误报）
MIN_FAMILY_MEAN_FOR_SPREAD = 800.0
SPREAD_CV_ATTENTION = 0.55
SPREAD_MIN_SHARE_OF_MEAN = 0.42
SPREAD_MIN_MAX_RATIO = 2.0

# 各店区分色（柱状图 / 图例）
STORE_COLORS: tuple[tuple[int, int, int], ...] = (
    (52, 152, 219),
    (46, 204, 113),
    (155, 89, 182),
    (230, 126, 34),
    (231, 76, 60),
)


from dataclasses import dataclass, field


@dataclass
class StoreOverview:
    shop_id: str
    name: str
    slug: str
    total_amount: float = 0.0
    total_qty: float = 0.0
    top_families: list[tuple[str, float]] = field(default_factory=list)
    layout_family_count: int = 0


@dataclass
class FamilyCompareRow:
    family: str
    by_store: dict[str, float] = field(default_factory=dict)
    by_slug: dict[str, float] = field(default_factory=dict)
    total: float = 0.0
    on_layout: bool = False
    spread_cv: float = 0.0
    min_shop_id: str = ""
    min_slug: str = ""
    min_store_name: str = ""
    min_amount: float = 0.0
    max_amount: float = 0.0
    attention: bool = False


def _selected_entries(selected_slugs: set[str] | None) -> list[dict[str, str]]:
    slug_set = selected_slugs or {e["slug"] for e in STORE_ENTRIES}
    return [e for e in STORE_ENTRIES if e["slug"] in slug_set]


def analyze_family_spread(
    entries: list[dict[str, str]],
    by_store: dict[str, float],
) -> tuple[float, str, str, str, float, float, bool]:
    """跨店离散度：变异系数 CV；attention=方差大且明显垫店。"""
    if len(entries) < 2:
        return 0.0, "", "", "", 0.0, 0.0, False
    amounts = [float(by_store.get(e["shop_id"], 0.0)) for e in entries]
    mean = sum(amounts) / len(amounts)
    if mean < MIN_FAMILY_MEAN_FOR_SPREAD:
        return 0.0, "", "", "", min(amounts), max(amounts), False
    variance = sum((a - mean) ** 2 for a in amounts) / len(amounts)
    stdev = math.sqrt(variance)
    cv = stdev / mean if mean > 0 else 0.0
    min_a = min(amounts)
    max_a = max(amounts)
    min_i = amounts.index(min_a)
    min_e = entries[min_i]
    attention = (
        cv >= SPREAD_CV_ATTENTION
        and min_a <= SPREAD_MIN_SHARE_OF_MEAN * mean
        and max_a >= min_a * SPREAD_MIN_MAX_RATIO
        and min_a < max_a
    )
    return (
        cv,
        min_e["shop_id"],
        min_e["slug"],
        min_e["name"],
        min_a,
        max_a,
        attention,
    )


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
    """Excel/销量里的系列名；nan/空 → 未分类。"""
    text = sanitize_display_text(raw, "")
    if not text:
        return "未分类"
    return text


def _family_match_key(family: str) -> str:
    """合并 Liberty / LIBERTY 等同系列。"""
    return _family_label(family).casefold()


def _pick_display_name(existing: str, new: str) -> str:
    """保留较规范的显示名（首字母大写优先）。"""
    if not existing:
        return new
    if existing == existing.lower() and new != new.lower():
        return new
    if existing.isupper() and not new.isupper():
        return new
    return existing


def aggregate_store_overviews(
    shop_ids: list[str],
    week_keys: list[str],
    *,
    selected_slugs: set[str] | None = None,
    top_n: int = 8,
) -> list[StoreOverview]:
    allowed = set(week_keys)
    by_shop: dict[str, StoreOverview] = {}
    fam_totals: dict[str, dict[str, float]] = {}
    fam_labels: dict[str, str] = {}

    slug_set = selected_slugs or {e["slug"] for e in STORE_ENTRIES}
    layout_by_shop: dict[str, set[str]] = {}
    for e in STORE_ENTRIES:
        if e["slug"] not in slug_set:
            continue
        fams = families_in_layouts({e["slug"]})
        keys = {_family_match_key(f) for f in fams}
        layout_by_shop.setdefault(e["shop_id"], set()).update(keys)

    id_to_entry = {e["shop_id"]: e for e in STORE_ENTRIES}

    for sid in shop_ids:
        entry = id_to_entry.get(sid)
        if not entry:
            continue
        by_shop[sid] = StoreOverview(
            shop_id=sid,
            name=entry["name"],
            slug=entry["slug"],
            layout_family_count=len(layout_by_shop.get(sid, set())),
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
        fkey = _family_match_key(fam)
        fam_labels[fkey] = _pick_display_name(fam_labels.get(fkey, ""), fam)
        fam_totals[row.shop_id][fkey] = fam_totals[row.shop_id].get(fkey, 0.0) + row.total_amount

    for sid, ov in by_shop.items():
        ranked = sorted(
            ((fam_labels.get(k, k), v) for k, v in fam_totals.get(sid, {}).items()),
            key=lambda x: -x[1],
        )
        ov.top_families = ranked[:top_n]

    order = {e["shop_id"]: i for i, e in enumerate(STORE_ENTRIES)}
    return sorted(by_shop.values(), key=lambda o: order.get(o.shop_id, 99))


def aggregate_family_comparison(
    shop_ids: list[str],
    week_keys: list[str],
    *,
    selected_slugs: set[str] | None = None,
    family_filter: str = FILTER_ALL,
    top_n: int | None = None,
) -> list[FamilyCompareRow]:
    allowed = set(week_keys)
    shop_set = set(shop_ids)
    matrix: dict[str, dict[str, float]] = {}
    fam_labels: dict[str, str] = {}

    slug_set = selected_slugs or {e["slug"] for e in STORE_ENTRIES}
    layout_family_keys: set[str] = set()
    for fam in families_in_layouts(slug_set):
        layout_family_keys.add(_family_match_key(fam))

    for row in load_weekly_sales():
        if row.shop_id not in shop_set:
            continue
        if _week_key(row.year_week_period) not in allowed:
            continue
        fam = _family_label(row.product_family)
        fkey = _family_match_key(fam)
        if family_filter == FILTER_LAYOUT and fkey not in layout_family_keys:
            continue
        fam_labels[fkey] = _pick_display_name(fam_labels.get(fkey, ""), fam)
        matrix.setdefault(fkey, {})
        matrix[fkey][row.shop_id] = matrix[fkey].get(row.shop_id, 0.0) + row.total_amount

    entries = _selected_entries(slug_set)
    rows: list[FamilyCompareRow] = []
    for fkey, stores in matrix.items():
        display = fam_labels.get(fkey, fkey)
        total = sum(stores.values())
        by_slug = {e["slug"]: float(stores.get(e["shop_id"], 0.0)) for e in entries}
        cv, min_sid, min_slug, min_name, min_amt, max_amt, attention = analyze_family_spread(
            entries, stores
        )
        rows.append(
            FamilyCompareRow(
                family=display,
                by_store=dict(stores),
                by_slug=by_slug,
                total=total,
                on_layout=fkey in layout_family_keys,
                spread_cv=cv,
                min_shop_id=min_sid,
                min_slug=min_slug,
                min_store_name=min_name,
                min_amount=min_amt,
                max_amount=max_amt,
                attention=attention,
            )
        )

    rows.sort(key=lambda r: (-r.total, r.family.lower()))
    if top_n is not None and top_n > 0:
        return rows[:top_n]
    return rows


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


def slug_to_entry() -> dict[str, dict[str, str]]:
    return {e["slug"]: e for e in STORE_ENTRIES}


def count_attention_families(rows: list[FamilyCompareRow]) -> int:
    return sum(1 for r in rows if r.attention)


def filter_attention_rows(rows: list[FamilyCompareRow]) -> list[FamilyCompareRow]:
    out = [r for r in rows if r.attention]
    out.sort(key=lambda r: (-r.spread_cv, -r.total, r.family.lower()))
    return out


def compare_store_columns(
    selected_slugs: set[str],
    shop_overviews: list[StoreOverview],
) -> list[StoreOverview]:
    """系列对比列：与侧栏一致，每 slug 一列（基督城两店各一列，销量可同为 chch）。"""
    by_shop = {o.shop_id: o for o in shop_overviews}
    out: list[StoreOverview] = []
    for e in STORE_ENTRIES:
        if e["slug"] not in selected_slugs:
            continue
        base = by_shop.get(e["shop_id"])
        out.append(
            StoreOverview(
                shop_id=e["shop_id"],
                name=e["name"],
                slug=e["slug"],
                total_amount=base.total_amount if base else 0.0,
                total_qty=base.total_qty if base else 0.0,
                top_families=list(base.top_families) if base else [],
                layout_family_count=base.layout_family_count if base else 0,
            )
        )
    return out


def sidebar_color_index(slug: str) -> int:
    for i, e in enumerate(STORE_ENTRIES):
        if e["slug"] == slug:
            return i
    return 0
