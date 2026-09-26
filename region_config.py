"""多区域配置：新西兰 / 澳洲 / 加拿大 独立数据库、门店与数据目录。"""
from __future__ import annotations

import json
import os
from typing import Any

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REGIONS_DIR = os.path.join(SCRIPT_DIR, "config", "regions")
SUPPORTED_REGIONS: tuple[str, ...] = ("nz", "au", "ca")
REGION_LABELS: dict[str, str] = {"nz": "新西兰", "au": "澳洲", "ca": "加拿大"}

# 无 config/regions/*.json 时的兜底（与旧版 NZ 一致）
_FALLBACK_NZ_SHOPS: list[dict[str, Any]] = [
    {"id": "all", "label": "全部", "patterns": []},
    {"id": "onehunga", "label": "Onehunga", "patterns": ["onehunga"]},
    {"id": "westgate", "label": "Westgate", "patterns": ["westgate"]},
    {"id": "hamilton", "label": "Hamilton", "patterns": ["hamilton"]},
    {"id": "chch", "label": "Christchurch", "patterns": ["chch", "chc", "christchurch", "christ church", "colombo", "bleiham", "hornby", "riccarton"]},
    {"id": "carbine", "label": "Carbine Rd", "patterns": ["carbine"]},
    {"id": "other", "label": "其他", "patterns": []},
]

_profile_cache: dict[str, dict[str, Any]] = {}


def _profile_path(region_id: str) -> str:
    return os.path.join(REGIONS_DIR, f"{region_id}.json")


def clear_profile_cache() -> None:
    _profile_cache.clear()


def load_region_profile(region_id: str) -> dict[str, Any]:
    region_id = normalize_region_id(region_id)
    if region_id in _profile_cache:
        return _profile_cache[region_id]
    path = _profile_path(region_id)
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            profile = json.load(f)
    else:
        profile = {"id": region_id, "label": REGION_LABELS.get(region_id, region_id.upper())}
    _profile_cache[region_id] = profile
    return profile


def normalize_region_id(region_id: str | None) -> str:
    rid = str(region_id or "nz").strip().lower()
    return rid if rid in SUPPORTED_REGIONS else "nz"


def get_active_region(cfg: dict | None = None) -> str:
    if cfg is None:
        cfg = _load_grabber_config_raw()
    env = os.environ.get("ACTIVE_REGION", "").strip().lower()
    if env in SUPPORTED_REGIONS:
        return env
    return normalize_region_id(cfg.get("active_region"))


def _load_grabber_config_raw() -> dict:
    for name in ("grabber_config.json", "grabber_config.example.json"):
        path = os.path.join(SCRIPT_DIR, name)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    return {}


def region_section(cfg: dict, region_id: str | None = None) -> dict[str, Any]:
    region_id = normalize_region_id(region_id or get_active_region(cfg))
    regions = cfg.get("regions") or {}
    section = regions.get(region_id) or {}
    return dict(section) if isinstance(section, dict) else {}


def default_sql_folder(region_id: str) -> str:
    profile = load_region_profile(region_id)
    return str(profile.get("default_sql_folder") or f"sql/{region_id}")


def default_output_folder(region_id: str) -> str:
    profile = load_region_profile(region_id)
    return str(profile.get("default_output_folder") or f"data/{region_id}")


def legacy_data_paths() -> list[str]:
    """迁移工具用：旧版扁平 data/ 与区域目录。"""
    return [
        os.path.join(SCRIPT_DIR, "data"),
        os.path.join(SCRIPT_DIR, "data", "nz"),
    ]


def legacy_display_excel_candidates() -> list[str]:
    """迁移工具用；运行时读取请用 display_excel_path()。"""
    paths = [
        os.path.join(SCRIPT_DIR, "data", "display.xlsx"),
        os.path.join(SCRIPT_DIR, "data", "nz", "display.xlsx"),
        os.path.join(SCRIPT_DIR, "display.xlsx"),
    ]
    seen: set[str] = set()
    out: list[str] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def merge_region_config(cfg: dict | None = None, region_id: str | None = None) -> dict[str, Any]:
    """合并全局配置 + 当前区域 overrides，供抓取与读取使用。"""
    base = dict(cfg or _load_grabber_config_raw())
    region_id = normalize_region_id(region_id or get_active_region(base))
    merged = {k: v for k, v in base.items() if k != "regions"}
    section = region_section(base, region_id)
    has_regions_block = isinstance(base.get("regions"), dict) and bool(base["regions"])
    for key, value in section.items():
        if value not in (None, ""):
            merged[key] = value
    if has_regions_block:
        sec_db = str(section.get("database_url") or "").strip()
        root_db = str(base.get("database_url") or "").strip()
        if sec_db:
            merged["database_url"] = sec_db
        elif region_id == "nz" and root_db:
            merged["database_url"] = root_db
        else:
            merged.pop("database_url", None)
    profile = load_region_profile(region_id)
    merged["active_region"] = region_id
    merged["region_id"] = region_id
    merged["_region_profile"] = profile
    merged["_region_label"] = str(profile.get("label") or REGION_LABELS.get(region_id, region_id))

    if not section.get("sql_folder"):
        root_sql = str(merged.get("sql_folder") or "").strip()
        if has_regions_block or not root_sql or root_sql == "sql":
            merged["sql_folder"] = default_sql_folder(region_id)
        elif not merged.get("sql_folder"):
            merged["sql_folder"] = default_sql_folder(region_id)
    elif has_regions_block:
        sql_norm = str(merged.get("sql_folder") or "").replace("\\", "/").rstrip("/")
        if sql_norm == "sql":
            merged["sql_folder"] = default_sql_folder(region_id)

    if not section.get("output_folder"):
        root_out = str(merged.get("output_folder") or "").strip()
        if has_regions_block or not root_out or root_out == "data":
            merged["output_folder"] = default_output_folder(region_id)
        elif not merged.get("output_folder"):
            merged["output_folder"] = default_output_folder(region_id)
    elif has_regions_block:
        out_norm = str(merged.get("output_folder") or "").replace("\\", "/").rstrip("/")
        if out_norm == "data":
            merged["output_folder"] = default_output_folder(region_id)

    if not merged.get("image_base_url"):
        merged["image_base_url"] = profile.get("image_base_url") or ""

    folder = str(merged.get("output_folder") or "").strip()
    sql_folder = str(merged.get("sql_folder") or default_sql_folder(region_id)).strip()

    if not section.get("sql_file"):
        merged["sql_file"] = os.path.join(sql_folder, "display.sql")
    if not section.get("sales_sql_file"):
        merged["sales_sql_file"] = os.path.join(sql_folder, "weekly_sales.sql")
    if not section.get("stock_price_sql_file"):
        merged["stock_price_sql_file"] = os.path.join(sql_folder, "product_stock_price.sql")

    if folder:
        if not section.get("output_excel"):
            merged["output_excel"] = os.path.join(folder, "display.xlsx")
        if not section.get("output_json"):
            merged["output_json"] = os.path.join(folder, "display_cache.json")
        if not section.get("sales_output_excel"):
            merged["sales_output_excel"] = os.path.join(folder, "weekly_sales.xlsx")
        if not section.get("stock_price_output_excel"):
            merged["stock_price_output_excel"] = os.path.join(folder, "product_stock_price.xlsx")
        if not section.get("blacklist_file"):
            merged["blacklist_file"] = os.path.join(folder, "display_blacklist.csv")

    return merged


def config_for_region(cfg: dict, region_id: str) -> dict:
    """把全局 cfg + 指定 region 合并为一次抓取用的配置。"""
    region_id = normalize_region_id(region_id)
    regions = dict(cfg.get("regions") or {})
    section = dict(regions.get(region_id) or {})
    return merge_region_config({**cfg, "active_region": region_id, "regions": {**regions, region_id: section}}, region_id)


def region_labels() -> list[tuple[str, str]]:
    return [(rid, REGION_LABELS.get(rid, rid.upper())) for rid in SUPPORTED_REGIONS]


def shops_for_region(region_id: str | None = None, cfg: dict | None = None) -> list[dict[str, Any]]:
    region_id = normalize_region_id(region_id or get_active_region(cfg or {}))
    profile = load_region_profile(region_id)
    shops = profile.get("shops")
    if isinstance(shops, list) and shops:
        return [dict(s) for s in shops]
    if region_id == "nz":
        return [dict(s) for s in _FALLBACK_NZ_SHOPS]
    return [
        {"id": "all", "label": "全部", "patterns": []},
        {"id": "other", "label": "其他", "patterns": []},
    ]


def store_entries(region_id: str | None = None) -> tuple[dict[str, str], ...]:
    region_id = normalize_region_id(region_id or get_active_region())
    profile = load_region_profile(region_id)
    entries = profile.get("store_entries") or []
    return tuple(dict(e) for e in entries if isinstance(e, dict))


def layout_catalog(region_id: str | None = None) -> list[tuple[str, str]]:
    region_id = normalize_region_id(region_id or get_active_region())
    profile = load_region_profile(region_id)
    layout_stores = profile.get("layout_stores")
    if isinstance(layout_stores, list) and layout_stores:
        if layout_stores and isinstance(layout_stores[0], (list, tuple)):
            return [(str(a), str(b)) for a, b in layout_stores]
        if layout_stores and isinstance(layout_stores[0], dict):
            return [(str(e["name"]), str(e["slug"])) for e in layout_stores]
    entries = profile.get("store_entries") or []
    return [(str(e["name"]), str(e["slug"])) for e in entries if isinstance(e, dict)]


def layout_slug_to_sales_shop(region_id: str | None = None) -> dict[str, str]:
    region_id = normalize_region_id(region_id or get_active_region())
    profile = load_region_profile(region_id)
    mapping = profile.get("layout_slug_to_sales_shop")
    if isinstance(mapping, dict) and mapping:
        return {str(k): str(v) for k, v in mapping.items()}
    entries = profile.get("store_entries") or []
    return {
        str(e["slug"]): str(e["shop_id"])
        for e in entries
        if isinstance(e, dict) and e.get("slug") and e.get("shop_id")
    }


def catalog_layout_specs(region_id: str | None = None) -> dict[str, tuple[int, int]]:
    region_id = normalize_region_id(region_id or get_active_region())
    profile = load_region_profile(region_id)
    raw = profile.get("catalog_layout_specs") or {}
    out: dict[str, tuple[int, int]] = {}
    for slug, dims in raw.items():
        if isinstance(dims, (list, tuple)) and len(dims) >= 2:
            out[str(slug)] = (int(dims[0]), int(dims[1]))
    return out


def layouts_dir(cfg: dict | None = None, region_id: str | None = None) -> str:
    merged = merge_region_config(cfg, region_id)
    output_folder = merged.get("output_folder") or "data"
    if os.path.isabs(output_folder):
        return os.path.join(output_folder, "layouts")
    return os.path.join(SCRIPT_DIR, output_folder, "layouts")


def region_database_url(cfg: dict, region_id: str | None = None) -> str:
    """区域数据库 URL：DISPLAY_DB_URL_{AU} > regions.*.database_url；多区域时不回退 NZ 根连接串。"""
    region_id = normalize_region_id(region_id or get_active_region(cfg))
    env_key = f"DISPLAY_DB_URL_{region_id.upper()}"
    env = os.environ.get(env_key, "").strip()
    if env:
        return env
    merged = merge_region_config(cfg, region_id)
    url = str(merged.get("database_url") or "").strip()
    if url:
        return url
    has_regions = isinstance((cfg or {}).get("regions"), dict) and bool((cfg or {}).get("regions"))
    if not has_regions:
        global_env = os.environ.get("DISPLAY_DB_URL", "").strip()
        if global_env:
            return global_env
    return ""


def display_excel_path(cfg: dict | None = None, region_id: str | None = None) -> str:
    merged = merge_region_config(cfg, region_id)
    if merged.get("output_excel"):
        path = merged["output_excel"]
        return path if os.path.isabs(path) else os.path.join(SCRIPT_DIR, path)
    folder = merged.get("output_folder") or "data"
    if os.path.isabs(folder):
        return os.path.join(folder, "display.xlsx")
    return os.path.join(SCRIPT_DIR, folder, "display.xlsx")


def weekly_sales_excel_path(cfg: dict | None = None, region_id: str | None = None) -> str:
    merged = merge_region_config(cfg, region_id)
    if merged.get("sales_output_excel"):
        path = merged["sales_output_excel"]
        return path if os.path.isabs(path) else os.path.join(SCRIPT_DIR, path)
    folder = merged.get("output_folder") or "data"
    if os.path.isabs(folder):
        return os.path.join(folder, "weekly_sales.xlsx")
    return os.path.join(SCRIPT_DIR, folder, "weekly_sales.xlsx")


def has_multi_region_config(cfg: dict | None = None) -> bool:
    base = cfg or _load_grabber_config_raw()
    regions = base.get("regions")
    return isinstance(regions, dict) and bool(regions)


def furniture_templates_path(cfg: dict | None = None, region_id: str | None = None) -> str:
    """区域测绘 JSON：data/{region}/furniture_templates.json。"""
    merged = merge_region_config(cfg, region_id)
    folder = str(merged.get("output_folder") or default_output_folder(normalize_region_id(region_id or get_active_region(cfg))))
    if os.path.isabs(folder):
        return os.path.join(folder, "furniture_templates.json")
    return os.path.join(SCRIPT_DIR, folder, "furniture_templates.json")


def resolve_furniture_templates_path(cfg: dict | None = None, region_id: str | None = None) -> str:
    """加载用路径：NZ 可回退仓库根目录 legacy；AU/CA 仅认本区域文件。"""
    region_id = normalize_region_id(region_id or get_active_region(cfg))
    regional = furniture_templates_path(cfg, region_id)
    if os.path.isfile(regional):
        return regional
    legacy = os.path.join(SCRIPT_DIR, "furniture_templates.json")
    if region_id == "nz" and os.path.isfile(legacy):
        return legacy
    return regional
