"""仓库库存 + UnitPrice / SalePrice 查询（读 data/product_stock_price.xlsx）。"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_EXCEL = os.path.join(SCRIPT_DIR, "data", "product_stock_price.xlsx")
STOCK_PRICE_SQL = os.path.join(SCRIPT_DIR, "sql", "product_stock_price.sql")

_cache: dict[str, "StockPriceRow"] = {}
_loaded_path: str | None = None
_last_error: str | None = None


@dataclass
class StockPriceRow:
    sku: str
    product_name: str
    product_family: str
    unit_price: float
    sale_price: float
    on_promotion: bool
    carbine_stock: int
    walls_stock: int
    north_island_total: int
    gerald_connolly_stock: int

    @property
    def total_warehouse_stock(self) -> int:
        return self.north_island_total + self.gerald_connolly_stock

    def price_label(self) -> str:
        if self.on_promotion and self.sale_price < self.unit_price:
            return f"${self.sale_price:,.0f} (促) ← ${self.unit_price:,.0f}"
        return f"${self.unit_price:,.0f}"

    def stock_label(self, *, compact: bool = False) -> str:
        if compact:
            return f"北{self.north_island_total} 南{self.gerald_connolly_stock}"
        return (
            f"Carbine {self.carbine_stock} · Walls {self.walls_stock} · "
            f"北岛 {self.north_island_total} · GC {self.gerald_connolly_stock}"
        )


def _norm_key(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _to_float(val, default=0.0) -> float:
    try:
        if val is None or val == "":
            return default
        return float(val)
    except (TypeError, ValueError):
        return default


def _to_int(val, default=0) -> int:
    try:
        if val is None or val == "":
            return default
        return int(float(val))
    except (TypeError, ValueError):
        return default


def _row_value(row: dict, *names: str, default=""):
    lower = {_norm_key(k): v for k, v in row.items()}
    for name in names:
        key = _norm_key(name)
        if key in lower:
            return lower[key]
    return default


def _parse_row(row: dict) -> StockPriceRow | None:
    sku = str(_row_value(row, "Sku", "SKU", "product_code") or "").strip()
    if not sku:
        return None
    unit = _to_float(_row_value(row, "UnitPrice", "unit_price"))
    sale = _to_float(_row_value(row, "SalePrice", "sale_price"), unit)
    on_promo = bool(_to_int(_row_value(row, "OnPromotion", "on_promotion")))
    if not on_promo and sale > 0 and unit > 0 and sale < unit:
        on_promo = True
    return StockPriceRow(
        sku=sku,
        product_name=str(_row_value(row, "ProductName", "product_name", "Name") or "").strip(),
        product_family=str(_row_value(row, "ProductFamily", "product_family", "Family") or "").strip(),
        unit_price=unit,
        sale_price=sale if sale > 0 else unit,
        on_promotion=on_promo,
        carbine_stock=_to_int(_row_value(row, "CarbineStock", "carbine_stock")),
        walls_stock=_to_int(_row_value(row, "WallsStock", "walls_stock")),
        north_island_total=_to_int(_row_value(row, "NorthIslandTotal", "north_island_total")),
        gerald_connolly_stock=_to_int(_row_value(row, "GeraldConnellyStock", "gerald_connolly_stock")),
    )


def reload_stock_prices(path: str | None = None) -> dict[str, StockPriceRow]:
    global _cache, _loaded_path, _last_error
    excel_path = path or DEFAULT_EXCEL
    _cache = {}
    _loaded_path = excel_path
    _last_error = None
    if not os.path.isfile(excel_path):
        _last_error = f"未找到 {excel_path}，请运行 scripts/grab_stock_price.py"
        return _cache
    try:
        import pandas as pd

        df = pd.read_excel(excel_path, dtype=str)
        rows = df.to_dict(orient="records")
    except Exception as exc:
        _last_error = str(exc)
        return _cache
    for row in rows:
        item = _parse_row(row)
        if item:
            _cache[_norm_key(item.sku)] = item
    return _cache


def lookup_stock_price(sku_or_name: str) -> StockPriceRow | None:
    if not _cache and _loaded_path is None:
        reload_stock_prices()
    key = _norm_key(sku_or_name)
    if not key:
        return None
    if key in _cache:
        return _cache[key]
    for sku, row in _cache.items():
        if sku.startswith(key) or key.startswith(sku):
            return row
    return None


def format_stock_badge(sku_or_name: str) -> str:
    """画布标签用：北6 南1"""
    row = lookup_stock_price(sku_or_name)
    if not row:
        return ""
    return row.stock_label(compact=True)


def format_stock_price_hint(sku_or_name: str, *, compact: bool = True) -> str:
    row = lookup_stock_price(sku_or_name)
    if not row:
        return ""
    if compact:
        return f"{row.price_label()} · 库存 {row.stock_label(compact=True)}"
    return f"{row.price_label()} · {row.stock_label(compact=False)}"


def last_load_error() -> str | None:
    return _last_error
