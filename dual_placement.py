"""双摆场产品：仓库有货 + Storage 有货（与 Display 共用门店/库位解析逻辑）。"""
from __future__ import annotations

from display_lookup import DisplayItem, lookup_display_item


def warehouse_fulfillment_qty(name_or_code: str) -> int:
    from stock_price_lookup import lookup_stock_price

    row = lookup_stock_price(name_or_code)
    if not row:
        return 0
    return int(row.total_warehouse_stock)


def is_dual_placement_eligible(name_or_code: str, *, shop_id: str = "all") -> bool:
    """仓库 fulfillment 有货，且 Storage 库位也有货（适合两处摆场/调拨）。"""
    item = lookup_display_item(name_or_code)
    if not item:
        return False
    return warehouse_fulfillment_qty(name_or_code) > 0 and item.storage_qty_for_shop(shop_id) > 0


def is_display_storage_pair(name_or_code: str, *, shop_id: str = "all") -> bool:
    """Display 与 Storage 同时有货（不含仓库 fulfillment）。"""
    item = lookup_display_item(name_or_code)
    if not item:
        return False
    return item.display_qty_for_shop(shop_id) > 0 and item.storage_qty_for_shop(shop_id) > 0


def dual_placement_badge(name_or_code: str, *, shop_id: str = "all") -> str:
    """画布/侧栏短标签：仓6 · 储2 · 场1"""
    item = lookup_display_item(name_or_code)
    if not item:
        return ""
    wh = warehouse_fulfillment_qty(name_or_code)
    st = item.storage_qty_for_shop(shop_id)
    disp = item.display_qty_for_shop(shop_id)
    if wh <= 0 or st <= 0:
        return ""
    parts = [f"仓{wh}", f"储{st}"]
    if disp > 0:
        parts.append(f"场{disp}")
    return " · ".join(parts)


def format_enhanced_stock_badge(name_or_code: str, *, shop_id: str = "all") -> str:
    from stock_price_lookup import format_stock_badge

    base = format_stock_badge(name_or_code)
    extra = dual_placement_badge(name_or_code, shop_id=shop_id)
    if base and extra:
        return f"{base} · {extra}"
    return base or extra


def filter_dual_placement_items(items: list[DisplayItem], *, shop_id: str = "all") -> list[DisplayItem]:
    return [it for it in items if is_dual_placement_eligible(it.key, shop_id=shop_id)]
