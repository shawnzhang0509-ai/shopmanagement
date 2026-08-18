#!/usr/bin/env python3
"""Generate draft Onehunga store layout JSON from architectural dimensions.

Plan reading (metres, origin top-left):
  - Total bbox: 43 × 76.3  (11+6+26 by 17+35.8+23.5)
  - Top wing: 11 wide × 17 deep (top-left)
  - Step at y=17: extends to x=17
  - Corridor runs down x=17 from y=17 to y=52.8 (35.8 m)
  - Main sales: x=17..43, y=52.8..76.3 (26 × 23.5)
  - Non-sales void: top-right above main (x=17..43, y=17..52.8) and top notch (x=11..43, y=0..17)

Walkable shop = bbox minus void polygons. Exterior walls follow the L-shaped footprint.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = os.path.join(ROOT, "data", "layouts", "onehunga.json")

WALL_T = 200
DOOR = 1400


def m(v: float) -> int:
    return int(round(v * 1000))


def wall_h(name: str, x1: int, x2: int, y: int) -> dict:
    return {"name": name, "kind": "wall", "points": [[x1, y], [x2, y], [x2, y + WALL_T], [x1, y + WALL_T]]}


def wall_v(name: str, x: int, y1: int, y2: int) -> dict:
    return {"name": name, "kind": "wall", "points": [[x, y1], [x + WALL_T, y1], [x + WALL_T, y2], [x, y2]]}


def void_rect(name: str, x1: int, y1: int, x2: int, y2: int) -> dict:
    return {"name": name, "points": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]}


def split_h(name: str, x1: int, x2: int, y: int, gap_x: int, gap: int = DOOR) -> list[dict]:
    half = gap // 2
    gx1, gx2 = gap_x - half, gap_x + half
    out = []
    if gx1 > x1 + 400:
        out.append(wall_h(f"{name}a", x1, gx1, y))
    if x2 > gx2 + 400:
        out.append(wall_h(f"{name}b", gx2, x2, y))
    return out


def split_v(name: str, x: int, y1: int, y2: int, gap_y: int, gap: int = DOOR) -> list[dict]:
    half = gap // 2
    gy1, gy2 = gap_y - half, gap_y + half
    out = []
    if gy1 > y1 + 400:
        out.append(wall_v(f"{name}a", x, y1, gy1))
    if y2 > gy2 + 400:
        out.append(wall_v(f"{name}b", x, gy2, y2))
    return out


def build_obstacles() -> list[dict]:
    # Plan constants (mm)
    x_top = m(11)
    x_corridor = m(17)
    x_right = m(43)
    y_top = m(17)
    y_main = y_top + m(35.8)
    y_bottom = y_main + m(23.5)
    y_office = y_bottom - m(11.2)

    obstacles: list[dict] = []

    # --- Non-sales voids (outside L-footprint inside bbox) ---
    obstacles.append(void_rect("外部-顶右缺口", x_top, 0, x_right, y_top))
    obstacles.append(void_rect("外部-上右后场", x_corridor, y_top, x_right, y_main))

    # --- Fixed interior non-sales ---
    obstacles.append(void_rect("Office", 0, y_office, m(26), y_bottom))
    obstacles.append(void_rect("楼梯间", x_right - m(5), y_office, x_right, y_bottom))

    # --- Exterior walls along L-shaped footprint ---
    obstacles.append(wall_h("外墙-顶", 0, x_top, 0))
    obstacles.append(wall_v("外墙-顶翼东", x_top - WALL_T, 0, y_top))
    obstacles.append(wall_h("外墙-翼底", 0, x_corridor, y_top - WALL_T))
    obstacles.extend(split_v("外墙-左", 0, 0, y_bottom, y_main // 2))
    obstacles.extend(split_v("外墙-廊东", x_corridor - WALL_T, y_top, y_main, y_top + m(20)))
    obstacles.extend(split_h("外墙-主区顶", x_corridor, x_right, y_main - WALL_T, (x_corridor + x_right) // 2))
    obstacles.extend(split_v("外墙-右", x_right - WALL_T, y_main, y_bottom, (y_main + y_bottom) // 2))
    obstacles.append(wall_h("外墙-底", 0, x_right, y_bottom - WALL_T))

    # --- Interior partitions (from plan) ---
    obstacles.extend(split_v("内墙-左室", x_corridor - WALL_T, y_top, y_top + m(23.5), y_top + m(12)))
    obstacles.extend(split_h("内墙-Office上", m(11.2), m(26), y_office - WALL_T, m(18)))

    return obstacles


def main():
    width_mm = m(43)
    height_mm = m(76.3)
    data = {
        "name": "Onehunga店",
        "store_slug": "onehunga",
        "store": {"width_mm": width_mm, "height_mm": height_mm},
        "furnitures": [],
        "obstacles": build_obstacles(),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "draft_note": (
            "v3 floor plan: 43×76.3 m L-footprint from architectural drawing. "
            "Top wing 11×17 m, corridor 35.8 m, main sales 26×23.5 m, "
            "office + stairs at bottom. Canvas size matches footprint — do not stretch to 60×90."
        ),
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Wrote {OUT} ({width_mm / 1000:g}×{height_mm / 1000:g} m, {len(data['obstacles'])} obstacles)")


if __name__ == "__main__":
    main()
