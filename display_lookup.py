"""Display 库数据层：抓取程序写 data/display.xlsx，模板编辑器只读可视化。

架构（和库存 main_gui 项目一样）：
  grab_display.bat        → Main：SQL 抓数据 → data/display.xlsx
  start_furniture_sim.bat → 可视化：furniture_sim 读 Excel 显示 Display 大库
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from urllib.parse import quote_plus
from datetime import datetime, timezone
from typing import Any

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
GRABBER_CONFIG = os.path.join(SCRIPT_DIR, "grabber_config.json")
GRABBER_CONFIG_EXAMPLE = os.path.join(SCRIPT_DIR, "grabber_config.example.json")
CACHE_FILE = os.path.join(SCRIPT_DIR, "display_cache.json")
DEFAULT_EXCEL = os.path.join(SCRIPT_DIR, "data", "display.xlsx")
LEGACY_EXCEL = os.path.join(SCRIPT_DIR, "display.xlsx")
DEFAULT_SQL = os.path.join(SCRIPT_DIR, "sql", "display.sql")
DEFAULT_BLACKLIST = os.path.join(SCRIPT_DIR, "data", "display_blacklist.xlsx")
DEFAULT_BLACKLIST_CSV = os.path.join(SCRIPT_DIR, "data", "display_blacklist.csv")
EXAMPLE_BLACKLIST_CSV = os.path.join(SCRIPT_DIR, "data", "display_blacklist.example.csv")

from region_config import (  # noqa: E402
    display_excel_path,
    get_active_region,
    has_multi_region_config,
    legacy_display_excel_candidates,
    load_region_profile,
    merge_region_config,
    region_database_url,
    shops_for_region,
    weekly_sales_excel_path,
)


def reload_shops(cfg: dict | None = None) -> list[dict[str, Any]]:
    """按 active_region 加载门店匹配规则（config/regions/*.json）。"""
    return shops_for_region(get_active_region(cfg or load_grabber_config()), cfg)


# 门店：按 Stock Details / Branch 名称匹配；切换区域后调用 reload_shops()
SHOPS: list[dict[str, Any]] = []

# Excel / SQL 列名别名（不区分大小写，空格会折叠）
_COL_ALIASES: dict[str, tuple[str, ...]] = {
    "warehouse_name": ("warehouse_name", "warehousename", "warehouse name", "warehouse"),
    "product_code": ("product_code", "productcode", "code", "sku", "product code", "item code"),
    "product_name": ("product_name", "productname", "product name", "title", "description"),
    "product_family": (
        "product_family",
        "productfamily",
        "family",
        "product family",
        "family name",
        "familyname",
        "range",
        "collection",
        "产品系列",
        "系列",
    ),
    "sub_product_family": (
        "sub_product_family",
        "subproductfamily",
        "sub product family",
        "subfamily",
        "sub family",
        "product line",
        "line",
    ),
    "display_qty": ("display_qty", "displayqty", "display qty", "quantity", "qty"),
    "image_url": (
        "image_url",
        "imageurl",
        "image url",
        "imagepath",
        "image path",
        "image",
        "picture",
        "photo",
        "thumbnail",
    ),
    "stock_details": ("stock_details", "stockdetails", "stock details", "stock", "display stock", "inventory"),
    "is_discontinued": ("is_discontinued", "isdiscontinued", "is discontinued", "discontinued"),
    "stock_status": ("stock_status", "stockstatus", "stock status"),
}

_display_cache: list["DisplayItem"] | None = None
_display_items_all: list["DisplayItem"] | None = None
_last_load_error: str | None = None
_last_load_source: str | None = None
_last_family_column: str | None = None
_last_sql_file: str | None = None


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
    sub_product_family: str = ""
    image_url: str = ""
    stock_details: str = ""
    is_discontinued: bool = False
    displays: list[DisplaySlot] = field(default_factory=list)
    storages: list[DisplaySlot] = field(default_factory=list)

    @property
    def key(self) -> str:
        return self.product_code or self.product_name

    def _qty_for_shop(self, slots: list[DisplaySlot], shop_id: str) -> int:
        if shop_id == "all":
            return sum(s.qty for s in slots)
        return sum(s.qty for s in slots if s.shop_id == shop_id)

    def display_qty_for_shop(self, shop_id: str) -> int:
        return self._qty_for_shop(self.displays, shop_id)

    def storage_qty_for_shop(self, shop_id: str) -> int:
        return self._qty_for_shop(self.storages, shop_id)

    def shops_with_display(self) -> set[str]:
        return {s.shop_id for s in self.displays if s.qty > 0}

    def shops_with_storage(self) -> set[str]:
        return {s.shop_id for s in self.storages if s.qty > 0}


def _normalize_key(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _normalize_header(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _cell_value(val) -> str:
    """Excel/SQL 单元格 → 字符串；None / NaN / 'nan' 视为空。"""
    if val is None:
        return ""
    if isinstance(val, float):
        import math

        if math.isnan(val):
            return ""
    s = str(val).strip()
    if s.lower() in ("nan", "none", "null", "#n/a", "n/a"):
        return ""
    return s


def _cell_bool(val) -> bool:
    """Excel/SQL 布尔/位字段 → bool。"""
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        try:
            import math

            if isinstance(val, float) and math.isnan(val):
                return False
        except Exception:
            pass
        return bool(val)
    s = _cell_value(val).lower()
    return s in ("1", "true", "yes", "y", "是")


def _canonicalize_row(raw: dict) -> dict:
    """把 Excel / SQL 任意列名映射到标准字段名。"""
    normalized = {_normalize_header(k): v for k, v in raw.items()}
    out: dict = {}
    for field, aliases in _COL_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                out[field] = _cell_value(normalized[alias])
                break
    return out


def _header_is_sub_family(header: str) -> bool:
    h = _normalize_header(header)
    compact = h.replace(" ", "")
    return h.startswith("sub") or " sub" in f" {h} " or compact.startswith("subproduct")


def _header_is_product_family(header: str) -> bool:
    h = _normalize_header(header)
    if _header_is_sub_family(h):
        return False
    if h in _COL_ALIASES["product_family"]:
        return True
    compact = h.replace(" ", "")
    if compact in ("productfamily", "familyname", "family"):
        return True
    if "系列" in h:
        return True
    if h.endswith("family") and "name" not in h.replace("family", ""):
        return True
    return False


def _infer_family_column_indices(headers: list[str]) -> tuple[int | None, int | None]:
    family_idx = sub_idx = None
    for i, h in enumerate(headers):
        if sub_idx is None and _header_is_sub_family(h):
            sub_idx = i
    for i, h in enumerate(headers):
        if family_idx is None and _header_is_product_family(h):
            family_idx = i
    return family_idx, sub_idx


def _resolve_family_name(family: str, name: str, code: str) -> str:
    """只用 Excel/SQL 的 ProductFamily；缺失时标为未分类，不用 SKU/产品名猜测。"""
    if family:
        return family
    return "未分类"


def _resolve_sub_family_name(sub_family: str, name: str, code: str) -> str:
    if sub_family:
        return sub_family
    return name or code or "未分类"


def family_is_sku_placeholder(family: str, sku: str) -> bool:
    """系列名视为未分配：空、未分类、或与 SKU 相同（测绘占位）。"""
    fam = _cell_value(family)
    sku_clean = _cell_value(sku)
    if not fam:
        return True
    if fam in ("未分类", "unnamed"):
        return True
    return fam == sku_clean


def infer_family_from_product_name(product_name: str, sku: str = "") -> str:
    """Display 无 ProductFamily 时，从产品名首词推断（如 Heyfield Queen ...）。"""
    pn = _cell_value(product_name)
    if not pn:
        return ""
    first = pn.split()[0]
    if len(first) < 3 or re.match(r"^\d", first):
        return ""
    if first.lower() in ("not", "display", "clearance", "discontinued", "the"):
        return ""
    if family_is_sku_placeholder(first, sku):
        return ""
    return first


def effective_family_from_display_item(item: DisplayItem) -> str:
    """从 Display 项解析可用系列名（列值 → 产品名推断 → 子系列）。"""
    sku = _cell_value(item.product_code or item.product_name)
    fam = _cell_value(item.product_family)
    if fam and fam not in ("未分类",) and not family_is_sku_placeholder(fam, sku):
        return fam
    inferred = infer_family_from_product_name(item.product_name, sku)
    if inferred:
        return inferred
    sub = _cell_value(item.sub_product_family)
    if sub and not family_is_sku_placeholder(sub, sku):
        return sub
    return ""


def _family_data_score(items: list[DisplayItem]) -> int:
    """优先选用真正带有 ProductFamily 数据的 Excel。"""
    score = 0
    for it in items:
        fam = it.product_family or ""
        if not fam or fam == "未分类":
            continue
        if fam == it.product_code:
            continue
        first = (it.product_name or "").split(" ")[0]
        if fam == first and re.match(r"^\d{3}-\d{3}$", fam):
            continue
        score += 1
    return score


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
    # 宽松匹配 family 列
    for i, h in enumerate(headers):
        if "sub_product_family" not in mapping and _header_is_sub_family(h):
            mapping["sub_product_family"] = i
        elif "product_family" not in mapping and _header_is_product_family(h):
            mapping["product_family"] = i
    return fmt, mapping


def _location_patterns(field: str, default: tuple[str, ...]) -> tuple[str, ...]:
    profile = load_region_profile(get_active_region())
    raw = profile.get(field) or list(default)
    if isinstance(raw, str):
        raw = [raw]
    patterns = tuple(str(p).strip().lower() for p in raw if str(p).strip())
    return patterns or default


def display_location_patterns() -> tuple[str, ...]:
    return _location_patterns("display_location_patterns", ("display",))


def storage_location_patterns() -> tuple[str, ...]:
    return _location_patterns("storage_location_patterns", ("storage",))


def classify_placement_location(location: str) -> str | None:
    """门店摆场库位类型：display / storage / None。"""
    low = str(location or "").lower()
    if not low or "no longer available" in low:
        return None
    if any(p in low for p in storage_location_patterns()):
        return "storage"
    if any(p in low for p in display_location_patterns()):
        return "display"
    return None


def is_display_location(location: str) -> bool:
    return classify_placement_location(location) == "display"


def is_storage_location(location: str) -> bool:
    return classify_placement_location(location) == "storage"


def shop_id_for_location(location: str) -> str:
    low = location.lower()
    for shop in reload_shops():
        if shop["id"] in ("all", "other"):
            continue
        if any(p in low for p in shop["patterns"]):
            return shop["id"]
    return "other"


def shop_label(shop_id: str) -> str:
    for shop in reload_shops():
        if shop["id"] == shop_id:
            return shop["label"]
    return shop_id


def parse_stock_details(text: str) -> list[DisplaySlot]:
    displays, _storages = parse_placement_stock_details(text)
    return displays


def parse_placement_stock_details(text: str) -> tuple[list[DisplaySlot], list[DisplaySlot]]:
    """解析 stock_details 字符串，按 Display / Storage 分类（与 SQL 抓取同一套规则）。"""
    displays: list[DisplaySlot] = []
    storages: list[DisplaySlot] = []
    if not text:
        return displays, storages
    for part in str(text).split(";"):
        part = part.strip()
        if not part or ":" not in part:
            continue
        loc, qty_s = part.rsplit(":", 1)
        loc = loc.strip()
        kind = classify_placement_location(loc)
        if kind is None:
            continue
        try:
            qty = int(float(qty_s.strip()))
        except (TypeError, ValueError):
            qty = 0
        if qty <= 0:
            continue
        sid = shop_id_for_location(loc)
        slot = DisplaySlot(sid, shop_label(sid), loc, qty)
        if kind == "storage":
            storages.append(slot)
        else:
            displays.append(slot)
    return displays, storages


def _cell_str(row: tuple, idx: int | None) -> str:
    if idx is None or idx >= len(row):
        return ""
    return _cell_value(row[idx])


def _row_to_item(row: dict) -> DisplayItem | None:
    code = _cell_value(row.get("product_code") or row.get("sku") or row.get("code"))
    name = _cell_value(row.get("product_name") or row.get("name") or row.get("title"))
    family = _cell_value(row.get("product_family") or row.get("family"))
    sub_family = _cell_value(row.get("sub_product_family") or row.get("subfamily"))
    image_url = _cell_value(row.get("image_url") or row.get("imageurl") or row.get("imagepath"))
    stock = _cell_value(row.get("stock_details") or row.get("stock") or row.get("Stock Details"))
    is_discontinued = _cell_bool(row.get("is_discontinued"))
    if not name and not code:
        return None
    family = _resolve_family_name(family, name, code)
    sub_family = _resolve_sub_family_name(sub_family, name, code)
    raw_displays = row.get("displays")
    raw_storages = row.get("storages")
    if isinstance(raw_displays, list) and raw_displays:
        display_slots = [
            DisplaySlot(
                str(d.get("shop_id", "other")),
                str(d.get("shop_label", shop_label(str(d.get("shop_id", "other"))))),
                str(d.get("location", "")),
                int(d.get("qty", 0) or 0),
            )
            for d in raw_displays
            if int(d.get("qty", 0) or 0) > 0
        ]
    else:
        display_slots, _parsed_storage = parse_placement_stock_details(stock)
        if not raw_storages:
            raw_storages = _parsed_storage
    if isinstance(raw_storages, list) and raw_storages:
        storage_slots = [
            DisplaySlot(
                str(d.get("shop_id", "other")),
                str(d.get("shop_label", shop_label(str(d.get("shop_id", "other"))))),
                str(d.get("location", "")),
                int(d.get("qty", 0) or 0),
            )
            for d in raw_storages
            if int(d.get("qty", 0) or 0) > 0
        ]
    else:
        storage_slots = []
    if not display_slots and not storage_slots:
        return None
    return DisplayItem(
        code or name,
        name or code,
        family,
        sub_family,
        image_url,
        stock,
        is_discontinued,
        display_slots,
        storage_slots,
    )


def _aggregate_warehouse_rows(rows: list[dict]) -> list[DisplayItem]:
    """多行（每行一个仓库+产品）合并为 DisplayItem。"""
    groups: dict[str, dict] = {}
    for raw in rows:
        row = raw if "warehouse_name" in raw else _canonicalize_row(raw)
        code = _cell_value(row.get("product_code"))
        name = _cell_value(row.get("product_name"))
        warehouse = _cell_value(row.get("warehouse_name"))
        try:
            qty = int(float(row.get("display_qty") or 0))
        except (TypeError, ValueError):
            qty = 0
        if not warehouse or qty <= 0 or (not code and not name):
            continue
        key = _normalize_key(code or name)
        family = _cell_value(row.get("product_family"))
        sub_family = _cell_value(row.get("sub_product_family"))
        image_url = _cell_value(row.get("image_url"))
        is_discontinued = _cell_bool(row.get("is_discontinued"))
        if key not in groups:
            groups[key] = {
                "product_code": code or name,
                "product_name": name or code,
                "product_family": _resolve_family_name(family, name, code),
                "sub_product_family": _resolve_sub_family_name(sub_family, name, code),
                "image_url": image_url,
                "is_discontinued": is_discontinued,
                "display_slots": {},
                "storage_slots": {},
            }
        else:
            if family:
                groups[key]["product_family"] = _resolve_family_name(
                    family, groups[key]["product_name"], groups[key]["product_code"]
                )
            if sub_family:
                groups[key]["sub_product_family"] = sub_family
            if image_url and not groups[key].get("image_url"):
                groups[key]["image_url"] = image_url
            if is_discontinued:
                groups[key]["is_discontinued"] = True
        sid = shop_id_for_location(warehouse)
        slot_key = (sid, warehouse)
        kind = classify_placement_location(warehouse) or "display"
        bucket = "storage_slots" if kind == "storage" else "display_slots"
        groups[key][bucket][slot_key] = groups[key][bucket].get(slot_key, 0) + qty

    items: list[DisplayItem] = []
    for g in groups.values():
        displays = [
            {"shop_id": sid, "shop_label": shop_label(sid), "location": loc, "qty": q}
            for (sid, loc), q in g["display_slots"].items()
        ]
        storages = [
            {"shop_id": sid, "shop_label": shop_label(sid), "location": loc, "qty": q}
            for (sid, loc), q in g["storage_slots"].items()
        ]
        stock_parts = [f"{d['location']}:{d['qty']}" for d in displays + storages]
        stock = ";".join(stock_parts)
        item = _row_to_item({**g, "displays": displays, "storages": storages, "stock_details": stock})
        if item:
            items.append(item)
    return items


def _rows_to_items(rows: list[dict], fmt: str | None = None, *, apply_blacklist: bool = True) -> list[DisplayItem]:
    if not rows:
        return []
    canonical = [_canonicalize_row(r) for r in rows]
    if fmt is None:
        fmt = _detect_format(canonical[0])
    if fmt == "warehouse":
        items = _aggregate_warehouse_rows(canonical)
    else:
        items = []
        for row in canonical:
            item = _row_to_item(row)
            if item:
                items.append(item)
    if apply_blacklist:
        return filter_blacklisted(items)
    return items


_BLACKLIST_ALIASES = {
    "sku": ("sku", "product_code", "productcode", "code", "product code", "item code"),
    "product_name": ("product_name", "productname", "name", "product name", "title"),
}


def resolve_blacklist_paths(cfg: dict | None = None) -> list[str]:
    cfg = cfg or load_grabber_config()
    paths: list[str] = []
    if cfg.get("blacklist_file"):
        paths.append(_resolve_path(cfg["blacklist_file"]))
    paths.extend([
        DEFAULT_BLACKLIST,
        DEFAULT_BLACKLIST_CSV,
        EXAMPLE_BLACKLIST_CSV,
        os.path.join(SCRIPT_DIR, "display_blacklist.xlsx"),
    ])
    seen: set[str] = set()
    out: list[str] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def blacklist_files_revision() -> str:
    """黑名单文件修改时间（画廊布局缓存用，改 CSV 后自动刷新）。"""
    parts: list[str] = []
    for path in resolve_blacklist_paths():
        if os.path.isfile(path):
            parts.append(f"{os.path.basename(path)}:{int(os.path.getmtime(path))}")
    return "|".join(parts)


def _blacklist_key(value) -> str:
    """黑名单 SKU 归一化（去空格、Excel 数字格式）。"""
    s = _cell_value(value)
    if not s:
        return ""
    if re.fullmatch(r"\d+\.0+", s):
        s = s.split(".", 1)[0]
    return _normalize_key(s)


def _blacklist_add_sku(blocked: set[str], value) -> None:
    key = _blacklist_key(value)
    if key:
        blocked.add(key)
        compact = re.sub(r"[^a-z0-9]", "", key)
        if compact:
            blocked.add(compact)


def _blacklist_read_csv_rows(path: str) -> list[list[str]]:
    import csv

    last_err: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "gbk", "cp936", "latin-1"):
        try:
            with open(path, "r", encoding=encoding, newline="") as f:
                return list(csv.reader(f))
        except UnicodeDecodeError as exc:
            last_err = exc
            continue
    if last_err is not None:
        raise last_err
    return []


def load_blacklist(cfg: dict | None = None) -> set[str]:
    """读取黑名单 SKU（支持仅一列 SKU，也兼容产品名列）。"""
    blocked: set[str] = set()
    for path in resolve_blacklist_paths(cfg):
        if not os.path.isfile(path):
            continue
        if path.lower().endswith(".csv"):
            rows = _blacklist_read_csv_rows(path)
            if not rows:
                continue
            headers = [_normalize_header(h) for h in rows[0]]
            sku_col = name_col = None
            for i, h in enumerate(headers):
                if h in _BLACKLIST_ALIASES["sku"]:
                    sku_col = i
                if h in _BLACKLIST_ALIASES["product_name"]:
                    name_col = i
            data_start = 1
            # 无表头：整文件每行第一列当作 SKU
            if sku_col is None and name_col is None:
                if len(headers) == 1:
                    sku_col = 0
                    data_start = 0
                elif all(_normalize_key(h) for h in rows[0]):
                    sku_col = 0
                    data_start = 0
            elif sku_col is None and len(headers) == 1:
                sku_col = 0
            for line in rows[data_start:]:
                if not line:
                    continue
                if sku_col is not None and sku_col < len(line):
                    _blacklist_add_sku(blocked, line[sku_col])
                if name_col is not None and name_col < len(line):
                    _blacklist_add_sku(blocked, line[name_col])
            continue
        try:
            import pandas as pd

            df = pd.read_excel(path)
            df.columns = [_normalize_header(c) for c in df.columns]
            for field, aliases in _BLACKLIST_ALIASES.items():
                for alias in aliases:
                    if alias in df.columns:
                        for val in df[alias].dropna():
                            key = _normalize_key(str(val))
                            if key:
                                blocked.add(key)
                        break
            continue
        except ImportError:
            pass
        from openpyxl import load_workbook

        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        raw = list(ws.iter_rows(values_only=True))
        wb.close()
        if not raw:
            continue
        headers = [_normalize_header(h) for h in raw[0]]
        sku_col = name_col = None
        for i, h in enumerate(headers):
            if h in _BLACKLIST_ALIASES["sku"]:
                sku_col = i
            if h in _BLACKLIST_ALIASES["product_name"]:
                name_col = i
        data_start = 1
        if sku_col is None and name_col is None and len(headers) == 1:
            sku_col = 0
            data_start = 0
        elif sku_col is None and len(headers) == 1:
            sku_col = 0
        for line in raw[data_start:]:
            if sku_col is not None and sku_col < len(line) and line[sku_col]:
                _blacklist_add_sku(blocked, line[sku_col])
            if name_col is not None and name_col < len(line) and line[name_col]:
                _blacklist_add_sku(blocked, line[name_col])
    return blocked


def is_blacklisted(item: DisplayItem, blocked: set[str]) -> bool:
    if not blocked:
        return False
    keys = {_blacklist_key(item.product_code), _blacklist_key(item.product_name)}
    keys.discard("")
    for key in keys:
        if key in blocked:
            return True
        compact = re.sub(r"[^a-z0-9]", "", key)
        if compact and compact in blocked:
            return True
    return False


def blacklist_status(cfg: dict | None = None) -> tuple[int, str, list[str]]:
    """返回 (SKU 数量, 主文件名, 实际读到的文件列表)。"""
    blocked = load_blacklist(cfg)
    used = [p for p in resolve_blacklist_paths(cfg) if os.path.isfile(p)]
    names = [os.path.basename(p) for p in used]
    primary = names[0] if names else "未找到黑名单文件"
    return len(blocked), primary, names


def filter_blacklisted(items: list[DisplayItem], cfg: dict | None = None) -> list[DisplayItem]:
    blocked = load_blacklist(cfg)
    if not blocked:
        return items
    return [it for it in items if not is_blacklisted(it, blocked)]


def _apply_family_fields(
    row: dict,
    values: tuple,
    headers: list[str],
    family_idx: int | None,
    sub_idx: int | None,
) -> None:
    if family_idx is not None and family_idx < len(values):
        row["product_family"] = _cell_value(values[family_idx])
    if sub_idx is not None and sub_idx < len(values):
        row["sub_product_family"] = _cell_value(values[sub_idx])


def _load_excel_rows(path: str) -> tuple[str, list[dict]]:
    global _last_family_column
    if not os.path.isfile(path):
        return "warehouse", []

    try:
        import pandas as pd

        df = pd.read_excel(path)
        df.columns = [_normalize_header(c) for c in df.columns]
        headers = list(df.columns)
        resolved = _resolve_columns(headers)
        if not resolved:
            raise ValueError(
                f"{os.path.basename(path)} 列不匹配。需要 WarehouseName+Sku+ProductName+DisplayQty（可选 ProductFamily/SubProductFamily），"
                "或 stock_details + product_name"
            )
        fmt, colmap = resolved
        family_idx, sub_idx = _infer_family_column_indices(headers)
        if family_idx is not None:
            _last_family_column = headers[family_idx]
        elif "product_family" in colmap:
            _last_family_column = headers[colmap["product_family"]]
        rows: list[dict] = []
        for _, series in df.iterrows():
            row = {
                field: _cell_value(series.iloc[idx] if idx < len(series) else None)
                for field, idx in colmap.items()
            }
            _apply_family_fields(row, tuple(series.tolist()), headers, family_idx, sub_idx)
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
    family_idx, sub_idx = _infer_family_column_indices(headers)
    if family_idx is not None:
        _last_family_column = headers[family_idx]
    elif "product_family" in colmap:
        _last_family_column = headers[colmap["product_family"]]
    rows: list[dict] = []
    for line in raw[1:]:
        if not line:
            continue
        row = {field: _cell_str(line, idx) for field, idx in colmap.items()}
        _apply_family_fields(row, line, headers, family_idx, sub_idx)
        rows.append(row)
    return fmt, rows


def load_from_excel(path: str | None = None) -> list[DisplayItem]:
    global _last_load_error, _last_load_source, _last_family_column
    candidates = [path] if path else resolve_display_excel_paths()
    last_exc = None
    best_items: list[DisplayItem] = []
    best_score = -1
    best_source: str | None = None
    for candidate in candidates:
        if not candidate or not os.path.isfile(candidate):
            continue
        try:
            fmt, rows = _load_excel_rows(candidate)
            items_all = _rows_to_items(rows, fmt, apply_blacklist=False)
            global _display_items_all
            _display_items_all = items_all
            items = filter_blacklisted(items_all)
            if not items:
                _last_load_error = f"{os.path.basename(candidate)} 中没有 Display 数据"
                continue
            score = _family_data_score(items)
            if score > best_score:
                best_score = score
                best_items = items
                best_source = candidate
        except Exception as exc:
            last_exc = exc
            _last_load_error = f"读取 {os.path.basename(candidate)} 失败: {exc}"
    if best_items and best_source:
        _last_load_source = display_source_label(best_source)
        if best_score <= 0:
            col = _last_family_column or "ProductFamily"
            _last_load_error = (
                f"未读到有效的 {col} 数据，界面将显示「未分类」。"
                "请确认 Excel 有 ProductFamily 列且已填写，或重新 grab_display.bat 抓取。"
            )
        else:
            _last_load_error = None
        return best_items
    if not candidates or not any(os.path.isfile(p) for p in candidates if p):
        _last_load_error = "未找到 display.xlsx，请先运行 grab_display.bat 抓取数据"
    elif last_exc:
        _last_load_error = str(last_exc)
    _last_load_source = None
    return []


def load_grabber_config() -> dict:
    for path in (GRABBER_CONFIG, GRABBER_CONFIG_EXAMPLE):
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    return {}


def save_grabber_config(cfg: dict) -> None:
    path = GRABBER_CONFIG
    existing: dict = {}
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except (OSError, json.JSONDecodeError):
            existing = {}
    merged = {**existing, **cfg}
    region_id = get_active_region(merged)
    db_url = str(merged.get("database_url") or "").strip()
    if db_url:
        regions = dict(merged.get("regions") or existing.get("regions") or {})
        section = dict(regions.get(region_id) or {})
        section["database_url"] = db_url
        if merged.get("sql_folder"):
            section["sql_folder"] = merged["sql_folder"]
        if merged.get("output_folder"):
            section["output_folder"] = merged["output_folder"]
        if merged.get("image_base_url"):
            section["image_base_url"] = merged["image_base_url"]
        regions[region_id] = section
        merged["regions"] = regions
    with open(path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    reload_shops(merged)


def _resolve_path(path: str) -> str:
    if not path:
        return SCRIPT_DIR
    return path if os.path.isabs(path) else os.path.join(SCRIPT_DIR, path)


def display_source_label(path: str | None) -> str:
    """状态栏用：相对项目根的路径，便于区分 data/nz vs data/au。"""
    if not path:
        return "display.xlsx"
    try:
        return os.path.relpath(path, SCRIPT_DIR).replace("\\", "/")
    except ValueError:
        return os.path.basename(path)


def build_runtime_config(cfg: dict | None = None) -> dict:
    """合并配置并解析 sql / 输出路径（含 active_region）。"""
    base = merge_region_config(cfg)
    sql_folder = base.get("sql_folder") or "sql"
    sql_folder_abs = _resolve_path(sql_folder)
    sql_file = base.get("sql_file")
    if not sql_file:
        sql_file = os.path.join(sql_folder_abs, "display.sql")
    else:
        sql_file = _resolve_path(sql_file)
    base["sql_file"] = _resolve_existing_sql_file(sql_file)

    output_folder = base.get("output_folder") or "data"
    output_folder_abs = _resolve_path(output_folder)
    if not base.get("output_excel"):
        base["output_excel"] = os.path.join(output_folder_abs, "display.xlsx")
    else:
        base["output_excel"] = _resolve_path(base["output_excel"])
    if not base.get("output_json"):
        base["output_json"] = os.path.join(output_folder_abs, "display_cache.json")
    else:
        base["output_json"] = _resolve_path(base["output_json"])
    return base


def resolve_display_excel_paths() -> list[str]:
    """仅当前区域 data/{region}/display.xlsx（不读 legacy data/display.xlsx）。"""
    cfg = load_grabber_config()
    return [display_excel_path(cfg)]


def resolve_cache_path() -> str:
    """当前区域 display_cache.json；多区域时不回退根目录 NZ 缓存。"""
    cfg = build_runtime_config()
    path = cfg.get("output_json")
    if path:
        return path if os.path.isabs(path) else os.path.join(SCRIPT_DIR, path)
    if has_multi_region_config(load_grabber_config()):
        folder = cfg.get("output_folder") or "data"
        folder_abs = folder if os.path.isabs(folder) else os.path.join(SCRIPT_DIR, folder)
        return os.path.join(folder_abs, "display_cache.json")
    data_json = os.path.join(SCRIPT_DIR, "data", "display_cache.json")
    if os.path.isfile(data_json):
        return data_json
    return CACHE_FILE


_IMAGE_URL_PREFIXES = (
    "https://ierpapi.ifurniture.co.nz/",
    "https://ierpapi.ifurniture.com.au/",
    "https://ierpapi.ifurniture.ca/",
)


def _sql_path_variants(path: str) -> list[str]:
    """同一条 SQL 的 .sql / .txt 变体（Windows 上有人用记事本存成 .txt）。"""
    folder = os.path.dirname(path) or "."
    name = os.path.basename(path) or "display.sql"
    stem, _ext = os.path.splitext(name)
    if not stem:
        return [path]
    out: list[str] = []
    for suffix in (".sql", ".txt"):
        candidate = os.path.join(folder, stem + suffix)
        if candidate not in out:
            out.append(candidate)
    if path not in out:
        out.insert(0, path)
    return out


def _resolve_existing_sql_file(path: str) -> str:
    """若 .sql 不存在则尝试同名的 .txt。"""
    abs_path = path if os.path.isabs(path) else _resolve_path(path)
    for candidate in _sql_path_variants(abs_path):
        if os.path.isfile(candidate):
            return candidate
    return abs_path


def _patch_sql_for_region(query: str, cfg: dict) -> str:
    """把 SQL 里的图片域名换成当前区域的 image_base_url（支持 {{IMAGE_BASE_URL}}）。"""
    merged = merge_region_config(cfg)
    target = str(merged.get("image_base_url") or "").strip()
    if not target:
        profile = (merged.get("_region_profile") or {}) if isinstance(merged.get("_region_profile"), dict) else {}
        target = str(profile.get("image_base_url") or "").strip()
    if not target:
        return query
    if not target.endswith("/"):
        target += "/"
    out = query.replace("{{IMAGE_BASE_URL}}", target)
    for prefix in _IMAGE_URL_PREFIXES:
        if prefix != target:
            out = out.replace(prefix, target)
    return out


def load_sql_query(cfg: dict | None = None, *, path: str | None = None) -> str:
    cfg = build_runtime_config(cfg)
    path = path or cfg["sql_file"]
    if not os.path.isfile(path):
        alts = [p for p in _sql_path_variants(path) if p != path]
        hint = f"（也可尝试 {os.path.basename(alts[0])}）" if alts else ""
        raise FileNotFoundError(f"找不到 SQL 文件: {path}{hint}")
    with open(path, "r", encoding="utf-8") as f:
        lines = [ln for ln in f.readlines() if not ln.strip().startswith("--")]
    query = "\n".join(lines).strip()
    if not query:
        raise ValueError(f"SQL 文件为空: {path}")
    return _patch_sql_for_region(query, cfg)


def _is_schema_sql_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return (
        "invalid object name" in msg
        or "invalid column name" in msg
        or "208," in msg
        or "207," in msg
    )


def _sql_fallback_paths(primary_path: str, cfg: dict | None = None) -> list[str]:
    """按区域目录 → 其它区域 → 根 sql/ 顺序尝试（文件缺失时不报错，由调用方跳过）。"""
    from region_config import SUPPORTED_REGIONS, default_sql_folder, get_active_region, normalize_region_id

    filename = os.path.basename(primary_path) or "display.sql"
    region_id = normalize_region_id(get_active_region(cfg or load_grabber_config()))
    ordered: list[str] = []

    def add(path: str) -> None:
        for variant in _sql_path_variants(path):
            if variant not in ordered:
                ordered.append(variant)

    add(primary_path)
    folder = os.path.dirname(primary_path) or _resolve_path("sql")
    for name in (filename, "display.sql", "display.minimal.sql", "weekly_sales.sql"):
        add(os.path.join(folder, name))

    for rid in [region_id] + [r for r in SUPPORTED_REGIONS if r != region_id]:
        reg_dir = _resolve_path(default_sql_folder(rid))
        add(os.path.join(reg_dir, filename))
        if filename not in ("display.sql", "display.minimal.sql", "display.txt", "display.minimal.txt"):
            add(os.path.join(reg_dir, "display.sql"))
        add(os.path.join(reg_dir, "display.minimal.sql"))
        add(os.path.join(reg_dir, "weekly_sales.sql"))

    root_sql = os.path.join(SCRIPT_DIR, "sql")
    add(os.path.join(root_sql, filename))
    add(os.path.join(root_sql, "display.sql"))
    add(os.path.join(root_sql, "display.minimal.sql"))
    add(os.path.join(root_sql, "weekly_sales.sql"))
    return ordered


def last_sql_file() -> str | None:
    return _last_sql_file


def _load_config() -> dict:
    return load_grabber_config()


def parse_mssql_url(url: str) -> dict:
    """从 SQLAlchemy 连接字符串解析服务器/用户名/密码/库名。"""
    url = (url or "").strip()
    if not url:
        return {}
    try:
        from sqlalchemy.engine.url import make_url

        parsed = make_url(url)
        return {
            "db_server": parsed.host or "",
            "db_port": parsed.port or 1433,
            "db_user": parsed.username or "",
            "db_password": parsed.password or "",
            "db_name": (parsed.database or "").lstrip("/"),
        }
    except Exception:
        return {}


def normalize_db_config(cfg: dict) -> dict:
    """合并旧版 database_url 与分项字段，分项优先。"""
    merged = dict(cfg)
    url = (merged.get("database_url") or "").strip()
    if url:
        for key, value in parse_mssql_url(url).items():
            if not str(merged.get(key) or "").strip() and value:
                merged[key] = value
    if not merged.get("db_port"):
        merged["db_port"] = 1433
    return merged


def build_database_url(cfg: dict) -> str | None:
    """优先使用区域环境变量 / database_url（与 main_gui 一致）；分项字段仅作备用。"""
    url = region_database_url(cfg)
    if url:
        return url

    merged = normalize_db_config(cfg)
    server = (merged.get("db_server") or "").strip()
    user = (merged.get("db_user") or "").strip()
    password = merged.get("db_password")
    db_name = (merged.get("db_name") or "").strip()
    if server and user and password not in (None, "") and db_name:
        port = int(merged.get("db_port") or 1433)
        enc_user = quote_plus(user)
        enc_pass = quote_plus(str(password))
        return (
            f"mssql+pymssql://{enc_user}:{enc_pass}@{server}:{port}/{db_name}?charset=utf8"
        )
    return None


def resolve_database_url(cfg: dict) -> str:
    """供界面显示：优先 database_url，否则由分项拼出。"""
    url = (cfg.get("database_url") or "").strip()
    if url:
        return url
    built = build_database_url(cfg)
    return built or ""


def format_db_error(exc: Exception) -> str:
    msg = str(exc)
    if "YOUR_PASSWORD" in msg:
        return "请在 grabber_config.json 或界面中填写真实数据库密码（不要用 YOUR_PASSWORD 占位符）。"
    if "18456" in msg or "Login failed" in msg:
        return (
            "数据库登录失败：请从 main_gui 复制完整 database_url 连接串粘贴到此处。"
            "密码中的 @ ^ ! 必须写成 %40 %5E %21 等形式，不能直接写明文。"
        )
    if "40615" in msg or "not allowed to access the server" in msg.lower():
        return "无法连接 Azure SQL：请在防火墙中添加当前公网 IP 后重试。"
    return msg


def test_database_connection(cfg: dict | None = None) -> tuple[bool, str]:
    runtime = build_runtime_config(cfg or {})
    url = build_database_url(runtime)
    if not url:
        return False, "未配置 database_url 连接串。"
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(url, connect_args={"timeout": 15})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "连接成功"
    except Exception as exc:
        return False, format_db_error(exc)


def _database_url(cfg: dict) -> str | None:
    return build_database_url(cfg)


def _fetch_raw_rows(
    cfg: dict,
    query: str | None = None,
    *,
    canonicalize: bool = True,
) -> list[dict]:
    global _last_sql_file
    url = _database_url(cfg)
    if not url:
        raise RuntimeError(
            "未配置 database_url（grabber_config.json 或环境变量 DISPLAY_DB_URL）"
        )

    from sqlalchemy import create_engine, text

    def _row_from_raw(raw: dict) -> dict:
        if canonicalize:
            return _canonicalize_row(raw)
        return dict(raw)

    def _execute(sql_text: str) -> list[dict]:
        engine = create_engine(url, connect_args={"timeout": 30})
        rows: list[dict] = []
        with engine.connect() as conn:
            result = conn.execute(text(sql_text))
            keys = list(result.keys())
            for row in result:
                raw = {keys[i]: row[i] for i in range(len(keys))}
                rows.append(_row_from_raw(raw))
        return rows

    if (query or cfg.get("query") or "").strip():
        sql_text = (query or cfg.get("query") or "").strip()
        try:
            rows = _execute(sql_text)
            _last_sql_file = cfg.get("sql_file")
            return rows
        except Exception as exc:
            raise RuntimeError(format_db_error(exc)) from exc

    primary = cfg["sql_file"]
    last_exc: Exception | None = None
    tried_missing: list[str] = []
    for path in _sql_fallback_paths(primary, cfg):
        if not os.path.isfile(path):
            tried_missing.append(path)
            continue
        try:
            rows = _execute(load_sql_query(cfg, path=path))
            _last_sql_file = path
            if path != primary:
                region = get_active_region(cfg)
                print(f"提示: 使用备用 SQL {os.path.relpath(path, SCRIPT_DIR)}（{region}）")
            return rows
        except Exception as exc:
            if _is_schema_sql_error(exc):
                last_exc = exc
                continue
            raise RuntimeError(format_db_error(exc)) from exc

    if tried_missing:
        sample = "\n  ".join(tried_missing[:5])
        bootstrap = os.path.join("tools", "bootstrap_region_sql.py")
        raise RuntimeError(
            f"找不到 SQL 文件（例如 {primary}）。\n"
            f"已尝试:\n  {sample}\n"
            f"请先 git pull，或运行: python {bootstrap}"
        )

    hint = "请在 SSMS 运行 sql/discover_schema.sql，把 Products 表的图片列名发给我们。"
    if last_exc is not None:
        raise RuntimeError(f"{format_db_error(last_exc)}\n{hint}") from last_exc
    raise RuntimeError(hint)


def write_rows_to_excel(rows: list[dict], path: str) -> None:
    """通用 SQL 结果导出：保留原始列名（用于周销量等非 Display 数据）。"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if not rows:
        try:
            import pandas as pd

            pd.DataFrame().to_excel(path, index=False)
            return
        except ImportError:
            from openpyxl import Workbook

            Workbook().save(path)
            return

    columns: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                columns.append(key)

    try:
        import pandas as pd

        pd.DataFrame(rows, columns=columns).to_excel(path, index=False)
        return
    except ImportError:
        pass

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(columns)
    for row in rows:
        ws.append([row.get(col) for col in columns])
    wb.save(path)


def grab_sql_to_excel(cfg: dict | None = None, *, sales: bool = False) -> tuple[list[dict], str]:
    """通用抓取：Display 或周销量（sales=True → sql/{region}/weekly_sales.sql → data/{region}/）。"""
    runtime = sales_runtime_config(cfg) if sales else build_runtime_config(cfg)
    rows = _fetch_raw_rows(runtime, canonicalize=False)
    excel_path = runtime["output_excel"]
    write_rows_to_excel(rows, excel_path)
    return rows, excel_path


def export_rows_to_excel(rows: list[dict], path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    export = []
    for row in rows:
        export.append({
            "WarehouseName": row.get("warehouse_name", ""),
            "Sku": row.get("product_code", ""),
            "ProductName": row.get("product_name", ""),
            "ProductFamily": row.get("product_family", ""),
            "SubProductFamily": row.get("sub_product_family", ""),
            "ImageUrl": row.get("image_url", ""),
            "IsDiscontinued": 1 if _cell_bool(row.get("is_discontinued")) else 0,
            "StockStatus": row.get("stock_status", ""),
            "DisplayQty": row.get("display_qty", 0),
        })
    try:
        import pandas as pd

        pd.DataFrame(export).to_excel(path, index=False)
        return
    except ImportError:
        pass
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["WarehouseName", "Sku", "ProductName", "ProductFamily", "SubProductFamily", "ImageUrl", "IsDiscontinued", "StockStatus", "DisplayQty"])
    for r in export:
        ws.append([
            r["WarehouseName"],
            r["Sku"],
            r["ProductName"],
            r["ProductFamily"],
            r["SubProductFamily"],
            r["ImageUrl"],
            r["IsDiscontinued"],
            r["StockStatus"],
            r["DisplayQty"],
        ])
    wb.save(path)


def sales_runtime_config(cfg: dict | None = None) -> dict:
    """周销量抓取路径（与 Display 共用当前区域 database_url）。"""
    base = build_runtime_config(cfg)
    sql_file = base.get("sales_sql_file") or os.path.join(
        base.get("sql_folder") or "sql", "weekly_sales.sql"
    )
    if not os.path.isabs(sql_file):
        sql_file = os.path.join(SCRIPT_DIR, sql_file)
    sql_file = _resolve_existing_sql_file(sql_file)
    output_excel = base.get("sales_output_excel")
    if output_excel:
        output_excel = _resolve_path(output_excel)
    else:
        output_excel = weekly_sales_excel_path(cfg)
    return {**base, "sql_file": sql_file, "output_excel": output_excel}


def grab_weekly_sales(cfg: dict | None = None) -> tuple[list[dict], str]:
    """周销量抓取：sql/{region}/weekly_sales.sql → data/{region}/weekly_sales.xlsx。"""
    rows, excel_path = grab_sql_to_excel(cfg, sales=True)
    try:
        from sales_lookup import reload_weekly_sales

        reload_weekly_sales(excel_path)
    except Exception:
        pass
    return rows, excel_path


def run_grab_pipeline(
    cfg: dict | None = None,
    *,
    display: bool = True,
    sales: bool = False,
    sync_roi: bool = False,
    log=print,
) -> dict:
    """统一抓取：Display + 周销量，可选同步 ROI 到模板。"""
    results: dict = {}
    if display:
        log("抓取 Display 数据...")
        items, excel_path = grab_and_save(cfg)
        results["display"] = {"items": items, "excel": excel_path, "count": len(items)}
        log(f"Display 完成: {len(items)} 款 → {excel_path}")
    if sales:
        log("抓取周销量...")
        rows, excel_path = grab_weekly_sales(cfg)
        results["sales"] = {"rows": rows, "excel": excel_path, "count": len(rows)}
        log(f"周销量完成: {len(rows)} 行 → {excel_path}")
    if sync_roi:
        log("同步 ROI 到模板与布局...")
        try:
            import importlib.util

            roi_script = os.path.join(SCRIPT_DIR, "scripts", "update_roi.py")
            spec = importlib.util.spec_from_file_location("update_roi", roi_script)
            if spec is None or spec.loader is None:
                raise ImportError(f"无法加载 {roi_script}")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            code = int(mod.main())
            results["roi_sync"] = {"ok": code == 0}
            if code == 0:
                log("ROI 同步完成")
            else:
                log("ROI 同步未完全成功，请查看日志")
        except Exception as exc:
            results["roi_sync"] = {"ok": False, "error": str(exc)}
            log(f"ROI 同步失败: {exc}")
    return results


def grab_and_save(cfg: dict | None = None) -> tuple[list["DisplayItem"], str]:
    """Main 抓取：SQL → data/display.xlsx + JSON 缓存。"""
    global _display_cache, _last_load_error, _last_load_source
    runtime = build_runtime_config(cfg)
    rows = _fetch_raw_rows(runtime)
    excel_path = runtime["output_excel"]
    export_rows_to_excel(rows, excel_path)
    items_all = _rows_to_items(rows, "warehouse", apply_blacklist=False)
    global _display_items_all
    _display_items_all = items_all
    items = filter_blacklisted(items_all)
    save_cache(items, runtime["output_json"])
    _display_cache = items
    _last_load_error = None
    _last_load_source = display_source_label(excel_path)
    return items, excel_path


def _fetch_from_database(cfg: dict) -> list[DisplayItem]:
    rows = _fetch_raw_rows(cfg)
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
                "sub_product_family": it.sub_product_family,
                "image_url": it.image_url,
                "stock_details": it.stock_details,
                "is_discontinued": it.is_discontinued,
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


def _display_cache_is_fresh(cache_path: str, excel_path: str | None) -> bool:
    if not excel_path or not os.path.isfile(excel_path) or not os.path.isfile(cache_path):
        return False
    try:
        return os.path.getmtime(cache_path) >= os.path.getmtime(excel_path)
    except OSError:
        return False


def load_display_items(*, prefer_db: bool = False) -> list[DisplayItem]:
    """可视化程序读取：JSON 缓存（若较新）→ Excel → 数据库抓取。"""
    global _display_cache, _last_load_error, _last_load_source
    if _display_cache is not None and not prefer_db:
        return _display_cache

    if prefer_db:
        try:
            items, _ = grab_and_save()
            return items
        except Exception as exc:
            _last_load_error = str(exc)
            print(f"Display 抓取失败，尝试读本地 Excel: {exc}")

    cache_path = resolve_cache_path()
    excel_path = next((p for p in resolve_display_excel_paths() if os.path.isfile(p)), None)
    if not excel_path:
        _display_cache = []
        folder = get_active_region(load_grabber_config())
        _last_load_error = (
            f"未找到本区域 Display（{display_excel_path()}），请先在 data/{folder}/ 运行 grab_display 抓取"
        )
        _last_load_source = None
        return []

    if _display_cache_is_fresh(cache_path, excel_path):
        items = _load_cache_file(cache_path)
        if items:
            _display_cache = items
            _last_load_error = None
            _last_load_source = display_source_label(cache_path)
            return items

    items = load_from_excel()
    if items:
        _display_cache = items
        return items

    if os.path.isfile(cache_path):
        items = _load_cache_file(cache_path)
        if items:
            _display_cache = items
            _last_load_source = display_source_label(cache_path)
            return items

    _display_cache = []
    if _last_load_error is None:
        _last_load_error = "Display Excel 为空或无法读取，请重新 grab_display"
    return []


def reload_display_items(*, prefer_db: bool = False) -> list[DisplayItem]:
    global _display_cache
    _display_cache = None
    return load_display_items(prefer_db=prefer_db)


def last_load_error() -> str | None:
    return _last_load_error


def last_load_source() -> str | None:
    return _last_load_source


def last_family_column() -> str | None:
    return _last_family_column


class TemplateIndexCache:
    """模板 id → 下标缓存，画廊筛选/统计时避免 O(n×m) 线性扫描。"""

    __slots__ = ("_key", "_by_id")

    def __init__(self) -> None:
        self._key: tuple | None = None
        self._by_id: dict[str, int] = {}

    @staticmethod
    def _templates_key(templates: list[dict]) -> tuple:
        if not templates:
            return (0,)
        return (len(templates),) + tuple(_normalize_key(t.get("id", "")) for t in templates)

    def for_templates(self, templates: list[dict]) -> "TemplateIndexCache":
        key = self._templates_key(templates)
        if key == self._key:
            return self
        self._key = key
        by_id: dict[str, int] = {}
        for i, tpl in enumerate(templates):
            tid = _normalize_key(tpl.get("id", ""))
            if tid and tid not in by_id:
                by_id[tid] = i
        self._by_id = by_id
        return self

    def lookup(self, item: DisplayItem) -> int:
        code = _normalize_key(item.product_code)
        name = _normalize_key(item.product_name)
        best: int | None = None
        if code and code in self._by_id:
            best = self._by_id[code]
        if name and name in self._by_id:
            idx = self._by_id[name]
            if best is None or idx < best:
                best = idx
        return best if best is not None else -1


_template_index_cache = TemplateIndexCache()
_shop_stats_cache_key: tuple | None = None
_shop_stats_cache: dict[str, dict[str, int]] = {}


def filter_gallery_items(
    items: list[DisplayItem],
    shop_id: str,
    query: str,
    templates: list[dict],
    *,
    survey_filter: str = "all",
    blacklist_mode: str = "exclude",
    dual_placement_only: bool = False,
    template_index: TemplateIndexCache | None = None,
) -> list[DisplayItem]:
    """画廊筛选：门店 / 搜索 / 已测绘 / 黑名单模式。"""
    idx_cache = (template_index or _template_index_cache).for_templates(templates)
    blocked = load_blacklist()
    q = _normalize_key(query)
    out: list[DisplayItem] = []
    for it in items:
        bl = is_blacklisted(it, blocked)
        if blacklist_mode == "exclude" and bl:
            continue
        if blacklist_mode == "only" and not bl:
            continue
        if shop_id != "all" and it.display_qty_for_shop(shop_id) <= 0:
            continue
        if q:
            blob = " ".join([
                it.product_code,
                it.product_name,
                it.product_family,
                it.sub_product_family,
            ]).lower()
            if q not in blob:
                continue
        modeled = idx_cache.lookup(it) >= 0
        if survey_filter == "modeled" and not modeled:
            continue
        if survey_filter == "unmodeled" and modeled:
            continue
        if dual_placement_only:
            from dual_placement import is_dual_placement_eligible

            if not is_dual_placement_eligible(it.key, shop_id=shop_id):
                continue
        out.append(it)
    out.sort(key=lambda x: (
        x.product_family.lower(),
        x.sub_product_family.lower(),
        x.product_name.lower(),
    ))
    return out


def display_items_including_blacklist() -> list[DisplayItem]:
    """含黑名单的完整 Display 列表（画廊「全部/仅黑名单」用）。"""
    if _display_items_all is not None:
        return _display_items_all
    return _display_cache or []


def lookup_display_item(name_or_code: str) -> DisplayItem | None:
    """按 SKU 或产品名查找 Display 项（含黑名单列表）。"""
    key = _normalize_key(name_or_code)
    if not key:
        return None
    for item in display_items_including_blacklist():
        if _normalize_key(item.product_code) == key or _normalize_key(item.product_name) == key:
            return item
    return None


def resolve_is_discontinued(name_or_code: str, stored: bool | None = None) -> bool:
    """解析产品是否停产：Display 缓存优先，否则用已存字段。"""
    item = lookup_display_item(name_or_code)
    if item is not None:
        return bool(item.is_discontinued)
    if stored is not None:
        return bool(stored)
    return False


def filter_items(items: list[DisplayItem], shop_id: str, query: str = "") -> list[DisplayItem]:
    q = _normalize_key(query)
    out: list[DisplayItem] = []
    for it in items:
        if shop_id != "all" and it.display_qty_for_shop(shop_id) <= 0:
            continue
        if q:
            blob = " ".join([
                it.product_code,
                it.product_name,
                it.product_family,
                it.sub_product_family,
            ]).lower()
            if q not in blob:
                continue
        out.append(it)
    out.sort(key=lambda x: (
        x.product_family.lower(),
        x.sub_product_family.lower(),
        x.product_name.lower(),
    ))
    return out


def group_by_family(items: list[DisplayItem]) -> list[tuple[str, list[DisplayItem]]]:
    groups: dict[str, list[DisplayItem]] = {}
    for it in items:
        groups.setdefault(it.product_family or "未分类", []).append(it)
    return sorted(groups.items(), key=lambda x: (-len(x[1]), x[0].lower()))


def group_by_family_hierarchy(
    items: list[DisplayItem],
) -> list[tuple[str, list[tuple[str, list[DisplayItem]]]]]:
    """Product Family → Sub Product Family → items。"""
    top: dict[str, dict[str, list[DisplayItem]]] = {}
    for it in items:
        fam = it.product_family or "未分类"
        sub = it.sub_product_family or it.product_name or it.product_code or "未分类"
        top.setdefault(fam, {}).setdefault(sub, []).append(it)
    out: list[tuple[str, list[tuple[str, list[DisplayItem]]]]] = []
    for fam in sorted(top.keys(), key=str.lower):
        subs = sorted(top[fam].items(), key=lambda x: x[0].lower())
        out.append((fam, subs))
    return out


def shop_stats(
    items: list[DisplayItem],
    templates: list[dict],
    *,
    template_index: TemplateIndexCache | None = None,
) -> dict[str, dict[str, int]]:
    idx_cache = (template_index or _template_index_cache).for_templates(templates)
    shops = reload_shops()
    stats: dict[str, dict[str, int]] = {
        shop["id"]: {"total": 0, "modeled": 0, "families": 0, "_fam_set": set()}
        for shop in shops
    }
    for it in items:
        modeled = idx_cache.lookup(it) >= 0
        fam = it.product_family if it.product_family and it.product_family != "未分类" else None
        for shop in shops:
            sid = shop["id"]
            if sid != "all" and it.display_qty_for_shop(sid) <= 0:
                continue
            row = stats[sid]
            row["total"] += 1
            if modeled:
                row["modeled"] += 1
            if fam:
                row["_fam_set"].add(fam)
    for sid, row in stats.items():
        row["families"] = len(row.pop("_fam_set"))
    return stats


def cached_shop_stats(items: list[DisplayItem], templates: list[dict]) -> dict[str, dict[str, int]]:
    """门店 Tab 统计：仅在 Display/模板变更时重算，避免每帧 O(n×shops)。"""
    global _shop_stats_cache_key, _shop_stats_cache
    key = (
        len(items),
        len(templates),
        id(items),
        _template_index_cache._templates_key(templates),
        blacklist_files_revision(),
    )
    if key != _shop_stats_cache_key:
        _shop_stats_cache_key = key
        _shop_stats_cache = shop_stats(items, templates)
    return _shop_stats_cache


def invalidate_shop_stats_cache() -> None:
    global _shop_stats_cache_key
    _shop_stats_cache_key = None


def shops_for_display_tabs(
    items: list[DisplayItem], templates: list[dict]
) -> list[tuple[dict[str, Any], dict[str, int]]]:
    """门店 Tab：全部固定第一，其余按 Product Family 数量从高到低。"""
    stats = cached_shop_stats(items, templates)
    rows: list[tuple[dict[str, Any], dict[str, int]]] = []
    for shop in reload_shops():
        sid = shop["id"]
        if sid == "other":
            continue
        st = stats.get(sid, {"total": 0, "modeled": 0, "families": 0})
        if sid != "all" and st["total"] == 0:
            continue
        rows.append((shop, st))
    all_row = next((r for r in rows if r[0]["id"] == "all"), None)
    rest = [r for r in rows if r[0]["id"] != "all"]
    rest.sort(key=lambda r: (-r[1].get("families", 0), -r[1]["total"], r[0]["label"].lower()))
    out: list[tuple[dict[str, Any], dict[str, int]]] = []
    if all_row:
        out.append(all_row)
    out.extend(rest)
    return out


def match_template_index(
    item: DisplayItem,
    templates: list[dict],
    *,
    template_index: TemplateIndexCache | None = None,
) -> int:
    """按 SKU 或产品名精确匹配模板，不按 Family 模糊匹配（避免测绘一款整族都变绿）。"""
    return (template_index or _template_index_cache).for_templates(templates).lookup(item)


def find_template_index_by_id(templates: list[dict], tpl_id: str) -> int:
    key = _normalize_key(tpl_id)
    for i, tpl in enumerate(templates):
        if _normalize_key(tpl.get("id", "")) == key:
            return i
    return -1


def template_matches_display_item(tpl: dict, item: DisplayItem) -> bool:
    """模板 id 是否与 Display 产品的 SKU 或产品名一致。"""
    tid = _normalize_key(tpl.get("id", ""))
    if not tid:
        return False
    code = _normalize_key(item.product_code)
    name = _normalize_key(item.product_name)
    return (code and code == tid) or (name and name == tid)


def find_display_item_for_template(
    tpl: dict, items: list[DisplayItem]
) -> DisplayItem | None:
    for item in items:
        if template_matches_display_item(tpl, item):
            return item
    return None


def prune_orphan_templates(
    templates: list[dict], items: list[DisplayItem]
) -> tuple[list[dict], list[str]]:
    """只保留能在 Display 库中匹配到的模板，删除手工测绘的游离项。"""
    if not items:
        return templates[:], []
    kept: list[dict] = []
    removed: list[str] = []
    for tpl in templates:
        if find_display_item_for_template(tpl, items):
            kept.append(tpl)
        else:
            removed.append(str(tpl.get("id", "")))
    return kept, removed


SHOPS = reload_shops()
