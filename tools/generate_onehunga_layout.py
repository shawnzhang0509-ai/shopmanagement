#!/usr/bin/env python3
"""Generate Onehunga store layout from architectural floor plan (mm, origin top-left).

Plan dimensions (metres):
  Width 43 = 17 (left column) + 26 (main block)
  Height 76.3 = 17 + 35.8 + 23.5
  Top wing 11×17 | corridor column 17 wide | main sales 26×23.5 (bottom-right)
  Left room 17×23.5 (below wing) | Office 26×11.2 (bottom-left) | Stairs 5×11.2 (bottom-right)
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = os.path.join(ROOT, "data", "layouts", "onehunga.json")
TEMPLATE_OUT = os.path.join(ROOT, "data", "layouts", "_templates", "onehunga.json")

WALL_T = 200
DOOR = 1400
LAYOUT_VERSION = 5


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
    # Key coordinates from plan (mm)
    x11 = m(11)
    x17 = m(17)
    x26 = m(26)
    x38 = m(38)
    x43 = m(43)
    y17 = m(17)
    y405 = y17 + m(23.5)   # left room bottom
    y528 = y17 + m(35.8)   # main sales top / corridor bottom
    y651 = m(76.3) - m(11.2)
    y763 = m(76.3)

    obs: list[dict] = []

    # ── Non-sales voids ─────────────────────────────────────────
    obs.append(void_rect("外部空地-顶右", x11, 0, x43, y17))
    obs.append(void_rect("外部空地-上右后场", x17, y17, x43, y528))
    obs.append(void_rect("Office", 0, y651, x26, y763))
    obs.append(void_rect("楼梯间", x38, y651, x43, y763))

    # ── Exterior walls (L-shaped footprint) ───────────────────
    obs.append(wall_h("外墙-顶", 0, x11, 0))
    obs.append(wall_v("外墙-顶翼东", x11 - WALL_T, 0, y17))
    obs.append(wall_h("外墙-翼底", 0, x17, y17 - WALL_T))
    obs.append(wall_v("外墙-左翼西", 0, 0, y17))
    # Left: 35.8 m corridor segment (plan) with door
    obs.extend(split_v("外墙-左廊", 0, y17, y528, y17 + m(18)))
    # Left: 6 m opening at y=52.8 junction, then down to bottom
    obs.extend(split_v("外墙-左下", 0, y528, y763, y528 + m(3)))
    # Corridor east / void west (full 35.8 m) with door
    obs.extend(split_v("外墙-廊东", x17 - WALL_T, y17, y528, y17 + m(20)))
    # Main block north (26 m wide) with center door
    obs.extend(split_h("外墙-主区顶", x17, x43, y528 - WALL_T, (x17 + x43) // 2))
    # East exterior of main block with door
    obs.extend(split_v("外墙-右", x43 - WALL_T, y528, y763, (y528 + y763) // 2))
    obs.append(wall_h("外墙-底", 0, x43, y763 - WALL_T))

    # ── Interior partitions (match plan labels) ─────────────────
    # 23.5 m room south wall (17 m wide) — separates room from lower corridor
    obs.extend(split_h("内墙-左室底", 0, x17, y405 - WALL_T, x17 // 2))
    # Room east = corridor wall (外墙-廊东), already above

    # Office north wall (11.2 m zone above office strip)
    obs.extend(split_h("内墙-Office上", 0, x26, y651 - WALL_T, m(13)))
    # Sales floor south edge between office and stairs (door to back)
    obs.extend(split_h("内墙-卖场南", x26, x38, y651 - WALL_T, (x26 + x38) // 2))
    # Office east face
    obs.extend(split_v("内墙-Office东", x26 - WALL_T, y651, y763, y651 + m(4)))
    # Stair west face
    obs.extend(split_v("内墙-楼梯西", x38 - WALL_T, y651, y763, y651 + m(4)))

    return obs


def build_layout_data() -> dict:
    width_mm = m(43)
    height_mm = m(76.3)
    obstacles = build_obstacles()
    wall_count = sum(1 for o in obstacles if o.get("kind") == "wall")
    return {
        "name": "Onehunga店",
        "store_slug": "onehunga",
        "layout_version": LAYOUT_VERSION,
        "store": {"width_mm": width_mm, "height_mm": height_mm},
        "furnitures": [],
        "obstacles": obstacles,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "draft_note": (
            f"v5: 43×76.3 m per plan — wing 11×17, corridor 35.8 m, room 17×23.5, "
            f"main 26×23.5, office 26×11.2, stairs 5×11.2. {wall_count} wall segments."
        ),
    }


def main():
    data = build_layout_data()
    width_mm = data["store"]["width_mm"]
    height_mm = data["store"]["height_mm"]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    os.makedirs(os.path.dirname(TEMPLATE_OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    shutil.copy2(OUT, TEMPLATE_OUT)
    n = len(data["obstacles"])
    walls = sum(1 for o in data["obstacles"] if o.get("kind") == "wall")
    print(f"Wrote {OUT} and template ({width_mm / 1000:g}×{height_mm / 1000:g} m, {n} items, {walls} walls)")


if __name__ == "__main__":
    main()
