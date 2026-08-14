"""iERP 产品图：相对路径拼 https://ierpapi.ifurniture.co.nz/ 并缓存缩略图。"""
from __future__ import annotations

import hashlib
import io
import os
import threading
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen

ERP_IMAGE_BASE = "https://ierpapi.ifurniture.co.nz/"
TIMEOUT = 12
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DisplayGallery/1.0)"}
THUMB_SIZE = (96, 72)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DISK_CACHE_DIR = os.path.join(SCRIPT_DIR, "data", "image_cache")

_surface_cache: dict[str, object] = {}
_loading: set[str] = set()
_failed: set[str] = set()
_lock = threading.Lock()


def normalize_image_url(url: str) -> str:
    """CSV / SQL 相对路径 → 绝对 URL。"""
    url = (url or "").strip()
    if not url:
        return ""
    if url.lower() in ("nan", "none", "null"):
        return ""
    if not url.lower().startswith("http"):
        url = ERP_IMAGE_BASE + url.replace("\\", "/").lstrip("/")
    parts = urlsplit(url)
    path = quote(parts.path, safe="/:%")
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def _cache_path(url: str) -> str:
    os.makedirs(DISK_CACHE_DIR, exist_ok=True)
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return os.path.join(DISK_CACHE_DIR, f"{digest}.png")


def _download_bytes(url: str) -> bytes:
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def _bytes_to_surface(data: bytes, max_size: tuple[int, int]) -> object | None:
    try:
        import pygame
        from PIL import Image
    except ImportError:
        return None

    img = Image.open(io.BytesIO(data))
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGBA")
    else:
        img = img.convert("RGB")
    img.thumbnail(max_size, Image.Resampling.LANCZOS)
    mode = img.mode
    size = img.size
    raw = img.tobytes()
    return pygame.image.frombytes(raw, size, mode)


def _load_worker(url: str, disk_path: str) -> None:
    try:
        data = _download_bytes(url)
        with open(disk_path, "wb") as f:
            f.write(data)
        surf = _bytes_to_surface(data, THUMB_SIZE)
        if surf is not None:
            with _lock:
                _surface_cache[url] = surf
    except Exception:
        with _lock:
            _failed.add(url)
    finally:
        with _lock:
            _loading.discard(url)


def request_thumbnail(url: str) -> object | None:
    """返回 pygame Surface 或 None（加载中/无图）。"""
    norm = normalize_image_url(url)
    if not norm:
        return None
    with _lock:
        if norm in _surface_cache:
            return _surface_cache[norm]
        if norm in _failed:
            return None
        if norm in _loading:
            return None

    disk_path = _cache_path(norm)
    if os.path.isfile(disk_path):
        try:
            with open(disk_path, "rb") as f:
                surf = _bytes_to_surface(f.read(), THUMB_SIZE)
            if surf is not None:
                with _lock:
                    _surface_cache[norm] = surf
                return surf
        except Exception:
            pass

    with _lock:
        if norm in _loading:
            return None
        _loading.add(norm)
    threading.Thread(target=_load_worker, args=(norm, disk_path), daemon=True).start()
    return None


def prefetch_urls(urls: list[str], limit: int = 24) -> None:
    """预取当前可见区域附近的图片。"""
    seen: set[str] = set()
    for raw in urls:
        norm = normalize_image_url(raw)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        request_thumbnail(norm)
        if len(seen) >= limit:
            break


def clear_image_cache() -> None:
    with _lock:
        _surface_cache.clear()
        _loading.clear()
        _failed.clear()
