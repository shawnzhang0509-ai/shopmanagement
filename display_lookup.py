"""Display 库数据层：抓取程序写 data/display.xlsx，模板编辑器只读可视化。

架构（和库存 main_gui 项目一样）：
  grab_display.bat   → Main：SQL 抓数据 → data/display.xlsx
  start_template.bat → 可视化：furniture_sim 读 Excel 显示 Display 大库
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
GRABBER_CONFIG = os.path.join(SCRIPT_DIR, "grabber_config.json")
GRABBER_CONFIG_EXAMPLE = os.path.join(SCRIPT_DIR, "grabber_config.example.json")
CONFIG_FILE = os.path.join(SCRIPT_DIR, "display_config.json")
CONFIG_EXAMPLE = os.path.join(SCRIPT_DIR, "display_config.example.json")
CACHE_FILE = os.path.join(SCRIPT_DIR, "display_cache.json")
DEFAULT_EXCEL = os.path.join(SCRIPT_DIR, "data", "display.xlsx")
LEGACY_EXCEL = os.path.join(SCRIPT_DIR, "display.xlsx")
DEFAULT_SQL = os.path.join(SCRIPT_DIR, "sql", "display.sql")

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


def _load_excel_rows(path: str) -> tuple[str, list[dict]]:
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
    candidates = [path] if path else resolve_display_excel_paths()
    last_exc = None
    for candidate in candidates:
        if not candidate or not os.path.isfile(candidate):
            continue
        try:
            fmt, rows = _load_excel_rows(candidate)
            items = _rows_to_items(rows, fmt)
            if items:
                _last_load_error = None
                _last_load_source = os.path.basename(candidate)
                return items
            _last_load_error = f"{os.path.basename(candidate)} 中没有 Display 数据"
        except Exception as exc:
            last_exc = exc
            _last_load_error = f"读取 {os.path.basename(candidate)} 失败: {exc}"
    if not candidates or not any(os.path.isfile(p) for p in candidates if p):
        _last_load_error = "未找到 display.xlsx，请先运行 grab_display.bat 抓取数据"
    elif last_exc:
        _last_load_error = str(last_exc)
    _last_load_source = None
    return []


def load_grabber_config() -> dict:
    for path in (GRABBER_CONFIG, GRABBER_CONFIG_EXAMPLE, CONFIG_FILE, CONFIG_EXAMPLE):
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    return {}


def save_grabber_config(cfg: dict) -> None:
    path = GRABBER_CONFIG
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _resolve_path(path: str) -> str:
    if not path:
        return SCRIPT_DIR
    return path if os.path.isabs(path) else os.path.join(SCRIPT_DIR, path)


def build_runtime_config(cfg: dict | None = None) -> dict:
    """合并配置并解析 sql / 输出路径。"""
    base = dict(cfg or load_grabber_config())
    sql_folder = base.get("sql_folder") or "sql"
    sql_folder_abs = _resolve_path(sql_folder)
    sql_file = base.get("sql_file")
    if not sql_file:
        sql_file = os.path.join(sql_folder_abs, "display.sql")
    else:
        sql_file = _resolve_path(sql_file)
    base["sql_file"] = sql_file

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
    cfg = load_grabber_config()
    paths: list[str] = []
    if cfg.get("output_excel"):
        paths.append(os.path.join(SCRIPT_DIR, cfg["output_excel"]))
    paths.extend([DEFAULT_EXCEL, LEGACY_EXCEL])
    seen: set[str] = set()
    out: list[str] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def resolve_cache_path() -> str:
    cfg = load_grabber_config()
    if cfg.get("output_json"):
        return os.path.join(SCRIPT_DIR, cfg["output_json"])
    data_json = os.path.join(SCRIPT_DIR, "data", "display_cache.json")
    if os.path.isfile(data_json):
        return data_json
    return CACHE_FILE


def load_sql_query(cfg: dict | None = None) -> str:
    cfg = build_runtime_config(cfg)
    path = cfg["sql_file"]
    if not os.path.isfile(path):
        raise FileNotFoundError(f"找不到 SQL 文件: {path}")
    with open(path, "r", encoding="utf-8") as f:
        lines = [ln for ln in f.readlines() if not ln.strip().startswith("--")]
    query = "\n".join(lines).strip()
    if not query:
        raise ValueError(f"SQL 文件为空: {path}")
    return query


def _load_config() -> dict:
    return load_grabber_config()


def _database_url(cfg: dict) -> str | None:
    env = os.environ.get("DISPLAY_DB_URL", "").strip()
    if env:
        return env
    return (cfg.get("database_url") or "").strip() or None


def _fetch_raw_rows(cfg: dict, query: str | None = None) -> list[dict]:
    url = _database_url(cfg)
    if not url:
        raise RuntimeError("未配置 database_url（grabber_config.json 或环境变量 DISPLAY_DB_URL）")
    query = (query or cfg.get("query") or "").strip() or load_sql_query(cfg)

    from sqlalchemy import create_engine, text

    engine = create_engine(url, connect_args={"timeout": 30})
    rows: list[dict] = []
    with engine.connect() as conn:
        result = conn.execute(text(query))
        keys = list(result.keys())
        for row in result:
            raw = {keys[i]: row[i] for i in range(len(keys))}
            rows.append(_canonicalize_row(raw))
    return rows


def export_rows_to_excel(rows: list[dict], path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    export = []
    for row in rows:
        export.append({
            "WarehouseName": row.get("warehouse_name", ""),
            "Sku": row.get("product_code", ""),
            "ProductName": row.get("product_name", ""),
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
    ws.append(["WarehouseName", "Sku", "ProductName", "DisplayQty"])
    for r in export:
        ws.append([r["WarehouseName"], r["Sku"], r["ProductName"], r["DisplayQty"]])
    wb.save(path)


def grab_and_save(cfg: dict | None = None) -> tuple[list["DisplayItem"], str]:
    """Main 抓取：SQL → data/display.xlsx + JSON 缓存。"""
    global _display_cache, _last_load_error, _last_load_source
    runtime = build_runtime_config(cfg)
    rows = _fetch_raw_rows(runtime)
    excel_path = runtime["output_excel"]
    export_rows_to_excel(rows, excel_path)
    items = _rows_to_items(rows, "warehouse")
    save_cache(items, runtime["output_json"])
    _display_cache = items
    _last_load_error = None
    _last_load_source = os.path.basename(excel_path)
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
    """可视化程序读取：优先 data/display.xlsx，可选尝试数据库抓取。"""
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

    items = load_from_excel()
    if items:
        _display_cache = items
        return items

    items = _load_cache_file(resolve_cache_path())
    _display_cache = items
    if items:
        _last_load_source = os.path.basename(resolve_cache_path())
        return items

    if _last_load_error is None:
        _last_load_error = "请先运行 grab_display.bat 抓取数据"
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
