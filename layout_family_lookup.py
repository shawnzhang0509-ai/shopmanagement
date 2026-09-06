"""从门店布局 JSON 读取已摆场 Product Family（供多店对比使用）。"""
from __future__ import annotations

import json
import os

from ui_common import sanitize_display_text

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LAYOUTS_DIR = os.path.join(SCRIPT_DIR, "data", "layouts")


def layout_path_for_slug(slug: str) -> str:
    return os.path.join(LAYOUTS_DIR, f"{slug}.json")


def layout_file_exists(slug: str) -> bool:
    return os.path.isfile(layout_path_for_slug(slug))


def _is_placeholder_family(family: str, sku: str) -> bool:
    fam = sanitize_display_text(family, "")
    sku_clean = sanitize_display_text(sku, "")
    if not fam:
        return True
    if fam in ("未分类", "unnamed"):
        return True
    return fam == sku_clean


def resolve_placed_family(name: str, stored: str = "") -> str:
    """解析布局里一件家具的系列名（与 layout 编辑器逻辑一致）。"""
    sku = sanitize_display_text(name, "")
    stored = sanitize_display_text(stored, "")
    if stored and not _is_placeholder_family(stored, sku):
        return stored
    try:
        from display_lookup import effective_family_from_display_item, lookup_display_item

        item = lookup_display_item(sku)
        if item:
            fam = effective_family_from_display_item(item)
            if fam and not _is_placeholder_family(fam, sku):
                return fam
    except Exception:
        pass
    try:
        with open(os.path.join(SCRIPT_DIR, "furniture_templates.json"), encoding="utf-8") as f:
            templates = json.load(f)
        for tpl in templates:
            if sanitize_display_text(tpl.get("id"), "") == sku:
                fam = sanitize_display_text(tpl.get("product_family"), "")
                if fam and not _is_placeholder_family(fam, sku):
                    return fam
    except Exception:
        pass
    try:
        from sales_lookup import aggregate_by_sku, resolve_product_family
        from sales_lookup import _normalize_key

        sku_key = _normalize_key(sku)
        sku_totals = aggregate_by_sku()
        row = sku_totals.get(sku_key)
        if row:
            fam = sanitize_display_text(row.get("product_family", ""), "")
            if fam and not _is_placeholder_family(fam, sku):
                return fam
        fam = resolve_product_family(sku)
        if fam and not _is_placeholder_family(fam, sku):
            return fam
    except Exception:
        pass
    return ""


def families_in_layout(slug: str) -> set[str]:
    """某门店布局里已摆放的系列名（去重）。"""
    path = layout_path_for_slug(slug)
    if not os.path.isfile(path):
        return set()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return set()
    out: set[str] = set()
    for furn in data.get("furnitures", []):
        name = furn.get("name", "")
        stored = furn.get("product_family", "")
        fam = resolve_placed_family(name, stored)
        if fam:
            out.add(fam)
    return out


def families_in_layouts(slugs: set[str]) -> set[str]:
    """多个门店布局里出现过的系列名并集。"""
    union: set[str] = set()
    for slug in slugs:
        union |= families_in_layout(slug)
    return union


def layout_families_by_store(slugs: set[str]) -> dict[str, list[str]]:
    """slug → 该店布局中的系列列表（排序）。"""
    out: dict[str, list[str]] = {}
    for slug in slugs:
        fams = sorted(families_in_layout(slug), key=str.lower)
        if fams:
            out[slug] = fams
    return out


def load_layout_snapshot(slug: str) -> dict | None:
    path = layout_path_for_slug(slug)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
