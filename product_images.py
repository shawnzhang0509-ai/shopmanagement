"""iERP 产品图：相对路径拼官网 CDN 并缓存缩略图。"""
from __future__ import annotations

import hashlib
import io
import json
import os
import threading
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen

# SQL 里已是完整 URL 时直接用；相对路径优先拼 ierpapi（与库存 stock SQL 一致）
DEFAULT_IMAGE_BASES = (
    "https://ierpapi.ifurniture.co.nz/",
    "https://ifurniture.co.nz/",
    "https://www.ifurniture.co.nz/",
)
TIMEOUT = 12
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DisplayGallery/1.0)"}
THUMB_SIZE = (96, 72)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DISK_CACHE_DIR = os.path.join(SCRIPT_DIR, "data", "image_cache")
CONFIG_PATH = os.path.join(SCRIPT_DIR, "grabber_config.json")

_surface_cache: dict[str, object] = {}
_loading: set[str] = set()
_failed: set[str] = set()
_lock = threading.Lock()
_config_bases: tuple[str, ...] | None = None


def _load_image_bases() -> tuple[str, ...]:
    global _config_bases
    if _config_bases is not None:
        return _config_bases
    bases: list[str] = []
    if os.path.isfile(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                cfg = json.load(f)
            custom = (cfg.get("image_base_url") or "").strip()
            if custom:
                bases.append(custom if custom.endswith("/") else f"{custom}/")
        except Exception:
            pass
    bases.extend(DEFAULT_IMAGE_BASES)
    # 去重，保持顺序
    seen: set[str] = set()
    ordered: list[str] = []
    for base in bases:
        if base not in seen:
            seen.add(base)
            ordered.append(base)
    _config_bases = tuple(ordered)
    return _config_bases


def _clean_raw(url: str) -> str:
    url = (url or "").strip()
    if not url or url.lower() in ("nan", "none", "null"):
        return ""
    return url


def _encode_url(url: str) -> str:
    parts = urlsplit(url)
    path = quote(parts.path, safe="/:%@")
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def image_candidates(url: str) -> list[str]:
    """DB/Excel 里的路径 → 按优先级尝试的绝对 URL 列表。"""
    raw = _clean_raw(url)
    if not raw:
        return []
    if raw.lower().startswith("http"):
        return [_encode_url(raw)]
    path = raw.replace("\\", "/").lstrip("/")
    return [_encode_url(base + path) for base in _load_image_bases()]


def normalize_image_url(url: str) -> str:
    """返回首选绝对 URL（兼容旧调用）。"""
    candidates = image_candidates(url)
    return candidates[0] if candidates else ""


def is_image_failed(url: str) -> bool:
    raw = _clean_raw(url)
    if not raw:
        return False
    with _lock:
        return raw in _failed


def _cache_path(raw_key: str) -> str:
    os.makedirs(DISK_CACHE_DIR, exist_ok=True)
    digest = hashlib.sha1(raw_key.encode("utf-8")).hexdigest()
    return os.path.join(DISK_CACHE_DIR, f"{digest}.img")


def _download_bytes(url: str) -> bytes:
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def _fit_surface(surf, max_size: tuple[int, int]):
    import pygame

    w, h = surf.get_size()
    mw, mh = max_size
    scale = min(mw / max(w, 1), mh / max(h, 1), 1.0)
    if scale >= 1.0:
        return surf
    nw = max(1, int(w * scale))
    nh = max(1, int(h * scale))
    return pygame.transform.smoothscale(surf, (nw, nh))


def _bytes_to_surface(data: bytes, max_size: tuple[int, int]) -> object | None:
    try:
        import pygame
    except ImportError:
        return None

    try:
        surf = pygame.image.load(io.BytesIO(data))
        if surf.get_flags() & pygame.SRCALPHA:
            surf = surf.convert_alpha()
        else:
            surf = surf.convert()
        return _fit_surface(surf, max_size)
    except Exception:
        pass

    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGBA")
        else:
            img = img.convert("RGB")
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        return pygame.image.frombytes(img.tobytes(), img.size, img.mode)
    except Exception:
        return None


def _load_worker(raw_key: str, candidates: list[str], disk_path: str) -> None:
    try:
        try:
            import pygame  # noqa: F401 — 确保主线程已 init 时 worker 可用
        except ImportError:
            with _lock:
                _failed.add(raw_key)
            return

        last_error: Exception | None = None
        for url in candidates:
            try:
                data = _download_bytes(url)
                surf = _bytes_to_surface(data, THUMB_SIZE)
                if surf is None:
                    continue
                with open(disk_path, "wb") as f:
                    f.write(data)
                with _lock:
                    _surface_cache[raw_key] = surf
                return
            except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
                last_error = exc
                continue

        if last_error is not None:
            with _lock:
                _failed.add(raw_key)
    finally:
        with _lock:
            _loading.discard(raw_key)


def request_thumbnail(url: str) -> object | None:
    """返回 pygame Surface 或 None（加载中/无图）。"""
    raw = _clean_raw(url)
    if not raw:
        return None
    with _lock:
        if raw in _surface_cache:
            return _surface_cache[raw]
        if raw in _failed:
            return None
        if raw in _loading:
            return None

    disk_path = _cache_path(raw)
    if os.path.isfile(disk_path):
        try:
            with open(disk_path, "rb") as f:
                surf = _bytes_to_surface(f.read(), THUMB_SIZE)
            if surf is not None:
                with _lock:
                    _surface_cache[raw] = surf
                return surf
        except Exception:
            pass

    candidates = image_candidates(raw)
    if not candidates:
        return None

    with _lock:
        if raw in _loading:
            return None
        _loading.add(raw)
    threading.Thread(
        target=_load_worker,
        args=(raw, candidates, disk_path),
        daemon=True,
    ).start()
    return None


def prefetch_urls(urls: list[str], limit: int = 24) -> None:
    """预取当前可见区域附近的图片。"""
    seen: set[str] = set()
    for raw in urls:
        key = _clean_raw(raw)
        if not key or key in seen:
            continue
        seen.add(key)
        request_thumbnail(key)
        if len(seen) >= limit:
            break


def clear_image_cache() -> None:
    global _config_bases
    with _lock:
        _surface_cache.clear()
        _loading.clear()
        _failed.clear()
    _config_bases = None
