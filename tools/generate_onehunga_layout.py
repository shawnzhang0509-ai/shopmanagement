#!/usr/bin/env python3
"""Generate draft Onehunga store layout JSON from architectural dimensions.

Coordinate system (matches layout.py):
  - Origin (0, 0) at top-left of canvas
  - X increases to the right, Y increases downward
  - All values in millimetres

This is a best-effort draft from labelled dimensions on the floor plan.
Door openings are left as gaps in wall segments. Verify and adjust in 坪效布局编辑器.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)
OUT = os.path.join(ROOT, "data", "layouts", "onehunga.json")

WALL_T = 200  # wall thickness mm
DOOR = 1400  # doorway gap mm


def m(metres: float) -> int:
    return int(round(metres * 1000))


def wall_h(name: str, x1: int, x2: int, y: int) -> dict:
    return {
        "name": name,
        "kind": "wall",
        "points": [[x1, y], [x2, y], [x2, y + WALL_T], [x1, y + WALL_T]],
    }


def wall_v(name: str, x: int, y1: int, y2: int) -> dict:
    return {
        "name": name,
        "kind": "wall",
        "points": [[x, y1], [x + WALL_T, y1], [x + WALL_T, y2], [x, y2]],
    }


def void_rect(name: str, x1: int, y1: int, x2: int, y2: int) -> dict:
    return {
        "name": name,
        "points": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
    }


def split_h_wall(name: str, x1: int, x2: int, y: int, gap_center_x: int, gap: int = DOOR) -> list[dict]:
    half = gap // 2
    gx1, gx2 = gap_center_x - half, gap_center_x + half
    parts = []
    if gx1 > x1 + 300:
        parts.append(wall_h(f"{name}a", x1, gx1, y))
    if x2 > gx2 + 300:
        parts.append(wall_h(f"{name}b", gx2, x2, y))
    return parts


def split_v_wall(name: str, x: int, y1: int, y2: int, gap_center_y: int, gap: int = DOOR) -> list[dict]:
    half = gap // 2
    gy1, gy2 = gap_center_y - half, gap_center_y + half
    parts = []
    if gy1 > y1 + 300:
        parts.append(wall_v(f"{name}a", x, y1, gy1))
    if y2 > gy2 + 300:
        parts.append(wall_v(f"{name}b", x, gy2, y2))
    return parts


def build_obstacles() -> list[dict]:
    """Walls + non-sales voids for Onehunga (dimensions from plan labels)."""
    x_left = 0
    x_step = m(11)
    x_main = m(17)
    x_right = m(43)
    y_top = m(17)
    y_room = y_top + m(23.5)
    y_main_top = y_room
    y_main_bot = y_main_top + m(23.5)
    y_bottom = y_main_bot + m(11.2)

    obstacles: list[dict] = []

    obstacles.append(void_rect("外部空地-顶右", x_step, 0, x_right, y_top))

    obstacles.append(wall_h("外墙-顶", x_left, x_step, 0))
    obstacles.extend(split_v_wall("外墙-左", x_left, 0, y_bottom, y_top // 2))
    obstacles.append(wall_h("外墙-上翼底", x_left, x_main, y_top - WALL_T))
    obstacles.extend(
        split_v_wall("外墙-廊东", x_main - WALL_T, y_top, y_bottom, (y_top + y_room) // 2)
    )
    obstacles.extend(split_h_wall("外墙-主区顶", x_main, x_right, y_main_top - WALL_T, (x_main + x_right) // 2))
    obstacles.extend(split_v_wall("外墙-右", x_right - WALL_T, y_main_top, y_main_bot, (y_main_top + y_main_bot) // 2))
    obstacles.append(wall_h("外墙-底", x_left, x_right, y_bottom - WALL_T))

    obstacles.extend(
        split_v_wall("内墙-左室", x_main - WALL_T, y_top, y_room, y_top + m(23.5) // 2)
    )
    obstacles.extend(
        split_v_wall("内墙-廊南", x_main - WALL_T, y_room, y_main_bot, y_room + m(6))
    )
    office_x1 = x_main
    office_x2 = office_x1 + m(11.2)
    obstacles.extend(
        split_h_wall("内墙-Office", office_x1, office_x2, y_main_bot, (office_x1 + office_x2) // 2, gap=1000)
    )

    obstacles.append(void_rect("楼梯间", x_right - m(5), y_main_bot, x_right, y_bottom))
    obstacles.append(void_rect("Office", x_left, y_main_bot, x_main, y_bottom))

    return obstacles


def main():
    width_mm = m(43)
    height_mm = m(75.8)
    data = {
        "name": "Onehunga店",
        "store_slug": "onehunga",
        "store": {"width_mm": width_mm, "height_mm": height_mm},
        "furnitures": [],
        "obstacles": build_obstacles(),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "draft_note": (
            "Auto-generated draft from plan dimensions (11/17/35.8/26/23.5/11.2 m). "
            "Origin top-left. Verify door positions, office and stairs in layout editor."
        ),
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Wrote {OUT} ({width_mm / 1000:g}×{height_mm / 1000:g} m, {len(data['obstacles'])} obstacles)")


if __name__ == "__main__":
    main()
