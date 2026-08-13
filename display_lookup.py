"""从 display.xlsx（推荐）或 JSON 缓存加载门店 Display 库存，并与模板库匹配。

推荐工作流（和 roi.xlsx 一样）：
  1. 在 SSMS 里写好 SQL（见 display.sql）
  2. 结果导出为 display.xlsx，放到项目根目录
  3. 启动 start_template → Display 库自动读取

可选：配置 display_config.json 直连 MSSQL（需 Azure 防火墙放行）。
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DISPLAY_FILE = os.path.join(SCRIPT_DIR, "display.xlsx")
CONFIG_FILE = os.path.join(SCRIPT_DIR, "display_config.json")
CONFIG_EXAMPLE = os.path.join(SCRIPT_DIR, "display_config.example.json")
CACHE_FILE = os.path.join(SCRIPT_DIR, "display_cache.json")

# 门店：按 Stock Details 里的 location 名称匹配
SHOPS: list[dict[str, Any]] = [
    {"id": "all", "label": "全部", "patterns": []},
    {"id": "onehunga", "label": "Onehunga", "patterns": ["onehunga"]},
    {"id": "westgate", "label": "Westgate", "patterns": ["westgate"]},
    {"id": "hamilton", "label": "Hamilton", "patterns": ["hamilton"]},
    {"id": "chch", "label": "Christchurch", "patterns": ["chch", "christchurch", "colombo"]},
    {"id": "carbine", "label": "Carbine Rd", "patterns": ["carbine"]},
    {"id": "other", "label": "其他", "patterns": []},
]

# Excel / SQL 列名别名（不区分大小写，空格会折叠）
_COL_ALIASES: dict[str, tuple[str, ...]] = {
    "warehouse_name": ("warehouse_name", "warehousename", "warehouse name", "warehouse"),
    "product_code": ("product_code", "productcode", "code", "sku", "product code", "item code"),
    "product_name": ("product_name", "productname", "product name", "title", "description"),
    "product_family": ("product_family", "productfamily", "family", "product family", "range", "collection"),
    "display_qty": ("display_qty", "displayqty", "display qty", "quantity", "qty"),
    "stock_details": ("stock_details", "stockdetails", "stock details", "stock", "display stock", "inventory"),
}

_display_cache: list["DisplayItem"] | None = None
_last_load_error: str | None = None
_last_load_source: str | None = None


@dataclass
class DisplaySlot:
    shop_id: str
    shop_label: str
    location: str
    qty: int


@dataclass
class DisplayItem:
    product_code: str
    product_name: str
    product_family: str
    stock_details: str
    displays: list[DisplaySlot] = field(default_factory=list)

    @property
    def key(self) -> str:
        return self.product_code or self.product_name

    def display_qty_for_shop(self, shop_id: str) -> int:
        if shop_id == "all":
            return sum(s.qty for s in self.displays)
        return sum(s.qty for s in self.displays if s.shop_id == shop_id)

    def shops_with_display(self) -> set[str]:
        return {s.shop_id for s in self.displays if s.qty > 0}


def _normalize_key(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _normalize_header(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _canonicalize_row(raw: dict) -> dict:
    """把 Excel / SQL 任意列名映射到标准字段名。"""
    normalized = {_normalize_header(k): v for k, v in raw.items()}
    out: dict = {}
    for field, aliases in _COL_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                out[field] = normalized[alias]
                break
    return out


def _detect_format(fields: dict) -> str | None:
    keys = set(fields)
    has_product = "product_code" in keys or "product_name" in keys
    if "warehouse_name" in keys and "display_qty" in keys and has_product:
        return "warehouse"
    if "stock_details" in keys and has_product:
        return "stock"
    return None


def _resolve_columns(headers: list[str]) -> tuple[str, dict[str, int]] | None:
    sample = {}
    for field, aliases in _COL_ALIASES.items():
        for i, h in enumerate(headers):
            if h in aliases:
                sample[field] = True
                break
    fmt = _detect_format(sample)
    if not fmt:
        return None
    mapping: dict[str, int] = {}
    for field, aliases in _COL_ALIASES.items():
        for i, h in enumerate(headers):
            if h in aliases:
                mapping[field] = i
                break
    return fmt, mapping


def is_display_location(location: str) -> bool:
    low = location.lower()
    if "no longer available" in low:
        return False
    return "display" in low


def shop_id_for_location(location: str) -> str:
    low = location.lower()
    for shop in SHOPS:
        if shop["id"] in ("all", "other"):
            continue
        if any(p in low for p in shop["patterns"]):
            return shop["id"]
    return "other"


def shop_label(shop_id: str) -> str:
    for shop in SHOPS:
        if shop["id"] == shop_id:
            return shop["label"]
    return shop_id


def parse_stock_details(text: str) -> list[DisplaySlot]:
    slots: list[DisplaySlot] = []
    if not text:
        return slots
    for part in str(text).split(";"):
        part = part.strip()
        if not part or ":" not in part:
            continue
        loc, qty_s = part.rsplit(":", 1)
        loc = loc.strip()
        if not is_display_location(loc):
            continue
        try:
            qty = int(float(qty_s.strip()))
        except (TypeError, ValueError):
            qty = 0
        if qty <= 0:
            continue
        sid = shop_id_for_location(loc)
        slots.append(DisplaySlot(sid, shop_label(sid), loc, qty))
    return slots


def _cell_str(row: tuple, idx: int | None) -> str:
    if idx is None or idx >= len(row):
        return ""
    val = row[idx]
    if val is None:
        return ""
    return str(val).strip()


def _row_to_item(row: dict) -> DisplayItem | None:
    code = str(row.get("product_code") or row.get("sku") or row.get("code") or "").strip()
    name = str(row.get("product_name") or row.get("name") or row.get("title") or "").strip()
    family = str(row.get("product_family") or row.get("family") or "").strip()
    stock = str(row.get("stock_details") or row.get("stock") or row.get("Stock Details") or "").strip()
    if not name and not code:
        return None
    if not family:
        family = name.split(" ")[0] if name else code
    displays = row.get("displays")
    if isinstance(displays, list) and displays:
        slots = [
            DisplaySlot(
                str(d.get("shop_id", "other")),
                str(d.get("shop_label", shop_label(str(d.get("shop_id", "other"))))),
                str(d.get("location", "")),
                int(d.get("qty", 0) or 0),
            )
            for d in displays
            if int(d.get("qty", 0) or 0) > 0
        ]
    else:
        slots = parse_stock_details(stock)
    if not slots:
        return None
    return DisplayItem(code or name, name or code, family, stock, slots)


def _aggregate_warehouse_rows(rows: list[dict]) -> list[DisplayItem]:
    """多行（每行一个仓库+产品）合并为 DisplayItem。"""
    groups: dict[str, dict] = {}
    for raw in rows:
        row = raw if "warehouse_name" in raw else _canonicalize_row(raw)
        code = str(row.get("product_code") or "").strip()
        name = str(row.get("product_name") or "").strip()
        warehouse = str(row.get("warehouse_name") or "").strip()
        try:
            qty = int(float(row.get("display_qty") or 0))
        except (TypeError, ValueError):
            qty = 0
        if not warehouse or qty <= 0 or (not code and not name):
            continue
        key = _normalize_key(code or name)
        if key not in groups:
            family = str(row.get("product_family") or "").strip()
            if not family:
                family = (name or code).split(" ")[0]
            groups[key] = {
                "product_code": code or name,
                "product_name": name or code,
                "product_family": family,
                "slots": {},
            }
        sid = shop_id_for_location(warehouse)
        slot_key = (sid, warehouse)
        groups[key]["slots"][slot_key] = groups[key]["slots"].get(slot_key, 0) + qty

    items: list[DisplayItem] = []
    for g in groups.values():
        displays = [
            {"shop_id": sid, "shop_label": shop_label(sid), "location": loc, "qty": q}
            for (sid, loc), q in g["slots"].items()
        ]
        stock = ";".join(f"{d['location']}:{d['qty']}" for d in displays)
        item = _row_to_item({**g, "displays": displays, "stock_details": stock})
        if item:
            items.append(item)
    return items


def _rows_to_items(rows: list[dict], fmt: str | None = None) -> list[DisplayItem]:
    if not rows:
        return []
    canonical = [_canonicalize_row(r) for r in rows]
    if fmt is None:
        fmt = _detect_format(canonical[0])
    if fmt == "warehouse":
        return _aggregate_warehouse_rows(canonical)
    items: list[DisplayItem] = []
    for row in canonical:
        item = _row_to_item(row)
        if item:
            items.append(item)
    return items


def _load_excel_rows(path: str | None = None) -> tuple[str, list[dict]]:
    path = path or DISPLAY_FILE
    if not os.path.isfile(path):
        return "warehouse", []

    try:
        import pandas as pd

        df = pd.read_excel(path)
        df.columns = [_normalize_header(c) for c in df.columns]
        resolved = _resolve_columns(list(df.columns))
        if not resolved:
            raise ValueError(
                f"{os.path.basename(path)} 列不匹配。需要 WarehouseName+Sku+ProductName+DisplayQty，"
                "或 stock_details + product_name"
            )
        fmt, colmap = resolved
        rows: list[dict] = []
        for _, series in df.iterrows():
            row = {field: series.iloc[idx] if idx < len(series) else "" for field, idx in colmap.items()}
            rows.append(row)
        return fmt, rows
    except ImportError:
        pass

    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    raw = list(ws.iter_rows(values_only=True))
    wb.close()
    if not raw:
        return "warehouse", []
    headers = [_normalize_header(h) for h in raw[0]]
    resolved = _resolve_columns(headers)
    if not resolved:
        raise ValueError(
            f"{os.path.basename(path)} 列不匹配。需要 WarehouseName+Sku+ProductName+DisplayQty，"
            "或 stock_details + product_name"
        )
    fmt, colmap = resolved
    rows: list[dict] = []
    for line in raw[1:]:
        if not line:
            continue
        row = {field: _cell_str(line, idx) for field, idx in colmap.items()}
        rows.append(row)
    return fmt, rows


def load_from_excel(path: str | None = None) -> list[DisplayItem]:
    global _last_load_error, _last_load_source
    path = path or DISPLAY_FILE
    if not os.path.isfile(path):
        _last_load_error = f"未找到 {os.path.basename(path)}，请从 SQL 导出 Excel 放到项目目录"
        _last_load_source = None
        return []
    try:
        fmt, rows = _load_excel_rows(path)
        items = _rows_to_items(rows, fmt)
        _last_load_error = None if items else f"{os.path.basename(path)} 中没有 Display 数据"
        _last_load_source = os.path.basename(path)
        return items
    except Exception as exc:
        _last_load_error = f"读取 {os.path.basename(path)} 失败: {exc}"
        _last_load_source = None
        return []


def _load_config() -> dict:
    path = CONFIG_FILE if os.path.isfile(CONFIG_FILE) else CONFIG_EXAMPLE
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _database_url(cfg: dict) -> str | None:
    env = os.environ.get("DISPLAY_DB_URL", "").strip()
    if env:
        return env
    return (cfg.get("database_url") or "").strip() or None


def _fetch_from_database(cfg: dict) -> list[DisplayItem]:
    url = _database_url(cfg)
    if not url:
        raise RuntimeError("未配置数据库连接（DISPLAY_DB_URL 或 display_config.json）")
    query = (cfg.get("query") or "").strip()
    if not query:
        raise RuntimeError("display_config.json 中缺少 query")

    from sqlalchemy import create_engine, text

    engine = create_engine(url, connect_args={"timeout": 30})
    rows: list[dict] = []
    with engine.connect() as conn:
        result = conn.execute(text(query))
        keys = list(result.keys())
        for row in result:
            raw = {keys[i]: row[i] for i in range(len(keys))}
            rows.append(_canonicalize_row(raw))
    fmt = _detect_format(rows[0]) if rows else "warehouse"
    return _rows_to_items(rows, fmt)


def _load_cache_file(path: str | None = None) -> list[DisplayItem]:
    path = path or CACHE_FILE
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    raw = payload.get("items", payload if isinstance(payload, list) else [])
    return _rows_to_items(raw)


def save_cache(items: list[DisplayItem], path: str | None = None) -> None:
    path = path or CACHE_FILE
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "items": [
            {
                "product_code": it.product_code,
                "product_name": it.product_name,
                "product_family": it.product_family,
                "stock_details": it.stock_details,
                "displays": [
                    {
                        "shop_id": s.shop_id,
                        "shop_label": s.shop_label,
                        "location": s.location,
                        "qty": s.qty,
                    }
                    for s in it.displays
                ],
            }
            for it in items
        ],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def refresh_from_database() -> list[DisplayItem]:
    global _display_cache, _last_load_error, _last_load_source
    cfg = _load_config()
    items = _fetch_from_database(cfg)
    save_cache(items)
    _display_cache = items
    _last_load_error = None
    _last_load_source = "database"
    return items


def load_display_items(*, prefer_db: bool = False) -> list[DisplayItem]:
    """优先读 display.xlsx，其次 display_cache.json，可选直连数据库。"""
    global _display_cache, _last_load_error, _last_load_source
    if _display_cache is not None and not prefer_db:
        return _display_cache

    if prefer_db:
        cfg = _load_config()
        if _database_url(cfg) and (cfg.get("query") or "").strip():
            try:
                return refresh_from_database()
            except Exception as exc:
                _last_load_error = str(exc)
                print(f"Display 数据库加载失败: {exc}")

    items = load_from_excel()
    if items:
        _display_cache = items
        return items

    items = _load_cache_file()
    _display_cache = items
    if items:
        _last_load_source = "display_cache.json"
        return items

    if _last_load_error is None:
        _last_load_error = (
            "请把 SQL 结果导出为 display.xlsx 放到项目目录（参考 display.sql）"
        )
    return items


def reload_display_items(*, prefer_db: bool = False) -> list[DisplayItem]:
    global _display_cache
    _display_cache = None
    return load_display_items(prefer_db=prefer_db)


def last_load_error() -> str | None:
    return _last_load_error


def last_load_source() -> str | None:
    return _last_load_source


def filter_items(items: list[DisplayItem], shop_id: str, query: str = "") -> list[DisplayItem]:
    q = _normalize_key(query)
    out: list[DisplayItem] = []
    for it in items:
        if shop_id != "all" and it.display_qty_for_shop(shop_id) <= 0:
            continue
        if q:
            blob = " ".join([it.product_code, it.product_name, it.product_family]).lower()
            if q not in blob:
                continue
        out.append(it)
    out.sort(key=lambda x: (x.product_family.lower(), x.product_name.lower()))
    return out


def group_by_family(items: list[DisplayItem]) -> list[tuple[str, list[DisplayItem]]]:
    groups: dict[str, list[DisplayItem]] = {}
    for it in items:
        groups.setdefault(it.product_family or "未分类", []).append(it)
    return sorted(groups.items(), key=lambda x: x[0].lower())


def shop_stats(items: list[DisplayItem], templates: list[dict]) -> dict[str, dict[str, int]]:
    stats: dict[str, dict[str, int]] = {}
    for shop in SHOPS:
        sid = shop["id"]
        filtered = filter_items(items, sid)
        modeled = sum(1 for it in filtered if match_template_index(it, templates) >= 0)
        stats[sid] = {"total": len(filtered), "modeled": modeled}
    return stats


def match_template_index(item: DisplayItem, templates: list[dict]) -> int:
    name = _normalize_key(item.product_name)
    code = _normalize_key(item.product_code)
    family = _normalize_key(item.product_family)
    for i, tpl in enumerate(templates):
        tid = _normalize_key(tpl.get("id", ""))
        tfam = _normalize_key(tpl.get("product_family", ""))
        if code and (code == tid or code == tfam):
            return i
        if name and (name == tid or name == tfam):
            return i
    for i, tpl in enumerate(templates):
        tid = _normalize_key(tpl.get("id", ""))
        tfam = _normalize_key(tpl.get("product_family", ""))
        if family and (family == tid or family == tfam):
            return i
        if name and (name in tid or tid in name):
            return i
        if family and (family in tfam or tfam in family):
            return i
    return -1
