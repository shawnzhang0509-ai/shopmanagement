"""布局预览渲染 — 与 layout 编辑器视觉一致（fit 内容区 + 墙体/障碍/家具）。"""
from __future__ import annotations

import math
from typing import Iterable

# layout.py 同款配色
C_CANVAS = (245, 247, 250)
C_FLOOR = (255, 255, 255)
C_WALL = (51, 65, 85)
C_WALL_FILL = (225, 230, 236)
C_WALL_BORDER = (148, 163, 184)
C_OBSTACLE = (254, 202, 202)
C_OBSTACLE_BORDER = (185, 28, 28)
C_FURN_FILL = (214, 234, 248)
C_FURN_BORDER = (52, 152, 219)


def obstacle_is_wall(col: dict) -> bool:
    kind = str(col.get("kind", "") or "").strip().lower()
    if kind == "wall":
        return True
    if kind in ("zone", "obstacle"):
        return False
    name = str(col.get("name", "") or "")
    return name.startswith("外墙") or name.startswith("墙") or "wall" in name.lower()


def rotated_furniture_points(furn: dict) -> list[tuple[float, float]]:
    points = furn.get("points") or []
    if len(points) < 3:
        return []
    x, y = float(furn.get("x", 0)), float(furn.get("y", 0))
    rot = float(furn.get("rotation", 0))
    cx = sum(p[0] for p in points) / len(points)
    cy = sum(p[1] for p in points) / len(points)
    rad = math.radians(rot)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    out: list[tuple[float, float]] = []
    for px, py in points:
        rx, ry = px - cx, py - cy
        out.append((rx * cos_a - ry * sin_a + cx + x, rx * sin_a + ry * cos_a + cy + y))
    return out


def _collect_xy(points: Iterable[tuple[float, float]], xs: list[float], ys: list[float]) -> None:
    for x, y in points:
        xs.append(float(x))
        ys.append(float(y))


def content_bounds(data: dict) -> tuple[float, float, float, float]:
    """家具 + 障碍/墙体的外接范围（预览 fit 用，避免 60×90m 空画布）。"""
    xs: list[float] = []
    ys: list[float] = []
    for furn in data.get("furnitures", []):
        _collect_xy(rotated_furniture_points(furn), xs, ys)
    for obs in data.get("obstacles", []):
        pts = obs.get("points") or []
        _collect_xy(((float(p[0]), float(p[1])) for p in pts if len(p) >= 2), xs, ys)

    store = data.get("store") or {}
    sw = float(store.get("width_mm", 20000))
    sh = float(store.get("height_mm", 15000))

    if not xs:
        return 0.0, 0.0, sw, sh

    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    span = max(xmax - xmin, ymax - ymin, 1.0)
    pad = max(800.0, span * 0.08)
    return xmin - pad, ymin - pad, xmax + pad, ymax + pad


def _world_to_screen(
    wx: float, wy: float, *, xmin: float, ymin: float, scale: float, ox: float, oy: float
) -> tuple[int, int]:
    return int(ox + (wx - xmin) * scale), int(oy + (wy - ymin) * scale)


def render_layout_preview(surface, rect, data: dict) -> dict:
    """在 rect 内绘制布局快照，返回统计信息。"""
    import pygame

    stats = {"furniture_count": 0, "obstacle_count": 0, "bounds": None}
    if not data:
        return stats

    inner = rect.inflate(-8, -8)
    pygame.draw.rect(surface, C_CANVAS, inner, border_radius=6)

    xmin, ymin, xmax, ymax = content_bounds(data)
    stats["bounds"] = (xmin, ymin, xmax, ymax)
    bw = max(1.0, xmax - xmin)
    bh = max(1.0, ymax - ymin)
    scale = min(inner.width / bw, inner.height / bh) * 0.96
    ox = inner.x + (inner.width - bw * scale) / 2
    oy = inner.y + (inner.height - bh * scale) / 2

    def to_screen(wx: float, wy: float) -> tuple[int, int]:
        return _world_to_screen(wx, wy, xmin=xmin, ymin=ymin, scale=scale, ox=ox, oy=oy)

    # 门店外框（浅灰虚线感）
    store = data.get("store") or {}
    sw = float(store.get("width_mm", bw))
    sh = float(store.get("height_mm", bh))
    floor_pts = [to_screen(0, 0), to_screen(sw, 0), to_screen(sw, sh), to_screen(0, sh)]
    pygame.draw.polygon(surface, C_FLOOR, floor_pts)
    pygame.draw.polygon(surface, C_WALL_BORDER, floor_pts, 1)

    # 障碍 / 墙体（与 layout 一致：墙=灰，区域=粉）
    for obs in data.get("obstacles", []):
        raw = obs.get("points") or []
        if len(raw) < 3:
            continue
        pts = [to_screen(float(p[0]), float(p[1])) for p in raw]
        if obstacle_is_wall(obs):
            pygame.draw.polygon(surface, C_WALL_FILL, pts)
            pygame.draw.polygon(surface, C_WALL_BORDER, pts, 2)
        else:
            pygame.draw.polygon(surface, C_OBSTACLE, pts)
            pygame.draw.polygon(surface, C_OBSTACLE_BORDER, pts, 2)
        stats["obstacle_count"] += 1

    # 家具
    for furn in data.get("furnitures", []):
        pts = rotated_furniture_points(furn)
        if len(pts) < 3:
            continue
        screen_pts = [to_screen(p[0], p[1]) for p in pts]
        pygame.draw.polygon(surface, C_FURN_FILL, screen_pts)
        pygame.draw.polygon(surface, C_FURN_BORDER, screen_pts, 1)
        stats["furniture_count"] += 1

    # 内容区边框（实际 fit 范围）
    view_pts = [
        to_screen(xmin, ymin),
        to_screen(xmax, ymin),
        to_screen(xmax, ymax),
        to_screen(xmin, ymax),
    ]
    pygame.draw.lines(surface, (180, 190, 200), True, view_pts, 1)

    return stats
