import copy
import json
import math
import os
import re
import shutil
import sys
import threading
import time
import traceback

# 无论从哪启动，都切换到脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

# IME / 中文输入：须在 import pygame 之前设置
os.environ.setdefault("SDL_IME_SHOW_UI", "1")
os.environ.setdefault("SDL_IME_SUPPORT_EXTENDED_TEXT", "1")
os.environ.setdefault("SDL_VIDEO_CENTERED", "1")
if sys.platform == "win32":
    os.environ.setdefault("SDL_WINDOWS_DPI_AWARENESS", "permonitorv2")

try:
    import pygame
except ModuleNotFoundError:
    print("未找到 pygame。Python 3.14 请安装: python -m pip install pygame-ce")
    raise SystemExit(1) from None

import tkinter as tk
from tkinter import filedialog, messagebox

from roi_lookup import lookup_roi
from heatmap_metrics import (
    adaptive_color_step,
    format_revenue_per_sqm,
    legend_tick_values,
    list_all_week_keys,
    lookup_sales_amount,
    revenue_per_sqm,
    revenue_per_sqm_to_color,
    revenue_per_sqm_to_rgba,
    clear_heatmap_cache,
    list_recent_week_keys,
    sales_data_ready,
    week_period_display,
)

pygame.init()

_tk_root = None


def get_tk_root():
    global _tk_root
    if _tk_root is None:
        _tk_root = tk.Tk()
        _tk_root.withdraw()
    return _tk_root

# ── 窗口与布局 ──────────────────────────────────────────────
SCREEN_WIDTH, SCREEN_HEIGHT = 1280, 800
SIDEBAR_WIDTH = 300
CANVAS_RECT = pygame.Rect(SIDEBAR_WIDTH, 0, SCREEN_WIDTH - SIDEBAR_WIDTH, SCREEN_HEIGHT)
GRID_SPACING = 100
ZOOM_IN, ZOOM_OUT = 1.15, 1 / 1.15
MIN_SCALE, MAX_SCALE = 0.002, 5.0

# ── 配色 ────────────────────────────────────────────────────
C_BG = (248, 250, 252)
C_SIDEBAR = (255, 255, 255)
C_CANVAS = (241, 245, 249)
C_GRID = (203, 213, 225)
C_TEXT = (15, 23, 42)
C_MUTED = (100, 116, 139)
C_BORDER = (226, 232, 240)
C_ACCENT = (37, 99, 235)
C_ACCENT_LIGHT = (219, 234, 254)
C_SUCCESS = (22, 163, 74)
C_SUCCESS_LIGHT = (220, 252, 231)
C_DANGER = (220, 38, 38)
C_DANGER_LIGHT = (254, 226, 226)
C_WARN = (234, 179, 8)
C_OBSTACLE = (248, 113, 113)
C_OBSTACLE_SEL = (252, 165, 165)
C_SELECTION = (37, 99, 235)
C_FLOOR = (255, 253, 245)
C_OUTSIDE = (148, 163, 184)
C_WALL = (51, 65, 85)

DEFAULT_STORE_WIDTH_M = 20.0
DEFAULT_STORE_HEIGHT_M = 15.0
LAYOUTS_DIR = os.path.join(SCRIPT_DIR, "data", "layouts")
LAYOUT_TEMPLATES_DIR = os.path.join(LAYOUTS_DIR, "_templates")
LEGACY_LAYOUT_FILE = os.path.join(SCRIPT_DIR, "saved_layout.json")
LAST_STORE_FILE = os.path.join(LAYOUTS_DIR, "_last.json")
CATALOG_LAYOUT_SPECS = {
    "onehunga": (43000, 76300),
}
# 固定门店列表：(显示名称, 文件标识)
STORE_CATALOG = [
    ("Onehunga店", "onehunga"),
    ("Hamilton店", "hamilton"),
    ("Westgate店", "westgate"),
    ("基督城 Colombo店", "christchurch_colombo"),
    ("基督城 Bleiham店", "christchurch_bleiham"),
]
STORE_PRESETS = [
    ("小型店 12×8 m", 12.0, 8.0),
    ("中型店 20×15 m", 20.0, 15.0),
    ("大型店 30×20 m", 30.0, 20.0),
    ("自定义", None, None),
]
APP_VERSION = "2.1.1"
MIN_SCREEN_W, MIN_SCREEN_H = 960, 600
LABEL_MIN_W, LABEL_MIN_H = 56, 28
WALL_LABEL_MIN_PX = 36  # 墙上至少显示长度（屏幕像素）
WALL_LABEL_NAME_MIN_PX = 68  # 足够宽时显示名称 + 长度
OBSTACLE_SNAP_MM = 100  # 0.1 m grid for obstacle vertices
OBSTACLE_MAGNET_MM = 300  # 拖动时顶点磁吸贴合（30cm）
ALIGN_GUIDE_SNAP_MM = 450  # 对齐参考线磁吸容差
OBSTACLE_TOUCH_TOLERANCE_MM = 80  # 贴边容差：小于此间隙不算重叠
ROTATE_FINE_DEG = 15
ROTATE_COARSE_DEG = 90
LABEL_HIT_PAD = 18  # 屏幕像素：点文字即可选中
FURNITURE_IMAGE_MIN_PX = 10  # zoom out 时仍显示的最小缩略图边长（像素）
FURNITURE_LABEL_MIN_SPAN_PX = 44  # 家具在屏幕上太小时隐藏名称，避免叠字
FURNITURE_IMG_SOURCE_PX = 96  # 统一从该尺寸解码，缩放走缓存
FURNITURE_DISPLAY_BUCKET_PX = 8  # 显示尺寸分桶，zoom 时减少重复 smoothscale
FURNITURE_DISPLAY_CACHE_MAX = 512
FURNITURE_PREFETCH_INTERVAL_MS = 1200
UNDO_LIMIT = 40
MARKER_SIZE_MM = 1000
MARKER_HIT_PAD_PX = 14
MARKER_KINDS = {
    "entrance": "入口",
    "stairs": "楼梯",
    "cashier": "收银台",
    "fire_exit": "消防出口",
}
MARKER_DEFAULT_SIZES_MM = {
    "entrance": (1000, 1000),
    "stairs": (2000, 1200),
    "cashier": (1500, 800),
    "fire_exit": (1000, 1000),
}
MARKER_COLORS = {
    "entrance": (220, 38, 38),
    "stairs": C_WALL,
    "cashier": (37, 99, 235),
    "fire_exit": (22, 163, 74),
}
WALL_ENDPOINT_HIT_PX = 14
WALL_MIN_LENGTH_MM = 200
EVENT_HOME_DEFERRED = pygame.USEREVENT + 1

# ── 字体 ────────────────────────────────────────────────────
FONT_CANDIDATES = ["Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "SimHei", "Arial"]


def load_font(size, bold=False):
    for name in FONT_CANDIDATES:
        path = pygame.font.match_font(name, bold=bold)
        if path:
            return pygame.font.Font(path, size)
    return pygame.font.SysFont(None, size, bold=bold)


FONT_TITLE = load_font(22, bold=True)
FONT_BODY = load_font(16)
FONT_SMALL = load_font(13)
FONT_TINY = load_font(11)
FONT_LABEL = load_font(14, bold=True)
FONT_MARK = load_font(12)
FONT_METRIC = load_font(13, bold=True)

screen = None
clock = None


def init_display():
    global screen, clock
    if screen is not None:
        return
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.RESIZABLE)
    pygame.display.set_caption("坪效布局编辑器")
    clock = pygame.time.Clock()
    pygame.mouse.set_visible(True)
    pygame.event.set_grab(False)
    pygame.event.clear()
    pygame.key.set_repeat(400, 35)


def handle_window_resize(w, h):
    global screen, SCREEN_WIDTH, SCREEN_HEIGHT, CANVAS_RECT
    SCREEN_WIDTH = max(MIN_SCREEN_W, int(w))
    SCREEN_HEIGHT = max(MIN_SCREEN_H, int(h))
    CANVAS_RECT = pygame.Rect(SIDEBAR_WIDTH, 0, SCREEN_WIDTH - SIDEBAR_WIDTH, SCREEN_HEIGHT)
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.RESIZABLE)


def ui_pos(pos):
    return int(pos[0]), int(pos[1])


# ── 状态 ────────────────────────────────────────────────────
offset_x, offset_y = 0.0, 0.0
scale = 0.011875
dragging_view = False
last_mouse_pos = (0, 0)
drawing_polygon = False
current_polygon = []
preview_point = None
selected_collision = None
selected_collisions: list[int] = []
collision_polygons = []
selected_furniture = None
dragging_furniture = None
selected_feature = None
placed_furnitures = []
renaming_obstacle = False
rename_collision_index = None
rename_dialog_buttons = {}
rename_input_rect = None
input_text = ""
selected_template_index = 0
dragging_collision = False
collision_drag_offset = (0, 0)
collision_drag_snapshot = None
_obstacle_clipboard = None
_undo_stack: list[dict] = []
_display_items_cache = None
search_text = ""
search_box_active = False
template_family_filter = ""
template_scroll_offset = 0
TEMPLATE_ROW_H = 56
TEMPLATE_THUMB = 40
rename_composition = ""
rotation_mode = "fine"  # "fine" = 15°, "90" = 90°
toast_message = ""
toast_until = 0
mouse_pos = (0, 0)
store_width_mm = int(DEFAULT_STORE_WIDTH_M * 1000)
store_height_mm = int(DEFAULT_STORE_HEIGHT_M * 1000)
startup_active = True
store_name = "新门店"
current_layout_path = None
store_picker_active = False
startup_buttons = None
renaming_store = False
editing_canvas_size = False
canvas_w_text = ""
canvas_h_text = ""
canvas_size_focus = "width"
canvas_size_buttons = {}
canvas_size_width_rect = None
canvas_size_height_rect = None
editing_wall_size = False
wall_length_text = ""
wall_width_text = ""
wall_size_focus = "length"
wall_size_buttons = {}
wall_length_rect = None
wall_width_rect = None
wall_size_edit_index = None
editing_obstacle_dialog = False
obstacle_edit_index = None
obstacle_edit_name = ""
obstacle_edit_length = ""
obstacle_edit_width = ""
obstacle_edit_focus = "name"
obstacle_edit_composition = ""
obstacle_edit_buttons = {}
obstacle_edit_name_rect = None
obstacle_edit_length_rect = None
obstacle_edit_width_rect = None
obstacle_edit_show_label = False
obstacle_edit_show_label_rect = None
canvas_last_click_time = 0
canvas_last_click_pos = None
DOUBLE_CLICK_MS = 450
pending_reset_confirm = False
reset_confirm_buttons = {}
_backspace_hold_start = 0
_backspace_last_delete = 0
force_rebuild_startup = False
_store_summary_cache = {}
_pending_save_snapshot = None
_save_thread = None
_save_generation = 0
_catalog_refresh_thread = None
_catalog_refresh_ready = False
marquee_active = False
marquee_start = None
marquee_current = None
multi_drag_snapshots: dict[int, list] = {}
active_alignment_guides: list[dict] = []
_next_group_id = 1
layout_markers: list[dict] = []
selected_marker_index = None
dragging_marker = False
marker_drag_offset = (0.0, 0.0)
editing_marker_dialog = False
editing_marker_index = None
marker_edit_name = ""
marker_edit_show_label = False
marker_edit_focus = "name"
marker_edit_composition = ""
marker_edit_buttons = {}
marker_edit_name_rect = None
marker_edit_show_label_rect = None
marker_edit_length = ""
marker_edit_width = ""
marker_edit_length_rect = None
marker_edit_width_rect = None
dragging_wall_endpoint = None
wall_endpoint_snapshot = None
_furniture_display_cache: dict[tuple[str, str, int, int], object] = {}
_furniture_aspect_cache: dict[tuple[str, str], float] = {}
_last_furniture_prefetch_ms = 0
_next_furniture_instance_id = 1
pending_bind_child = None
show_roi_overlap_mode = False
ROI_OVERLAP_BLINK_MS = 750
heatmap_week_count = 4
heatmap_week_mode = "single"  # single | range
heatmap_week_index = -1
heatmap_vmin = 0.0
heatmap_vmax = 1.0
heatmap_color_step = 200.0
heatmap_week_bar_rects: dict[str, pygame.Rect] = {}
_pending_heatmap_week: str | None = None
_heatmap_metrics_dirty = True
_sidebar_metric_cache: dict[tuple, tuple[float, float]] = {}
furniture_drag_snapshot: dict[str, tuple[float, float]] = {}


def clear_obstacle_selection():
    global selected_collision, selected_collisions
    selected_collision = None
    selected_collisions = []


def set_obstacle_selection(indices, *, toast_msg: str | None = None):
    global selected_collision, selected_collisions, selected_furniture, selected_feature, selected_marker_index
    selected_collisions = sorted({i for i in indices if 0 <= i < len(collision_polygons)})
    selected_collision = selected_collisions[0] if selected_collisions else None
    selected_furniture = selected_feature = None
    selected_marker_index = None
    if toast_msg is not None:
        show_toast(toast_msg)
    elif len(selected_collisions) == 1:
        show_toast(f"选中: {collision_polygons[selected_collision]['name']}")
    elif len(selected_collisions) > 1:
        show_toast(f"已选 {len(selected_collisions)} 个障碍/墙体")


def expand_group_members(indices) -> list[int]:
    out = set(indices)
    for i in list(out):
        if 0 <= i < len(collision_polygons):
            gid = collision_polygons[i].get("group_id")
            if gid:
                for j, col in enumerate(collision_polygons):
                    if col.get("group_id") == gid:
                        out.add(j)
    return sorted(out)


def obstacle_bbox(col) -> tuple[float, float, float, float]:
    pts = col["points"]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def obstacles_in_screen_rect(x1, y1, x2, y2) -> list[int]:
    left, right = sorted([x1, x2])
    top, bottom = sorted([y1, y2])
    wx1, wy1 = screen_to_world(left, top)
    wx2, wy2 = screen_to_world(right, bottom)
    bl, bt = min(wx1, wx2), min(wy1, wy2)
    br, bb = max(wx1, wx2), max(wy1, wy2)
    hits = []
    for i, col in enumerate(collision_polygons):
        cl, ct, cr, cb = obstacle_bbox(col)
        if cr >= bl and cl <= br and cb >= bt and ct <= bb:
            hits.append(i)
    return hits


def select_all_obstacles():
    if not collision_polygons:
        show_toast("画布上没有障碍或墙体")
        return
    set_obstacle_selection(range(len(collision_polygons)), toast_msg=f"已全选 {len(collision_polygons)} 项")


def group_selected_obstacles():
    global _next_group_id
    if len(selected_collisions) < 2:
        show_toast("请至少选中 2 个障碍/墙体再成组")
        return
    push_undo()
    gid = f"g{_next_group_id}"
    _next_group_id += 1
    for i in selected_collisions:
        collision_polygons[i]["group_id"] = gid
    show_toast(f"已成组 {len(selected_collisions)} 项（移动/旋转联动）")


def ungroup_selected_obstacles():
    if not selected_collisions:
        show_toast("请先选中要解组的障碍/墙体")
        return
    push_undo()
    gids = {
        collision_polygons[i].get("group_id")
        for i in selected_collisions
        if collision_polygons[i].get("group_id")
    }
    if not gids:
        show_toast("选中项未在组内")
        return
    for col in collision_polygons:
        if col.get("group_id") in gids:
            col.pop("group_id", None)
    show_toast("已解组")


def try_move_obstacles_batch(indices, dx, dy) -> bool:
    global active_alignment_guides
    if not indices:
        active_alignment_guides = []
        return False
    originals = {i: [tuple(p) for p in collision_polygons[i]["points"]] for i in indices}
    dx, dy = clamp_group_translation(originals, dx, dy)
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        active_alignment_guides = []
        return False
    trials = {}
    for i in indices:
        trials[i] = [(x + dx, y + dy) for x, y in originals[i]]
    all_pts = [p for pts in trials.values() for p in pts]
    snap_dx, snap_dy, guides = compute_alignment_snap(all_pts, indices)
    if abs(snap_dx) > 1e-9 or abs(snap_dy) > 1e-9:
        for i in trials:
            trials[i] = [(x + snap_dx, y + snap_dy) for x, y in trials[i]]
        all_pts = [p for pts in trials.values() for p in pts]
    snapped = magnet_snap_translate(all_pts, indices)
    idx = 0
    for i in sorted(trials):
        n = len(trials[i])
        trials[i] = snapped[idx : idx + n]
        idx += n
    active_alignment_guides = guides if guides else []
    zone_indices = [i for i in indices if obstacle_is_zone(collision_polygons[i])]
    for a in range(len(zone_indices)):
        for b in range(a + 1, len(zone_indices)):
            ia, ib = zone_indices[a], zone_indices[b]
            if polygons_interior_overlap(trials[ia], trials[ib]):
                active_alignment_guides = []
                return False
    for i in zone_indices:
        if zone_overlaps_any(trials[i], *indices)[0]:
            active_alignment_guides = []
            return False
    for i, pts in trials.items():
        collision_polygons[i]["points"] = [[int(round(x)), int(round(y))] for x, y in pts]
    return True


def batch_has_zone_overlap(indices) -> bool:
    idxs = [i for i in indices if obstacle_is_zone(collision_polygons[i])]
    for a in range(len(idxs)):
        for b in range(a + 1, len(idxs)):
            if polygons_interior_overlap(
                collision_polygons[idxs[a]]["points"],
                collision_polygons[idxs[b]]["points"],
            ):
                return True
    return False


def zone_overlap_hint(index) -> str | None:
    if not obstacle_is_zone(collision_polygons[index]):
        return None
    _, other_name = zone_overlaps_any(collision_polygons[index]["points"], index)
    return other_name or None


def show_toast(msg, duration_ms=2500):
    global toast_message, toast_until
    toast_message = msg
    toast_until = pygame.time.get_ticks() + duration_ms
    print(msg)


def _furniture_snapshot(furnitures):
    return [
        {
            "name": f.name,
            "roi": f.roi,
            "points": [tuple(p) for p in f.points],
            "x": f.x,
            "y": f.y,
            "rotation": f.rotation,
            "instance_id": getattr(f, "instance_id", "") or "",
            "attach_to": getattr(f, "attach_to", "") or "",
            "product_family": getattr(f, "product_family", "") or "",
        }
        for f in furnitures
    ]


def _furnitures_from_snapshot(snap):
    out = []
    for d in snap:
        furn = Furniture(
            d["name"],
            d["roi"],
            [tuple(p) for p in d["points"]],
            d.get("x", 0),
            d.get("y", 0),
            d.get("rotation", 0),
            product_family=d.get("product_family", "") or "",
        )
        furn.instance_id = d.get("instance_id", "") or ""
        furn.attach_to = d.get("attach_to", "") or ""
        out.append(furn)
    return out


def _alloc_furniture_instance_id() -> str:
    global _next_furniture_instance_id
    iid = f"f{_next_furniture_instance_id}"
    _next_furniture_instance_id += 1
    return iid


def sync_furniture_instance_ids():
    global _next_furniture_instance_id
    max_n = 0
    for furn in placed_furnitures:
        iid = getattr(furn, "instance_id", "") or ""
        if not iid:
            furn.instance_id = _alloc_furniture_instance_id()
            iid = furn.instance_id
        if isinstance(iid, str) and iid.startswith("f"):
            try:
                max_n = max(max_n, int(iid[1:]))
            except ValueError:
                pass
    _next_furniture_instance_id = max(max_n + 1, _next_furniture_instance_id)


def furniture_by_instance_id(instance_id: str):
    if not instance_id:
        return None
    for furn in placed_furnitures:
        if getattr(furn, "instance_id", "") == instance_id:
            return furn
    return None


def furniture_attached_descendants(root) -> list:
    if root is None:
        return []
    ids = {root.instance_id}
    out: list = []
    changed = True
    while changed:
        changed = False
        for furn in placed_furnitures:
            if furn.attach_to in ids and furn.instance_id not in ids:
                ids.add(furn.instance_id)
                out.append(furn)
                changed = True
    return out


def furniture_drag_pack(root):
    if root is None:
        return []
    return [root, *furniture_attached_descendants(root)]


def bring_furniture_to_front(furn):
    global placed_furnitures
    if furn not in placed_furnitures:
        return
    push_undo()
    placed_furnitures.remove(furn)
    placed_furnitures.append(furn)
    show_toast(f"{furn.name} 已置于顶层")


def send_furniture_to_back(furn):
    global placed_furnitures
    if furn not in placed_furnitures:
        return
    push_undo()
    placed_furnitures.remove(furn)
    placed_furnitures.insert(0, furn)
    show_toast(f"{furn.name} 已置于底层")


def start_bind_to_parent():
    global pending_bind_child
    if selected_furniture is None:
        show_toast("请先选中子件（如床垫）")
        return
    pending_bind_child = selected_furniture
    show_toast(f"已选子件 {selected_furniture.name}，请点父件（如床架）")


def cancel_bind_to_parent():
    global pending_bind_child
    pending_bind_child = None


def complete_bind_to_parent(parent):
    global pending_bind_child
    child = pending_bind_child
    if child is None or parent is None or child is parent:
        return False
    if parent.attach_to == child.instance_id:
        show_toast("不能循环绑定")
        pending_bind_child = None
        return True
    push_undo()
    child.attach_to = parent.instance_id
    pending_bind_child = None
    show_toast(f"已绑定：{child.name} → {parent.name}（拖父件时联动；可开「ROI重叠闪烁」查看坪效）")
    return True


def unbind_furniture(furn=None):
    global pending_bind_child
    furn = furn or selected_furniture
    if furn is None:
        show_toast("请先选中要解绑的家具")
        return
    if not furn.attach_to:
        show_toast("该家具未绑定父件")
        return
    push_undo()
    furn.attach_to = ""
    pending_bind_child = None
    show_toast(f"已解绑 {furn.name}")


def toggle_roi_overlap_mode(buttons=None):
    global show_roi_overlap_mode
    show_roi_overlap_mode = not show_roi_overlap_mode
    if buttons and "roi_overlap" in buttons:
        buttons["roi_overlap"].active = show_roi_overlap_mode
    show_toast(
        "已开启 ROI 重叠闪烁（床+床垫等叠放时交替显示坪效）"
        if show_roi_overlap_mode
        else "已关闭 ROI 重叠模式"
    )


def capture_layout_state():
    return {
        "collision_polygons": copy.deepcopy(collision_polygons),
        "placed_furnitures": _furniture_snapshot(placed_furnitures),
        "layout_markers": copy.deepcopy(layout_markers),
        "store_width_mm": store_width_mm,
        "store_height_mm": store_height_mm,
        "store_name": store_name,
    }


def push_undo():
    global _undo_stack
    _undo_stack.append(capture_layout_state())
    if len(_undo_stack) > UNDO_LIMIT:
        _undo_stack.pop(0)


def clear_undo():
    global _undo_stack
    _undo_stack = []


def undo_layout():
    global collision_polygons, placed_furnitures, selected_collision, selected_collisions
    global selected_furniture, selected_feature, store_width_mm, store_height_mm, store_name
    global layout_markers, selected_marker_index
    if not _undo_stack:
        show_toast("无可撤销的操作")
        return
    state = _undo_stack.pop()
    collision_polygons = state["collision_polygons"]
    placed_furnitures = _furnitures_from_snapshot(state["placed_furnitures"])
    sync_furniture_instance_ids()
    layout_markers = state.get("layout_markers", [])
    store_width_mm = state.get("store_width_mm", store_width_mm)
    store_height_mm = state.get("store_height_mm", store_height_mm)
    store_name = state.get("store_name", store_name)
    clear_obstacle_selection()
    selected_furniture = selected_feature = None
    selected_marker_index = None
    show_toast("已撤销")


def sync_group_id_counter():
    global _next_group_id
    max_n = 0
    for col in collision_polygons:
        gid = col.get("group_id", "")
        if isinstance(gid, str) and gid.startswith("g"):
            try:
                max_n = max(max_n, int(gid[1:]))
            except ValueError:
                pass
    _next_group_id = max_n + 1


def copy_selected_obstacle():
    global _obstacle_clipboard
    if not selected_collisions:
        show_toast("请先选中障碍或墙体")
        return False
    if len(selected_collisions) == 1:
        _obstacle_clipboard = copy.deepcopy(collision_polygons[selected_collisions[0]])
        show_toast(f"已复制: {_obstacle_clipboard['name']}")
    else:
        _obstacle_clipboard = [copy.deepcopy(collision_polygons[i]) for i in selected_collisions]
        show_toast(f"已复制 {len(_obstacle_clipboard)} 项")
    return True


def paste_obstacle():
    global selected_collision, selected_furniture, selected_feature, selected_collisions
    if not _obstacle_clipboard:
        show_toast("剪贴板为空，请先 Ctrl+C 复制")
        return
    push_undo()
    items = _obstacle_clipboard if isinstance(_obstacle_clipboard, list) else [_obstacle_clipboard]
    names = {c.get("name") for c in collision_polygons}
    new_indices = []
    offset = OBSTACLE_SNAP_MM * 3
    for src in items:
        new_ob = copy.deepcopy(src)
        base_name = new_ob.get("name", "障碍物")
        candidate = f"{base_name}_copy"
        n = 2
        while candidate in names:
            candidate = f"{base_name}_copy{n}"
            n += 1
        new_ob["name"] = candidate
        names.add(candidate)
        new_ob["points"] = [(x + offset, y + offset) for x, y in new_ob["points"]]
        if not polygon_fully_inside_store(new_ob["points"]):
            new_ob["points"] = [(x - offset, y - offset) for x, y in new_ob["points"]]
        if obstacle_is_zone(new_ob) and zone_overlaps_any(new_ob["points"])[0]:
            show_toast("粘贴会与其它障碍区域重叠，已跳过")
            continue
        collision_polygons.append(new_ob)
        new_indices.append(len(collision_polygons) - 1)
    if not new_indices:
        if _undo_stack:
            _undo_stack.pop()
        show_toast("粘贴失败：与现有障碍重叠")
        return
    set_obstacle_selection(new_indices, toast_msg=f"已粘贴 {len(new_indices)} 项")


# ── UI 组件 ─────────────────────────────────────────────────
class Button:
    def __init__(self, rect, label, action, primary=False, danger=False, toggle=False):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.action = action
        self.primary = primary
        self.danger = danger
        self.toggle = toggle
        self.active = False
        self.enabled = True

    def contains(self, pos):
        if not self.enabled:
            return False
        return self.rect.collidepoint(ui_pos(pos))

    def draw(self, surface):
        hover = self.enabled and self.rect.collidepoint(ui_pos(mouse_pos))
        if self.toggle and self.active:
            bg, fg, border = C_ACCENT, (255, 255, 255), C_ACCENT
        elif self.danger:
            bg = C_DANGER if hover else C_DANGER_LIGHT
            fg = (255, 255, 255) if hover else C_DANGER
            border = C_DANGER
        elif self.primary:
            bg = (29, 78, 216) if hover else C_ACCENT
            fg = (255, 255, 255)
            border = C_ACCENT
        else:
            bg = C_ACCENT_LIGHT if hover else (255, 255, 255)
            fg = C_ACCENT if hover else C_TEXT
            border = C_BORDER

        if not self.enabled:
            bg, fg, border = (241, 245, 249), C_MUTED, C_BORDER

        pygame.draw.rect(surface, bg, self.rect, border_radius=8)
        pygame.draw.rect(surface, border, self.rect, 1, border_radius=8)
        text = FONT_SMALL.render(self.label, True, fg)
        surface.blit(text, text.get_rect(center=self.rect.center))


class InputBox:
    def __init__(self, rect, placeholder=""):
        self.rect = pygame.Rect(rect)
        self.text = ""
        self.placeholder = placeholder
        self.active = False

    def contains(self, pos):
        return self.rect.collidepoint(ui_pos(pos))

    def draw(self, surface):
        bg = (255, 255, 255) if self.active else (248, 250, 252)
        pygame.draw.rect(surface, bg, self.rect, border_radius=8)
        border = C_ACCENT if self.active else C_BORDER
        pygame.draw.rect(surface, border, self.rect, 2 if self.active else 1, border_radius=8)
        display = self.text if self.text else self.placeholder
        color = C_TEXT if self.text else C_MUTED
        prefix = "搜索 " if not self.text else ""
        surface.blit(FONT_SMALL.render(prefix + display, True, color), (self.rect.x + 10, self.rect.y + 9))


# ── 几何工具 ────────────────────────────────────────────────
def point_in_poly(x, y, poly):
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-9) + xi):
            inside = not inside
        j = i
    return inside


def screen_to_world(sx, sy):
    return offset_x + (sx - SIDEBAR_WIDTH) / scale, offset_y + sy / scale


def world_to_screen(wx, wy):
    return (wx - offset_x) * scale + SIDEBAR_WIDTH, (wy - offset_y) * scale


def store_rect_points():
    return [
        (0, 0),
        (store_width_mm, 0),
        (store_width_mm, store_height_mm),
        (0, store_height_mm),
    ]


def set_store_size(width_m, height_m):
    global store_width_mm, store_height_mm
    width_m = float(width_m)
    height_m = float(height_m)
    if width_m <= 0 or height_m <= 0:
        raise ValueError("门店宽高必须大于 0")
    store_width_mm = int(round(width_m * 1000))
    store_height_mm = int(round(height_m * 1000))
    fit_view_to_store()


def fit_view_to_store():
    global offset_x, offset_y, scale
    margin = 64
    avail_w = max(1, CANVAS_RECT.width - margin * 2)
    avail_h = max(1, SCREEN_HEIGHT - margin * 2)
    scale = min(avail_w / store_width_mm, avail_h / store_height_mm)
    scale = max(MIN_SCALE, min(MAX_SCALE, scale))
    store_cx = store_width_mm / 2
    store_cy = store_height_mm / 2
    canvas_cx = SIDEBAR_WIDTH + CANVAS_RECT.width / 2
    canvas_cy = SCREEN_HEIGHT / 2
    offset_x = store_cx - (canvas_cx - SIDEBAR_WIDTH) / scale
    offset_y = store_cy - canvas_cy / scale


def viewport_world_center():
    return screen_to_world(SIDEBAR_WIDTH + CANVAS_RECT.width / 2, SCREEN_HEIGHT / 2)


def furniture_shape_centroid(furn):
    return (
        sum(p[0] for p in furn.points) / len(furn.points),
        sum(p[1] for p in furn.points) / len(furn.points),
    )


def furniture_overlaps_zone(furn) -> bool:
    pts = furn.get_rotated_points()
    for col in collision_polygons:
        if obstacle_is_wall(col):
            continue
        if polygons_interior_overlap(pts, col["points"]):
            return True
    return False


def place_furniture_at_world(furn, wx, wy):
    local_cx, local_cy = furniture_shape_centroid(furn)
    furn.x = wx - local_cx
    furn.y = wy - local_cy


def find_clear_furniture_position(furn, wx, wy):
    place_furniture_at_world(furn, wx, wy)
    if polygon_fully_inside_store(furn.get_rotated_points()) and not furniture_overlaps_zone(furn):
        return
    step = 800
    for ring in range(1, 20):
        for dx, dy in (
            (step * ring, 0),
            (-step * ring, 0),
            (0, step * ring),
            (0, -step * ring),
            (step * ring, step * ring),
            (-step * ring, step * ring),
            (step * ring, -step * ring),
            (-step * ring, -step * ring),
        ):
            place_furniture_at_world(furn, wx + dx, wy + dy)
            if polygon_fully_inside_store(furn.get_rotated_points()) and not furniture_overlaps_zone(furn):
                return
    place_furniture_at_world(furn, wx, wy)


def clear_marker_selection():
    global selected_marker_index
    selected_marker_index = None


def set_marker_selection(index, *, toast_msg: str | None = None):
    global selected_marker_index, selected_furniture, selected_feature
    if index is None or index < 0 or index >= len(layout_markers):
        selected_marker_index = None
        return
    selected_marker_index = index
    selected_furniture = selected_feature = None
    clear_obstacle_selection()
    marker = layout_markers[index]
    kind_label = MARKER_KINDS.get(marker.get("kind"), "图标")
    label = marker.get("label") or kind_label
    if toast_msg is not None:
        show_toast(toast_msg)
    else:
        show_toast(f"选中: {label}")


def marker_default_label(kind: str) -> str:
    return MARKER_KINDS.get(kind, "图标")


def new_layout_marker(kind: str, x_mm: float, y_mm: float) -> dict:
    dw, dh = MARKER_DEFAULT_SIZES_MM.get(kind, (MARKER_SIZE_MM, MARKER_SIZE_MM))
    return {
        "kind": kind,
        "x_mm": int(round(x_mm)),
        "y_mm": int(round(y_mm)),
        "rotation": 0.0,
        "width_mm": dw,
        "height_mm": dh,
        "label": marker_default_label(kind),
    }


def marker_width_mm(marker) -> int:
    kind = marker.get("kind", "entrance")
    default_w, _ = MARKER_DEFAULT_SIZES_MM.get(kind, (MARKER_SIZE_MM, MARKER_SIZE_MM))
    return int(marker.get("width_mm", default_w))


def marker_height_mm(marker) -> int:
    kind = marker.get("kind", "entrance")
    _, default_h = MARKER_DEFAULT_SIZES_MM.get(kind, (MARKER_SIZE_MM, MARKER_SIZE_MM))
    return int(marker.get("height_mm", default_h))


def marker_screen_dims(marker) -> tuple[float, float]:
    return (
        max(16.0, marker_width_mm(marker) * scale),
        max(12.0, marker_height_mm(marker) * scale),
    )


def marker_color(kind: str):
    return MARKER_COLORS.get(kind, C_WALL)


def marker_screen_center(marker) -> tuple[float, float]:
    return world_to_screen(marker["x_mm"], marker["y_mm"])


def _rotate_screen_point(cx, cy, x, y, deg):
    rad = math.radians(deg)
    dx, dy = x - cx, y - cy
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    return cx + dx * cos_a - dy * sin_a, cy + dx * sin_a + dy * cos_a


def _marker_local_to_screen(cx, cy, lx, ly, rotation):
    return _rotate_screen_point(cx, cy, cx + lx, cy + ly, rotation)


def marker_local_corners(marker) -> list[tuple[float, float]]:
    hw = marker_width_mm(marker) / 2.0
    hh = marker_height_mm(marker) / 2.0
    cx, cy = marker["x_mm"], marker["y_mm"]
    corners = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
    return rotate_polygon_points(corners, marker.get("rotation", 0), (cx, cy))


def marker_hit_test(mx, my, marker) -> bool:
    cx, cy = marker_screen_center(marker)
    w_px, h_px = marker_screen_dims(marker)
    radius = max(w_px, h_px) * 0.55 + MARKER_HIT_PAD_PX
    dx, dy = mx - cx, my - cy
    return dx * dx + dy * dy <= radius * radius


def should_show_marker_label(marker, index: int) -> bool:
    return index == selected_marker_index or bool(marker.get("user_named"))


def draw_marker_entrance(surface, cx, cy, w_px, h_px, rotation, color, width=3):
    half_w = w_px * 0.46
    half_h = h_px * 0.46
    frame = [
        (-half_w * 0.35, half_h * 0.45),
        (-half_w * 0.35, -half_h * 0.25),
        (half_w * 0.35, -half_h * 0.25),
        (half_w * 0.35, half_h * 0.45),
    ]
    frame_pts = [_marker_local_to_screen(cx, cy, x, y, rotation) for x, y in frame]
    pygame.draw.lines(surface, color, False, frame_pts, width)
    arrow = [
        (0, -half_h * 0.82),
        (-half_w * 0.22, -half_h * 0.42),
        (half_w * 0.22, -half_h * 0.42),
        (0, -half_h * 0.82),
    ]
    arrow_pts = [_marker_local_to_screen(cx, cy, x, y, rotation) for x, y in arrow]
    pygame.draw.lines(surface, color, False, arrow_pts, width)


def draw_marker_stairs(surface, cx, cy, w_px, h_px, rotation, color, width=2):
    half_w = w_px * 0.48
    base_y = h_px * 0.42
    base_pts = [
        _marker_local_to_screen(cx, cy, -half_w, base_y, rotation),
        _marker_local_to_screen(cx, cy, half_w, base_y, rotation),
    ]
    pygame.draw.line(surface, color, base_pts[0], base_pts[1], width + 1)
    rung_top = -h_px * 0.38
    for i in range(5):
        t = i / 4
        x = -half_w + t * (2 * half_w)
        p1 = _marker_local_to_screen(cx, cy, x, rung_top, rotation)
        p2 = _marker_local_to_screen(cx, cy, x, base_y, rotation)
        pygame.draw.line(surface, color, p1, p2, width)
    elbow = [
        (half_w * 0.55, base_y),
        (half_w * 0.55, h_px * 0.62),
        (half_w * 0.15, h_px * 0.62),
    ]
    elbow_pts = [_marker_local_to_screen(cx, cy, x, y, rotation) for x, y in elbow]
    pygame.draw.lines(surface, color, False, elbow_pts, width)


def draw_marker_cashier(surface, cx, cy, w_px, h_px, rotation, color, width=2):
    half_w = w_px * 0.46
    half_h = h_px * 0.46
    counter = [
        (-half_w, half_h * 0.35),
        (half_w, half_h * 0.35),
        (half_w, -half_h * 0.15),
        (-half_w * 0.15, -half_h * 0.15),
        (-half_w * 0.15, -half_h * 0.45),
        (-half_w, -half_h * 0.45),
        (-half_w, half_h * 0.35),
    ]
    pts = [_marker_local_to_screen(cx, cy, x, y, rotation) for x, y in counter]
    pygame.draw.lines(surface, color, False, pts, width + 1)
    screen = [
        (-half_w * 0.55, -half_h * 0.55),
        (half_w * 0.15, -half_h * 0.55),
        (half_w * 0.15, -half_h * 0.25),
        (-half_w * 0.55, -half_h * 0.25),
        (-half_w * 0.55, -half_h * 0.55),
    ]
    screen_pts = [_marker_local_to_screen(cx, cy, x, y, rotation) for x, y in screen]
    pygame.draw.lines(surface, color, False, screen_pts, width)


def draw_marker_fire_exit(surface, cx, cy, w_px, h_px, rotation, color, width=2):
    half_w = w_px * 0.42
    half_h = h_px * 0.42
    frame = [
        (-half_w * 0.3, half_h * 0.4),
        (-half_w * 0.3, -half_h * 0.3),
        (half_w * 0.3, -half_h * 0.3),
        (half_w * 0.3, half_h * 0.4),
    ]
    frame_pts = [_marker_local_to_screen(cx, cy, x, y, rotation) for x, y in frame]
    pygame.draw.lines(surface, color, False, frame_pts, width + 1)
    person = [
        (half_w * 0.55, half_h * 0.35),
        (half_w * 0.55, -half_h * 0.05),
        (half_w * 0.85, -half_h * 0.25),
        (half_w * 0.55, -half_h * 0.25),
        (half_w * 0.65, -half_h * 0.45),
    ]
    person_pts = [_marker_local_to_screen(cx, cy, x, y, rotation) for x, y in person]
    pygame.draw.lines(surface, color, False, person_pts, width)


def draw_marker_footprint(surface, marker, selected: bool):
    if not selected:
        return
    pts = [world_to_screen(x, y) for x, y in marker_local_corners(marker)]
    if len(pts) >= 3:
        pygame.draw.polygon(surface, C_ACCENT_LIGHT, pts)
        pygame.draw.polygon(surface, C_ACCENT, pts, 1)


def draw_single_layout_marker(surface, marker, index: int):
    cx, cy = marker_screen_center(marker)
    w_px, h_px = marker_screen_dims(marker)
    selected = index == selected_marker_index
    kind = marker.get("kind", "entrance")
    color = marker_color(kind)
    rotation = marker.get("rotation", 0)
    draw_marker_footprint(surface, marker, selected)
    if selected:
        ring = int(max(w_px, h_px) * 0.55)
        pygame.draw.circle(surface, C_ACCENT_LIGHT, (int(cx), int(cy)), ring + 4)
        pygame.draw.circle(surface, C_ACCENT, (int(cx), int(cy)), ring, 2)
    if kind == "stairs":
        draw_marker_stairs(surface, cx, cy, w_px, h_px, rotation, color)
    elif kind == "cashier":
        draw_marker_cashier(surface, cx, cy, w_px, h_px, rotation, color)
    elif kind == "fire_exit":
        draw_marker_fire_exit(surface, cx, cy, w_px, h_px, rotation, color)
    else:
        draw_marker_entrance(surface, cx, cy, w_px, h_px, rotation, color)
    if should_show_marker_label(marker, index):
        label = marker.get("label") or marker_default_label(kind)
        draw_label_pill(surface, label, (cx, cy - max(w_px, h_px) * 0.72), font=FONT_SMALL, fg=color)


def draw_layout_markers(surface):
    for i, marker in enumerate(layout_markers):
        draw_single_layout_marker(surface, marker, i)


def add_marker_to_canvas(kind: str):
    global selected_marker_index
    if kind not in MARKER_KINDS:
        show_toast("未知图标类型")
        return
    wx, wy = viewport_world_center()
    wx, wy = snap_world_point(wx, wy)
    push_undo()
    layout_markers.append(new_layout_marker(kind, wx, wy))
    set_marker_selection(len(layout_markers) - 1)
    w_m = marker_width_mm(layout_markers[-1]) / 1000
    h_m = marker_height_mm(layout_markers[-1]) / 1000
    show_toast(
        f"已添加{MARKER_KINDS[kind]} {w_m:g}×{h_m:g} m（可拖动、旋转，双击编辑尺寸）"
    )


def normalize_layout_markers(markers: list[dict]) -> list[dict]:
    out = []
    for marker in markers:
        m = copy.deepcopy(marker)
        kind = m.get("kind", "entrance")
        dw, dh = MARKER_DEFAULT_SIZES_MM.get(kind, (MARKER_SIZE_MM, MARKER_SIZE_MM))
        m.setdefault("width_mm", dw)
        m.setdefault("height_mm", dh)
        out.append(m)
    return out


def wall_segment_endpoints(points):
    metrics = obstacle_rect_metrics(points)
    if not metrics:
        return None
    cx, cy, length_mm, width_mm = metrics
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    horizontal = (max_x - min_x) >= (max_y - min_y)
    if horizontal:
        endpoints = ((min_x, cy), (max_x, cy))
    else:
        endpoints = ((cx, min_y), (cx, max_y))
    return endpoints, length_mm, width_mm, horizontal


def wall_endpoint_hit_test(mx, my, index: int):
    col = collision_polygons[index]
    if not obstacle_is_wall(col):
        return None
    data = wall_segment_endpoints(col["points"])
    if not data:
        return None
    endpoints, _, _, _ = data
    hit_r = max(12, WALL_ENDPOINT_HIT_PX)
    for i, ep in enumerate(endpoints):
        sx, sy = world_to_screen(*ep)
        if (mx - sx) ** 2 + (my - sy) ** 2 <= hit_r * hit_r:
            return i
    return None


def resize_wall_by_endpoint(index: int, end_idx: int, wx: float, wy: float) -> bool:
    col = collision_polygons[index]
    data = wall_segment_endpoints(col["points"])
    if not data:
        return False
    endpoints, _, width_mm, horizontal = data
    fixed = endpoints[1 - end_idx]
    wx, wy = snap_world_point(wx, wy)
    if horizontal:
        new_length = abs(wx - fixed[0])
        if new_length < WALL_MIN_LENGTH_MM:
            return False
        new_cx = (wx + fixed[0]) / 2
        new_cy = fixed[1]
        new_points = rect_points_centered(new_cx, new_cy, new_length, width_mm)
    else:
        new_length = abs(wy - fixed[1])
        if new_length < WALL_MIN_LENGTH_MM:
            return False
        new_cx = fixed[0]
        new_cy = (wy + fixed[1]) / 2
        new_points = rect_points_centered(new_cx, new_cy, width_mm, new_length)
    new_points = clip_obstacle_points(new_points)
    if len(new_points) < 3 or polygon_area(new_points) <= 1.0:
        return False
    if not polygon_fully_inside_store(new_points):
        return False
    col["points"] = [[int(round(x)), int(round(y))] for x, y in new_points]
    return True


def draw_wall_endpoint_handles(surface):
    if len(selected_collisions) != 1:
        return
    idx = selected_collision
    if not obstacle_is_wall(collision_polygons[idx]):
        return
    data = wall_segment_endpoints(collision_polygons[idx]["points"])
    if not data:
        return
    endpoints, _, _, _ = data
    for ep in endpoints:
        sx, sy = world_to_screen(*ep)
        rect = pygame.Rect(0, 0, 14, 14)
        rect.center = (int(sx), int(sy))
        pygame.draw.rect(surface, C_ACCENT, rect, border_radius=3)
        pygame.draw.rect(surface, (255, 255, 255), rect, 2, border_radius=3)


def snap_world_mm(value):
    return round(value / OBSTACLE_SNAP_MM) * OBSTACLE_SNAP_MM


def snap_world_point(wx, wy):
    return snap_world_mm(wx), snap_world_mm(wy)


def format_snap_m(mm_value):
    return f"{snap_world_mm(mm_value) / 1000:.1f}"


def store_edge_offsets_mm(x, y):
    """Distances from a point to store edges in mm (for corner readout)."""
    return (
        snap_world_mm(x),
        snap_world_mm(y),
        snap_world_mm(store_width_mm - x),
        snap_world_mm(store_height_mm - y),
    )


def boundary_corner_label(x, y):
    """Human-readable distances to corners; emphasise top-right for layout work."""
    left, top, right, bottom = store_edge_offsets_mm(x, y)
    left_m = left / 1000
    top_m = top / 1000
    right_m = right / 1000
    bottom_m = bottom / 1000
    tol = OBSTACLE_SNAP_MM / 2
    on_top = top <= tol
    on_bottom = bottom <= tol
    on_left = left <= tol
    on_right = right <= tol
    if on_top and not on_left and not on_right:
        return f"距左上 {left_m:.1f}m · 距右上 {right_m:.1f}m"
    if on_bottom and not on_left and not on_right:
        return f"距左下 {left_m:.1f}m · 距右下 {right_m:.1f}m"
    if on_left and not on_top and not on_bottom:
        return f"距左上 {top_m:.1f}m · 距左下 {bottom_m:.1f}m"
    if on_right and not on_top and not on_bottom:
        return f"距右上 {top_m:.1f}m · 距右下 {bottom_m:.1f}m"
    if on_top and on_left:
        return f"左上角"
    if on_top and on_right:
        return f"右上角"
    if on_bottom and on_left:
        return f"左下角"
    if on_bottom and on_right:
        return f"右下角"
    return f"←{left_m:.1f}m ↑{top_m:.1f}m →{right_m:.1f}m ↓{bottom_m:.1f}m"


def segment_rect_crossings(p1, p2, xmin, ymin, xmax, ymax):
    x1, y1 = p1
    x2, y2 = p2
    dx = x2 - x1
    dy = y2 - y1
    hits = []
    if abs(dx) > 1e-9:
        for x_edge in (xmin, xmax):
            t = (x_edge - x1) / dx
            if 0.0 <= t <= 1.0:
                y = y1 + t * dy
                if ymin - 1e-6 <= y <= ymax + 1e-6:
                    hits.append((t, (snap_world_mm(x_edge), snap_world_mm(y))))
    if abs(dy) > 1e-9:
        for y_edge in (ymin, ymax):
            t = (y_edge - y1) / dy
            if 0.0 <= t <= 1.0:
                x = x1 + t * dx
                if xmin - 1e-6 <= x <= xmax + 1e-6:
                    hits.append((t, (snap_world_mm(x), snap_world_mm(y_edge))))
    hits.sort(key=lambda item: item[0])
    unique = []
    for _, pt in hits:
        if not unique or math.hypot(pt[0] - unique[-1][0], pt[1] - unique[-1][1]) > 1:
            unique.append(pt)
    return unique


def segment_store_boundary_crossings(p1, p2):
    return segment_rect_crossings(p1, p2, 0, 0, store_width_mm, store_height_mm)


def point_in_store(x, y):
    return 0 <= x <= store_width_mm and 0 <= y <= store_height_mm


def is_on_store_boundary(pt, tol=None):
    tol = tol if tol is not None else OBSTACLE_SNAP_MM / 2 + 1
    x, y = pt
    if not point_in_store(x, y):
        return False
    return (
        x <= tol
        or x >= store_width_mm - tol
        or y <= tol
        or y >= store_height_mm - tol
    )


def is_store_interior(x, y):
    return point_in_store(x, y) and not is_on_store_boundary((x, y))


def _points_near(a, b, tol=None):
    tol = tol if tol is not None else OBSTACLE_SNAP_MM
    return math.hypot(a[0] - b[0], a[1] - b[1]) <= tol


def _segment_enters_interior(p1, p2, crossings=None):
    crossings = crossings if crossings is not None else segment_store_boundary_crossings(p1, p2)
    if is_store_interior(p2[0], p2[1]):
        return True
    if not crossings:
        return False
    if not point_in_store(p1[0], p1[1]) and not point_in_store(p2[0], p2[1]):
        mx = (p1[0] + p2[0]) / 2
        my = (p1[1] + p2[1]) / 2
        return is_store_interior(mx, my)
    return False


def apply_obstacle_shift(wx, wy, last):
    if last is None:
        return wx, wy
    keys = pygame.key.get_pressed()
    if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
        if abs(wx - last[0]) > abs(wy - last[1]):
            wy = last[1]
        else:
            wx = last[0]
    return wx, wy


def _obstacle_last_allows_free_turn(last):
    """After a boundary corner (or when already inside), next segment is unconstrained."""
    return point_in_store(last[0], last[1])


def obstacle_draw_target(last, wx, wy):
    """From outside, preview stops at boundary; after that, preview follows the cursor freely."""
    wx, wy = apply_obstacle_shift(wx, wy, last)
    target = snap_world_point(wx, wy)
    if last is None:
        return None if is_store_interior(target[0], target[1]) else target
    if _obstacle_last_allows_free_turn(last):
        return target
    crossings = segment_store_boundary_crossings(last, target)
    if crossings and _segment_enters_interior(last, target, crossings):
        return crossings[0]
    return target


def obstacle_vertices_for_click(last, wx, wy):
    """First crossing from outside becomes a corner; later points may go inside, outside, or along edges."""
    wx, wy = apply_obstacle_shift(wx, wy, last)
    target = snap_world_point(wx, wy)
    if last is None:
        if is_store_interior(target[0], target[1]):
            show_toast("请从门店外或边界开始勾勒")
            return []
        return [target]

    if _obstacle_last_allows_free_turn(last):
        if _points_near(target, last):
            return []
        return [target]

    crossings = segment_store_boundary_crossings(last, target)
    if is_store_interior(target[0], target[1]):
        if crossings:
            show_toast("已在边界落点，可向内、沿边或向外转折")
            return [crossings[0]]
        return []

    if crossings and _segment_enters_interior(last, target, crossings):
        entry = crossings[0]
        if _points_near(entry, last):
            return []
        show_toast("已在边界落点，可向内、沿边或向外转折")
        return [entry]

    if _points_near(target, last):
        return []
    return [target]


def append_obstacle_vertices(vertices):
    global current_polygon
    for vertex in vertices:
        if current_polygon and _points_near(vertex, current_polygon[-1]):
            continue
        current_polygon.append(vertex)


def polygon_area(points):
    if len(points) < 3:
        return 0.0
    area = 0.0
    for i, (x1, y1) in enumerate(points):
        x2, y2 = points[(i + 1) % len(points)]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def _clip_polygon_edge(points, inside, intersect):
    if not points:
        return []
    output = []
    s = points[-1]
    for e in points:
        s_in = inside(s)
        e_in = inside(e)
        if s_in and e_in:
            output.append(e)
        elif s_in and not e_in:
            output.append(intersect(s, e))
        elif not s_in and e_in:
            output.append(intersect(s, e))
            output.append(e)
        s = e
    return output


def clip_polygon_to_rect(points, xmin, ymin, xmax, ymax):
    if len(points) < 3:
        return []

    def intersect_vertical(s, e, x_val):
        x1, y1 = s
        x2, y2 = e
        if abs(x2 - x1) < 1e-9:
            return (x_val, y1)
        t = (x_val - x1) / (x2 - x1)
        return (x_val, y1 + t * (y2 - y1))

    def intersect_horizontal(s, e, y_val):
        x1, y1 = s
        x2, y2 = e
        if abs(y2 - y1) < 1e-9:
            return (x1, y_val)
        t = (y_val - y1) / (y2 - y1)
        return (x1 + t * (x2 - x1), y_val)

    result = list(points)
    result = _clip_polygon_edge(result, lambda p: p[0] >= xmin, lambda s, e: intersect_vertical(s, e, xmin))
    result = _clip_polygon_edge(result, lambda p: p[0] <= xmax, lambda s, e: intersect_vertical(s, e, xmax))
    result = _clip_polygon_edge(result, lambda p: p[1] >= ymin, lambda s, e: intersect_horizontal(s, e, ymin))
    result = _clip_polygon_edge(result, lambda p: p[1] <= ymax, lambda s, e: intersect_horizontal(s, e, ymax))
    return result


def clip_polygon_to_store(points):
    return clip_polygon_to_rect(points, 0, 0, store_width_mm, store_height_mm)


def clip_obstacle_points(points):
    clipped = clip_polygon_to_store(points)
    if len(clipped) >= 3 and polygon_area(clipped) > 1.0:
        return clipped
    return clipped


def polygon_fully_inside_store(points):
    for x, y in points:
        if x < 0 or y < 0 or x > store_width_mm or y > store_height_mm:
            return False
    return True


def try_translate_obstacle(points, dx, dy):
    """在店内时禁止拖出画布；若因缩小画布已越界，仍允许拖回店内。"""
    new_points = [(x + dx, y + dy) for x, y in points]
    if polygon_fully_inside_store(points) and not polygon_fully_inside_store(new_points):
        return points
    return new_points


def clamp_group_translation(originals, dx, dy):
    """Rigid group move: clamp one dx/dy so every member stays inside the store."""
    all_pts = [p for pts in originals.values() for p in pts]
    if not all_pts:
        return dx, dy
    if not all(0 <= p[0] <= store_width_mm and 0 <= p[1] <= store_height_mm for p in all_pts):
        return dx, dy
    min_x = min(p[0] for p in all_pts)
    max_x = max(p[0] for p in all_pts)
    min_y = min(p[1] for p in all_pts)
    max_y = max(p[1] for p in all_pts)
    dx = max(-min_x, min(dx, store_width_mm - max_x))
    dy = max(-min_y, min(dy, store_height_mm - max_y))
    return dx, dy


def rect_points_centered(cx, cy, length_mm, width_mm):
    hl, hw = length_mm / 2.0, width_mm / 2.0
    return [
        (cx - hl, cy - hw),
        (cx + hl, cy - hw),
        (cx + hl, cy + hw),
        (cx - hl, cy + hw),
    ]


def obstacle_rect_metrics(points, tol=OBSTACLE_SNAP_MM):
    """Axis-aligned rectangle obstacles return (cx, cy, length_mm, width_mm)."""
    if len(points) != 4:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max_x - min_x
    span_y = max_y - min_y
    if span_x < tol or span_y < tol:
        return None
    for x, y in points:
        on_corner = (
            (abs(x - min_x) <= tol or abs(x - max_x) <= tol)
            and (abs(y - min_y) <= tol or abs(y - max_y) <= tol)
        )
        if not on_corner:
            return None
    cx = (min_x + max_x) / 2
    cy = (min_y + max_y) / 2
    length_mm = max(span_x, span_y)
    width_mm = min(span_x, span_y)
    return cx, cy, length_mm, width_mm


def resize_obstacle_rect(index, length_m, width_m) -> bool:
    col = collision_polygons[index]
    metrics = obstacle_rect_metrics(col["points"])
    if not metrics:
        return False
    cx, cy, _, _ = metrics
    length_mm = length_m * 1000
    width_mm = width_m * 1000
    xs = [p[0] for p in col["points"]]
    ys = [p[1] for p in col["points"]]
    span_x = max(xs) - min(xs)
    span_y = max(ys) - min(ys)
    if span_x >= span_y:
        new_points = rect_points_centered(cx, cy, length_mm, width_mm)
    else:
        new_points = rect_points_centered(cx, cy, width_mm, length_mm)
    new_points = clip_obstacle_points(new_points)
    if len(new_points) < 3 or polygon_area(new_points) <= 1.0:
        return False
    if obstacle_is_zone(col):
        overlaps, other_name = zone_overlaps_any(new_points, index)
        if overlaps:
            show_toast(f"尺寸修改后会与障碍「{other_name}」重叠")
            return False
    col["points"] = [[int(round(x)), int(round(y))] for x, y in new_points]
    return True


def roi_to_color(roi):
    """兼容旧 ROI 0–10；新坪效请用 revenue_per_sqm_to_color。"""
    roi = max(0, min(10, roi))
    start, end = (173, 216, 230), (178, 34, 34)
    t = roi / 10
    return tuple(int(start[i] + t * (end[i] - start[i])) for i in range(3))


def current_store_slug() -> str | None:
    if current_layout_path:
        return catalog_slug_for_path(current_layout_path)
    return None


def furniture_area_mm2(furn) -> float:
    return polygon_area(furn.get_rotated_points())


def mark_heatmap_dirty() -> None:
    global _heatmap_metrics_dirty
    _heatmap_metrics_dirty = True
    _sidebar_metric_cache.clear()


def mark_heatmap_clean() -> None:
    global _heatmap_metrics_dirty
    _heatmap_metrics_dirty = False


def _resolve_pending_heatmap_week() -> None:
    global heatmap_week_index, _pending_heatmap_week
    if _pending_heatmap_week is None and heatmap_week_index >= 0:
        return
    weeks = heatmap_store_weeks()
    if _pending_heatmap_week and _pending_heatmap_week in weeks:
        heatmap_week_index = weeks.index(_pending_heatmap_week)
    elif weeks:
        heatmap_week_index = len(weeks) - 1
    else:
        heatmap_week_index = -1
    _pending_heatmap_week = None


def ensure_heatmap_metrics() -> None:
    global _heatmap_metrics_dirty
    if not placed_furnitures or not sales_data_ready():
        return
    if not _heatmap_metrics_dirty:
        return
    _resolve_pending_heatmap_week()
    recompute_heatmap_metrics()
    mark_heatmap_clean()


def template_sidebar_metrics(name: str, family: str, area: float) -> tuple[float, float]:
    key = (
        name,
        family,
        current_store_slug(),
        heatmap_week_mode,
        heatmap_week_count,
        tuple(active_heatmap_week_keys()),
    )
    cached = _sidebar_metric_cache.get(key)
    if cached is not None:
        return cached
    amt = lookup_sales_amount(name, family, **heatmap_lookup_kwargs())
    rps = revenue_per_sqm(amt, area, num_weeks=heatmap_week_divisor())
    _sidebar_metric_cache[key] = (amt, rps)
    return amt, rps


def heatmap_store_weeks() -> list[str]:
    return list_all_week_keys(current_store_slug())


def active_heatmap_week_keys() -> list[str]:
    slug = current_store_slug()
    if heatmap_week_mode == "range":
        return list_recent_week_keys(slug, heatmap_week_count)
    weeks = heatmap_store_weeks()
    if not weeks:
        return []
    idx = heatmap_week_index
    if idx < 0 or idx >= len(weeks):
        idx = len(weeks) - 1
    return [weeks[idx]]


def heatmap_period_title() -> str:
    keys = active_heatmap_week_keys()
    slug = current_store_slug()
    if heatmap_week_mode == "range":
        if not keys:
            return f"周均 · 近 {heatmap_week_count} 周（无数据）"
        if len(keys) == 1:
            return f"周均 · {week_period_display(slug, keys[0])}"
        return f"周均 · 近 {len(keys)} 周 · {keys[0]} … {keys[-1]}"
    if not keys:
        return "暂无周销量 — 请先 grab_sales"
    return week_period_display(slug, keys[0])


def heatmap_week_caption() -> str:
    keys = active_heatmap_week_keys()
    if heatmap_week_mode == "range":
        return f"周均 · 近 {heatmap_week_count} 周"
    if not keys:
        return "无周数据"
    key = keys[0]
    full = week_period_display(current_store_slug(), key)
    if len(full) > 28:
        return key + " " + full.split("(", 1)[-1].rstrip(")")
    return full


def sync_heatmap_week_ui(buttons=None) -> None:
    if not buttons:
        return
    is_range = heatmap_week_mode == "range"
    if "week_mode" in buttons:
        buttons["week_mode"].label = f"周均 {heatmap_week_count}周" if is_range else "单周查看"
        buttons["week_mode"].active = is_range
    if "week_prev" in buttons:
        buttons["week_prev"].enabled = not is_range and bool(heatmap_store_weeks())
    if "week_next" in buttons:
        buttons["week_next"].enabled = not is_range and bool(heatmap_store_weeks())
    if "range_less" in buttons:
        buttons["range_less"].enabled = is_range
    if "range_more" in buttons:
        buttons["range_more"].enabled = is_range


def navigate_heatmap_week(delta: int, buttons=None) -> None:
    global heatmap_week_mode, heatmap_week_index
    weeks = heatmap_store_weeks()
    if not weeks:
        show_toast("暂无周销量数据，请先运行 grab_sales.bat")
        return
    heatmap_week_mode = "single"
    if heatmap_week_index < 0:
        heatmap_week_index = len(weeks) - 1
    heatmap_week_index = max(0, min(len(weeks) - 1, heatmap_week_index + int(delta)))
    mark_heatmap_dirty()
    clear_heatmap_cache()
    recompute_heatmap_metrics()
    mark_heatmap_clean()
    sync_heatmap_week_ui(buttons)
    show_toast(heatmap_period_title())


def toggle_heatmap_week_mode(buttons=None) -> None:
    global heatmap_week_mode
    heatmap_week_mode = "range" if heatmap_week_mode == "single" else "single"
    mark_heatmap_dirty()
    clear_heatmap_cache()
    recompute_heatmap_metrics()
    mark_heatmap_clean()
    sync_heatmap_week_ui(buttons)
    show_toast(heatmap_period_title())


def change_heatmap_range_weeks(delta: int, buttons=None) -> None:
    global heatmap_week_mode, heatmap_week_count
    heatmap_week_mode = "range"
    heatmap_week_count = max(1, min(52, heatmap_week_count + int(delta)))
    mark_heatmap_dirty()
    clear_heatmap_cache()
    recompute_heatmap_metrics()
    mark_heatmap_clean()
    sync_heatmap_week_ui(buttons)
    show_toast(heatmap_period_title())


def heatmap_week_divisor() -> int:
    return max(1, len(active_heatmap_week_keys()))


def compute_furniture_revenue_per_sqm(furn, shop_slug: str | None = None) -> float:
    area = furniture_area_mm2(furn)
    amount = lookup_sales_amount(
        furn.name,
        furn.product_family,
        shop_id=shop_slug,
        num_weeks=heatmap_week_count,
        week_keys=active_heatmap_week_keys(),
    )
    return revenue_per_sqm(amount, area, num_weeks=heatmap_week_divisor())


def recompute_heatmap_metrics() -> None:
    global heatmap_vmin, heatmap_vmax, heatmap_color_step
    slug = current_store_slug()
    values: list[float] = []
    for furn in placed_furnitures:
        furn.revenue_per_sqm = compute_furniture_revenue_per_sqm(furn, slug)
        if furn.revenue_per_sqm > 0:
            values.append(furn.revenue_per_sqm)
    heatmap_vmin = min(values) if values else 0.0
    heatmap_vmax = max(values) if values else 1.0
    heatmap_color_step = adaptive_color_step(heatmap_vmin, heatmap_vmax)


def heatmap_lookup_kwargs() -> dict:
    return {
        "shop_id": current_store_slug(),
        "num_weeks": heatmap_week_count,
        "week_keys": active_heatmap_week_keys(),
    }


def heatmap_color_for_value(value: float) -> tuple[int, int, int]:
    return revenue_per_sqm_to_color(
        value, heatmap_vmin, heatmap_vmax, step=heatmap_color_step
    )


def heatmap_rgba_for_value(value: float, *, dim: bool = False) -> tuple[int, int, int, int]:
    r, g, b, a = revenue_per_sqm_to_rgba(
        value, heatmap_vmin, heatmap_vmax, step=heatmap_color_step
    )
    if dim:
        a = max(28, int(a * 0.22))
    return r, g, b, a


def _blit_polygon_tint(surface, screen_pts, rgba: tuple[int, int, int, int]) -> None:
    if len(screen_pts) < 3:
        return
    xs = [p[0] for p in screen_pts]
    ys = [p[1] for p in screen_pts]
    min_x, max_x = int(min(xs)), int(max(xs))
    min_y, max_y = int(min(ys)), int(max(ys))
    w = max(2, max_x - min_x + 1)
    h = max(2, max_y - min_y + 1)
    local_pts = [(p[0] - min_x, p[1] - min_y) for p in screen_pts]
    layer = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.polygon(layer, rgba, local_pts)
    surface.blit(layer, (min_x, min_y))


def _shade_color(color, factor=0.55):
    return tuple(max(0, min(255, int(c * factor))) for c in color[:3])


def _blend_colors(a, b, t=0.35):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def shape_to_points(item):
    shape_type = item.get("type", "")
    if shape_type == "polygon":
        return [tuple(p) for p in item.get("points", [])]
    if shape_type == "rectangle":
        w, h = item.get("width", 0), item.get("height", 0)
        ox, oy = item.get("offset_x", 0) or 0, item.get("offset_y", 0) or 0
        return [(ox, oy), (ox + w, oy), (ox + w, oy + h), (ox, oy + h)]
    if shape_type == "circle":
        cx = item.get("center_x", 0) or 0
        cy = item.get("center_y", 0) or 0
        legacy = item.get("radius", 0) or 0
        rx = item.get("radius_x", legacy) or legacy
        ry = item.get("radius_y", legacy if legacy else rx) or rx
        return [
            (cx + rx * math.cos(2 * math.pi * i / 24), cy + ry * math.sin(2 * math.pi * i / 24))
            for i in range(24)
        ]
    if shape_type == "l_shape":
        w, h = item.get("width", 0), item.get("height", 0)
        cw, ch = item.get("cut_width", 0), item.get("cut_height", 0)
        return [(0, 0), (w, 0), (w, ch), (cw, ch), (cw, h), (0, h)]
    return []


# ── 家具 ────────────────────────────────────────────────────
class Furniture:
    def __init__(self, name, roi, points, x=0, y=0, rotation=0, product_family=""):
        self.name = name
        self.roi = roi
        self.revenue_per_sqm = 0.0
        self.points = points
        self.product_family = product_family or ""
        self.x = x
        self.y = y
        self.rotation = rotation
        self.instance_id = ""
        self.attach_to = ""
        self.dragging = False
        self._label_cache_key = None
        self._name_label_surf = None
        self._roi_label_surf = None

    def _label_surfaces(self, selected: bool):
        key = (self.name, self.revenue_per_sqm, selected)
        if self._label_cache_key != key:
            self._label_cache_key = key
            self._name_label_surf = FONT_MARK.render(self.name, True, C_TEXT)
            metric = format_revenue_per_sqm(self.revenue_per_sqm)
            self._roi_label_surf = FONT_MARK.render(metric, True, C_MUTED)
        return self._name_label_surf, self._roi_label_surf

    def rotate_by(self, angle):
        self.rotation = (self.rotation + angle) % 360

    def get_rotated_points(self):
        cx = sum(p[0] for p in self.points) / len(self.points)
        cy = sum(p[1] for p in self.points) / len(self.points)
        rad = math.radians(self.rotation)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        rotated = []
        for px, py in self.points:
            rx, ry = px - cx, py - cy
            rotated.append((rx * cos_a - ry * sin_a + cx + self.x, rx * sin_a + ry * cos_a + cy + self.y))
        return rotated

    def draw(self, surface, selected=False):
        if not furniture_on_screen(self):
            self._label_rect = None
            return
        pts = [world_to_screen(x, y) for x, y in self.get_rotated_points()]
        border_rgb = heatmap_color_for_value(self.revenue_per_sqm)
        blink_active = _overlap_blink_active(self)
        dim_tint = show_roi_overlap_mode and not blink_active and not selected
        tint = heatmap_rgba_for_value(self.revenue_per_sqm, dim=dim_tint)

        pygame.draw.polygon(surface, (252, 253, 255), pts)
        _blit_polygon_tint(surface, pts, tint)
        border_w = 4 if selected else 3
        if selected:
            border_c = C_SELECTION
        elif self.revenue_per_sqm > 0:
            border_c = border_rgb
        else:
            border_c = C_BORDER
        pygame.draw.polygon(surface, border_c, pts, border_w)
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        span = max(max(xs) - min(xs), max(ys) - min(ys))
        min_y, max_y = min(ys), max(ys)
        img_cy = cy - span * 0.16

        if span >= 6:
            display_w = max(FURNITURE_IMAGE_MIN_PX, min(160, int(span * 0.78)))
            aspect = _furniture_aspect(self.name, self.product_family)
            display_h = max(FURNITURE_IMAGE_MIN_PX, int(display_w * aspect))
            img = furniture_display_image(
                self.name, display_w, display_h, family=self.product_family
            )
            if img is not None:
                img_rect = img.get_rect(center=(int(cx), int(img_cy)))
                if display_w >= 20:
                    shadow_rect = img_rect.inflate(6, 6)
                    pygame.draw.rect(surface, (255, 255, 255), shadow_rect, border_radius=4)
                    pygame.draw.rect(surface, (200, 210, 220), shadow_rect, 1, border_radius=4)
                surface.blit(img, img_rect)
            else:
                inner = [
                    (int(cx + (p[0] - cx) * 0.72), int(img_cy + (p[1] - cy) * 0.72))
                    for p in pts
                ]
                if len(inner) >= 3:
                    pygame.draw.polygon(surface, _shade_color(border_rgb, 0.75), inner)

        if span >= FURNITURE_LABEL_MIN_SPAN_PX or selected:
            metric = format_revenue_per_sqm(self.revenue_per_sqm)
            if dim_tint:
                metric = "…"
            tag_rect = draw_furniture_metric_tag(
                surface,
                self.name,
                metric,
                cx,
                max_y - 2,
                border_rgb,
                selected=selected,
            )
            self._label_rect = tag_rect.inflate(LABEL_HIT_PAD, LABEL_HIT_PAD)
        else:
            self._label_rect = pygame.Rect(int(cx) - 8, int(cy) - 8, 16, 16)

    def is_label_clicked(self, mx, my):
        rect = getattr(self, "_label_rect", None)
        return rect is not None and rect.collidepoint(mx, my)

    def is_clicked(self, mx, my):
        if self.is_label_clicked(mx, my):
            return True
        wx, wy = screen_to_world(mx, my)
        return point_in_poly(wx, wy, self.get_rotated_points())


def _segments_intersect(a1, a2, b1, b2):
    def ccw(a, b, c):
        return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])

    return ccw(a1, b1, b2) != ccw(a2, b1, b2) and ccw(a1, a2, b1) != ccw(a1, a2, b2)


def _polygon_edges(points):
    for i in range(len(points)):
        yield points[i], points[(i + 1) % len(points)]


def polygons_overlap(poly_a, poly_b):
    if len(poly_a) < 3 or len(poly_b) < 3:
        return False
    for px, py in poly_a:
        if point_in_poly(px, py, poly_b):
            return True
    for px, py in poly_b:
        if point_in_poly(px, py, poly_a):
            return True
    for a1, a2 in _polygon_edges(poly_a):
        for b1, b2 in _polygon_edges(poly_b):
            if _segments_intersect(a1, a2, b1, b2):
                return True
    return False


def _inset_polygon(points, inset_mm=OBSTACLE_TOUCH_TOLERANCE_MM):
    if len(points) < 3:
        return points
    cx = sum(p[0] for p in points) / len(points)
    cy = sum(p[1] for p in points) / len(points)
    inset_pts = []
    for x, y in points:
        dx, dy = cx - x, cy - y
        dist = math.hypot(dx, dy)
        if dist < 1:
            inset_pts.append((x, y))
            continue
        move = min(inset_mm, dist * 0.45)
        inset_pts.append((x + dx / dist * move, y + dy / dist * move))
    return inset_pts


def polygons_interior_overlap(poly_a, poly_b):
    """仅检测面积重叠，贴边相邻不算重叠。"""
    return polygons_overlap(_inset_polygon(poly_a), _inset_polygon(poly_b))


def _line_intersection(p1, p2, p3, p4):
    x1, y1, x2, y2 = p1[0], p1[1], p2[0], p2[1]
    x3, y3, x4, y4 = p3[0], p3[1], p4[0], p4[1]
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) < 1e-9:
        return p1
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
    return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))


def _clip_polygon_half_plane(subject, edge_a, edge_b):
    if not subject:
        return []
    output = []
    for i in range(len(subject)):
        curr = subject[i]
        prev = subject[i - 1]
        curr_in = _edge_inside(curr, edge_a, edge_b)
        prev_in = _edge_inside(prev, edge_a, edge_b)
        if curr_in:
            if not prev_in:
                output.append(_line_intersection(prev, curr, edge_a, edge_b))
            output.append(curr)
        elif prev_in:
            output.append(_line_intersection(prev, curr, edge_a, edge_b))
    return output


def _edge_inside(point, edge_a, edge_b):
    return (
        (edge_b[0] - edge_a[0]) * (point[1] - edge_a[1])
        - (edge_b[1] - edge_a[1]) * (point[0] - edge_a[0])
    ) >= -1e-6


def convex_polygon_intersection(poly_a, poly_b):
    if len(poly_a) < 3 or len(poly_b) < 3:
        return []
    output = list(poly_a)
    for i in range(len(poly_b)):
        edge_a = poly_b[i]
        edge_b = poly_b[(i + 1) % len(poly_b)]
        output = _clip_polygon_half_plane(output, edge_a, edge_b)
        if not output:
            return []
    return output


def _darken_color(color, factor=0.55):
    return tuple(max(0, min(255, int(c * factor))) for c in color[:3])


def _overlap_groups() -> list[list["Furniture"]]:
    """空间重叠或父子绑定的家具分为一组（如床架+床垫）。"""
    n = len(placed_furnitures)
    if n < 2:
        return []
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    id_to_idx = {
        f.instance_id: i for i, f in enumerate(placed_furnitures) if getattr(f, "instance_id", "")
    }
    for i in range(n):
        for j in range(i + 1, n):
            a, b = placed_furnitures[i], placed_furnitures[j]
            if polygons_overlap(a.get_rotated_points(), b.get_rotated_points()):
                union(i, j)
    for i, furn in enumerate(placed_furnitures):
        parent_id = getattr(furn, "attach_to", "") or ""
        if parent_id and parent_id in id_to_idx:
            union(i, id_to_idx[parent_id])
    buckets: dict[int, list[Furniture]] = {}
    for i in range(n):
        buckets.setdefault(find(i), []).append(placed_furnitures[i])
    return [g for g in buckets.values() if len(g) >= 2]


def _overlap_blink_active(furn: "Furniture") -> bool:
    if not show_roi_overlap_mode:
        return True
    tick = pygame.time.get_ticks()
    for group in _overlap_groups():
        if furn not in group:
            continue
        phase = (tick // ROI_OVERLAP_BLINK_MS) % len(group)
        return group[phase] is furn
    return True


def draw_crosshatch_polygon(surface, screen_pts, color_a, color_b, spacing=7):
    if len(screen_pts) < 3:
        return
    xs = [p[0] for p in screen_pts]
    ys = [p[1] for p in screen_pts]
    min_x, max_x = int(min(xs)), int(max(xs))
    min_y, max_y = int(min(ys)), int(max(ys))
    w = max_x - min_x + 1
    h = max_y - min_y + 1
    if w < 3 or h < 3:
        return
    local_pts = [(p[0] - min_x, p[1] - min_y) for p in screen_pts]
    mask = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.polygon(mask, (255, 255, 255, 150), local_pts)
    ca = (*color_a[:3], 130)
    cb = (*color_b[:3], 130)
    for i in range(-h, w + h, spacing):
        pygame.draw.line(mask, ca, (i, 0), (i + h, h), 1)
    for i in range(-h, w + h, spacing):
        pygame.draw.line(mask, cb, (i, h), (i + h, 0), 1)
    surface.blit(mask, (min_x, min_y))


def furniture_draw_order() -> list:
    """重叠闪烁模式下，当前高亮件最后绘制以置于顶层。"""
    if not show_roi_overlap_mode:
        return placed_furnitures
    active: set = set()
    for group in _overlap_groups():
        for furn in group:
            if _overlap_blink_active(furn):
                active.add(furn)
    if not active:
        return placed_furnitures
    back = [f for f in placed_furnitures if f not in active]
    front = [f for f in placed_furnitures if f in active]
    return back + front


def draw_furniture_roi_overlaps(surface):
    """重叠区只画闪烁描边与名称，不遮挡产品图。"""
    if not show_roi_overlap_mode or len(placed_furnitures) < 2:
        return
    tick = pygame.time.get_ticks()
    pulse = 0.55 + 0.45 * abs(math.sin(tick / 280.0))
    for group in _overlap_groups():
        phase = (tick // ROI_OVERLAP_BLINK_MS) % len(group)
        active = group[phase]
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                if not furniture_on_screen(a) and not furniture_on_screen(b):
                    continue
                pts_a = a.get_rotated_points()
                pts_b = b.get_rotated_points()
                if not polygons_overlap(pts_a, pts_b):
                    continue
                overlap = convex_polygon_intersection(pts_a, pts_b)
                if len(overlap) < 3:
                    continue
                screen_pts = [world_to_screen(x, y) for x, y in overlap]
                color = heatmap_color_for_value(active.revenue_per_sqm)
                width = max(2, int(2 + pulse * 3))
                if len(screen_pts) >= 3:
                    pygame.draw.polygon(surface, color, screen_pts, width)
                cx = sum(p[0] for p in screen_pts) / len(screen_pts)
                cy = sum(p[1] for p in screen_pts) / len(screen_pts)
                if max(max(p[0] for p in screen_pts) - min(p[0] for p in screen_pts), 28) >= 28:
                    draw_label_pill(
                        surface,
                        active.name,
                        (cx, cy),
                        font=FONT_TINY,
                        fg=C_TEXT,
                        bg=(255, 255, 255, 235),
                    )


def obstacle_is_wall(col) -> bool:
    return col.get("kind") == "wall" or str(col.get("name", "")).startswith("墙体")


def obstacle_is_zone(col) -> bool:
    return not obstacle_is_wall(col)


def zone_overlaps_any(points, *ignore_indices):
    """粉色障碍区域之间不可重叠；与墙体允许贴边/重叠。"""
    ignore = set(ignore_indices)
    for i, col in enumerate(collision_polygons):
        if i in ignore or not obstacle_is_zone(col):
            continue
        if polygons_interior_overlap(points, col["points"]):
            return True, col.get("name", "")
    return False, ""


def obstacle_overlaps_any(points, *ignore_indices):
    ignore = set(ignore_indices)
    for i, col in enumerate(collision_polygons):
        if i in ignore:
            continue
        if polygons_interior_overlap(points, col["points"]):
            return True, col.get("name", "")
    return False, ""


def _snap_vertex(p):
    return snap_world_point(p[0], p[1])


def _undirected_edge_key(p1, p2):
    a = _snap_vertex(p1)
    b = _snap_vertex(p2)
    return (a, b) if a <= b else (b, a)


def _segment_overlap_length(p1, p2, q1, q2, tol=OBSTACLE_SNAP_MM):
    vx, vy = p2[0] - p1[0], p2[1] - p1[1]
    len_v = math.hypot(vx, vy)
    if len_v < 1:
        return 0.0

    def perp_dist(px, py):
        return abs((px - p1[0]) * vy - (py - p1[1]) * vx) / len_v

    for px, py in (q1, q2):
        if perp_dist(px, py) > tol:
            return 0.0

    def proj_t(px, py):
        return ((px - p1[0]) * vx + (py - p1[1]) * vy) / (len_v * len_v)

    t_lo, t_hi = sorted([proj_t(q1[0], q1[1]), proj_t(q2[0], q2[1])])
    overlap = min(1.0, t_hi) - max(0.0, t_lo)
    if overlap <= 0:
        return 0.0
    return overlap * len_v


def shared_edge_length(poly_a, poly_b):
    total = 0.0
    for a1, a2 in _polygon_edges(poly_a):
        for b1, b2 in _polygon_edges(poly_b):
            total += _segment_overlap_length(a1, a2, b1, b2)
    return total


def _segment_param(p, a, b):
    ax, ay = a
    bx, by = b
    px, py = p
    den = (bx - ax) ** 2 + (by - ay) ** 2
    if den < 1:
        return 0.0
    return ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / den


def _point_on_segment(p, a, b, tol=OBSTACLE_SNAP_MM):
    if math.hypot(b[0] - a[0], b[1] - a[1]) < 1:
        return False
    if abs((p[0] - a[0]) * (b[1] - a[1]) - (p[1] - a[1]) * (b[0] - a[0])) > tol * math.hypot(b[0] - a[0], b[1] - a[1]):
        return False
    t = _segment_param(p, a, b)
    return -0.01 <= t <= 1.01


def _segment_intersection_point(a1, a2, b1, b2, tol=5):
    x1, y1 = a1
    x2, y2 = a2
    x3, y3 = b1
    x4, y4 = b2
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) < 1:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
    u = ((x1 - x3) * (y1 - y2) - (y1 - y3) * (x1 - x2)) / den
    if -0.001 <= t <= 1.001 and -0.001 <= u <= 1.001:
        pt = (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
        return _snap_vertex(pt)
    return None


def subdivide_polygon_at_poly(points, other, tol=OBSTACLE_SNAP_MM):
    """在 T 形/贴边处插入顶点，使共边能被正确抵消。"""
    snaps = [_snap_vertex(p) for p in points]
    other_pts = [_snap_vertex(p) for p in other]
    out: list[tuple[float, float]] = []
    n = len(snaps)
    for i in range(n):
        a = snaps[i]
        b = snaps[(i + 1) % n]
        splits = [a]
        for p in other_pts:
            if p == a or p == b:
                continue
            if _point_on_segment(p, a, b, tol):
                splits.append(p)
        for oa, ob in _polygon_edges(other_pts):
            hit = _segment_intersection_point(a, b, oa, ob, tol=10)
            if hit and hit != a and hit != b:
                splits.append(hit)
        splits.append(b)
        splits.sort(key=lambda p: _segment_param(p, a, b))
        deduped = [splits[0]]
        for p in splits[1:]:
            if math.hypot(p[0] - deduped[-1][0], p[1] - deduped[-1][1]) > tol / 2:
                deduped.append(p)
        for p in deduped[:-1]:
            if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > tol / 2:
                out.append(p)
    return out if len(out) >= 3 else snaps


def _trace_polygon_loop(adj, start, start_nbr, used_edges):
    path = [start]
    prev = start
    cur = start_nbr
    used_edges.add(_undirected_edge_key(start, start_nbr))
    for _ in range(len(adj) * 4 + 8):
        path.append(cur)
        if cur == start and len(path) > 3:
            path.pop()
            break
        nxt = None
        for n in adj.get(cur, []):
            if n == prev:
                continue
            ek = _undirected_edge_key(cur, n)
            if ek in used_edges:
                continue
            nxt = n
            used_edges.add(ek)
            break
        if nxt is None:
            break
        prev, cur = cur, nxt
    return path if len(path) >= 3 else []


def _trace_largest_loop(outer):
    adj = {}
    for p1, p2 in outer:
        adj.setdefault(p1, []).append(p2)
        adj.setdefault(p2, []).append(p1)
    used_edges: set = set()
    best: list[tuple[float, float]] = []
    best_area = 0.0
    for p1, p2 in outer:
        ek = _undirected_edge_key(p1, p2)
        if ek in used_edges:
            continue
        loop = _trace_polygon_loop(adj, p1, p2, used_edges)
        if len(loop) >= 3:
            area = polygon_area(loop)
            if area > best_area:
                best_area = area
                best = loop
    return best if best_area > 1.0 else None


def union_polygons(poly_a, poly_b):
    """共边抵消后取外轮廓；先细分贴边顶点以支持 T 形/L 形融合。"""
    pa = subdivide_polygon_at_poly(poly_a, poly_b)
    pb = subdivide_polygon_at_poly(poly_b, poly_a)
    edges = []
    for poly in (pa, pb):
        n = len(poly)
        for i in range(n):
            p1 = poly[i]
            p2 = poly[(i + 1) % n]
            if p1 == p2:
                continue
            edges.append((p1, p2))
    counts = {}
    directed = {}
    for p1, p2 in edges:
        key = _undirected_edge_key(p1, p2)
        counts[key] = counts.get(key, 0) + 1
        directed[key] = (p1, p2)
    outer = [directed[k] for k, c in counts.items() if c == 1]
    if not outer:
        return None
    path = _trace_largest_loop(outer)
    if not path or len(path) < 3 or polygon_area(path) <= 1.0:
        return None
    return path


def _merge_area_ok(poly_a, poly_b, merged):
    area_a = polygon_area(poly_a)
    area_b = polygon_area(poly_b)
    area_m = polygon_area(merged)
    if polygons_interior_overlap(poly_a, poly_b):
        return area_m >= max(area_a, area_b) * 0.85
    expected = area_a + area_b
    return area_m >= expected * 0.90


def align_polygon_for_merge(poly_a, poly_b):
    """磁吸对齐：平移 B 使共边最长。"""
    best_b = poly_b
    best_shared = shared_edge_length(poly_a, poly_b)
    for ox, oy in poly_b:
        for px, py in poly_a:
            dx, dy = px - ox, py - oy
            if math.hypot(dx, dy) > OBSTACLE_MAGNET_MM:
                continue
            shifted = [(x + dx, y + dy) for x, y in poly_b]
            shared = shared_edge_length(poly_a, shifted)
            if shared > best_shared:
                best_shared = shared
                best_b = shifted
    return best_b, best_shared


def _alignment_ref_coords(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    refs_x = xs + [min(xs), max(xs), (min(xs) + max(xs)) / 2]
    refs_y = ys + [min(ys), max(ys), (min(ys) + max(ys)) / 2]
    return refs_x, refs_y


def _collect_alignment_targets(ignore_indices):
    ignore = set(ignore_indices)
    target_x, target_y = [], []
    for j, col in enumerate(collision_polygons):
        if j in ignore:
            continue
        for x, y in col["points"]:
            target_x.append(x)
            target_y.append(y)
        if obstacle_rect_metrics(col["points"]):
            xs = [p[0] for p in col["points"]]
            ys = [p[1] for p in col["points"]]
            target_x.extend([min(xs), max(xs)])
            target_y.extend([min(ys), max(ys)])
    return target_x, target_y


def _best_1d_snap(refs, targets, tol=ALIGN_GUIDE_SNAP_MM):
    best_delta = 0.0
    best_coord = None
    best_gap = tol
    for ref in refs:
        for target in targets:
            gap = abs(ref - target)
            if gap < best_gap:
                best_gap = gap
                best_delta = target - ref
                best_coord = target
    if best_coord is None:
        return 0.0, None
    return best_delta, best_coord


def compute_alignment_snap(points, ignore_indices):
    refs_x, refs_y = _alignment_ref_coords(points)
    target_x, target_y = _collect_alignment_targets(ignore_indices)
    dx, guide_x = _best_1d_snap(refs_x, target_x)
    dy, guide_y = _best_1d_snap(refs_y, target_y)
    guides = []
    if guide_x is not None and abs(dx) > 1e-9:
        guides.append({"axis": "v", "coord": guide_x})
    if guide_y is not None and abs(dy) > 1e-9:
        guides.append({"axis": "h", "coord": guide_y})
    return dx, dy, guides


def draw_alignment_guides(surface):
    if not active_alignment_guides:
        return
    dash, gap = 8, 6
    color = (37, 99, 235, 200)
    top = CANVAS_RECT.top
    bottom = SCREEN_HEIGHT
    left = SIDEBAR_WIDTH
    right = SCREEN_WIDTH
    for guide in active_alignment_guides:
        if guide["axis"] == "v":
            sx, _ = world_to_screen(guide["coord"], 0)
            sx = int(sx)
            y = top
            while y < bottom:
                y2 = min(y + dash, bottom)
                pygame.draw.line(surface, color, (sx, y), (sx, y2), 2)
                y += dash + gap
        else:
            _, sy = world_to_screen(0, guide["coord"])
            sy = int(sy)
            x = left
            while x < right:
                x2 = min(x + dash, right)
                pygame.draw.line(surface, color, (x, sy), (x2, sy), 2)
                x += dash + gap


def merge_two_wall_rects(poly_a, poly_b):
    """共线贴边或重叠的两面墙合并为一个长方形墙段。"""
    ma, mb = obstacle_rect_metrics(poly_a), obstacle_rect_metrics(poly_b)
    if not ma or not mb:
        return None
    axs = [p[0] for p in poly_a]
    ays = [p[1] for p in poly_a]
    bxs = [p[0] for p in poly_b]
    bys = [p[1] for p in poly_b]
    span_ax = max(axs) - min(axs)
    span_ay = max(ays) - min(ays)
    span_bx = max(bxs) - min(bxs)
    span_by = max(bys) - min(bys)
    horizontal = span_ax >= span_ay and span_bx >= span_by
    vertical = span_ax < span_ay and span_bx < span_by
    if not horizontal and not vertical:
        return None
    if horizontal:
        cy_a = (min(ays) + max(ays)) / 2
        cy_b = (min(bys) + max(bys)) / 2
        if abs(cy_a - cy_b) > OBSTACLE_MAGNET_MM * 2:
            return None
        min_x = min(min(axs), min(bxs))
        max_x = max(max(axs), max(bxs))
        thickness = max(span_ay, span_by)
        cy = (cy_a + cy_b) / 2
        return rect_points_centered((min_x + max_x) / 2, cy, max_x - min_x, thickness)
    cx_a = (min(axs) + max(axs)) / 2
    cx_b = (min(bxs) + max(bxs)) / 2
    if abs(cx_a - cx_b) > OBSTACLE_MAGNET_MM * 2:
        return None
    min_y = min(min(ays), min(bys))
    max_y = max(max(ays), max(bys))
    thickness = max(span_ax, span_bx)
    cx = (cx_a + cx_b) / 2
    return rect_points_centered(cx, (min_y + max_y) / 2, thickness, max_y - min_y)


def magnet_snap_translate(points, ignore_idx):
    """拖动时顶点磁吸到其它障碍的顶点，便于贴边融合。"""
    ignore_set = {ignore_idx} if isinstance(ignore_idx, int) else set(ignore_idx)
    best_dx = best_dy = 0.0
    best_gap = OBSTACLE_MAGNET_MM
    for j, col in enumerate(collision_polygons):
        if j in ignore_set:
            continue
        for px, py in points:
            for ox, oy in col["points"]:
                dx, dy = ox - px, oy - py
                gap = math.hypot(dx, dy)
                if 1 < gap < best_gap:
                    best_gap = gap
                    best_dx, best_dy = dx, dy
    if best_gap < OBSTACLE_MAGNET_MM:
        return [(x + best_dx, y + best_dy) for x, y in points]
    return points


def try_move_obstacle(points, dx, dy, ignore_idx):
    """平移 + 店内约束 + 磁吸；允许与其它障碍暂时重叠。"""
    moved = try_translate_obstacle(points, dx, dy)
    moved = magnet_snap_translate(moved, ignore_idx)
    return moved


def rotate_polygon_points(points, angle_deg, origin=None):
    if not points:
        return []
    if origin is None:
        cx = sum(p[0] for p in points) / len(points)
        cy = sum(p[1] for p in points) / len(points)
        origin = (cx, cy)
    ox, oy = origin
    rad = math.radians(angle_deg)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    rotated = []
    for x, y in points:
        rx, ry = x - ox, y - oy
        rotated.append((rx * cos_a - ry * sin_a + ox, rx * sin_a + ry * cos_a + oy))
    return rotated


def try_rotate_obstacle(points, angle_deg, ignore_idx):
    rotated = rotate_polygon_points(points, angle_deg)
    if polygon_fully_inside_store(points) and not polygon_fully_inside_store(rotated):
        return points, False
    return rotated, True


def rotation_step_degrees():
    return ROTATE_COARSE_DEG if rotation_mode == "90" else ROTATE_FINE_DEG


def rotation_mode_label():
    return "90°翻转" if rotation_mode == "90" else f"微调{ROTATE_FINE_DEG}°"


def toggle_rotation_mode():
    global rotation_mode
    rotation_mode = "90" if rotation_mode == "fine" else "fine"
    show_toast(f"旋转模式: {rotation_mode_label()}")


def find_merge_partner(idx):
    poly = collision_polygons[idx]["points"]
    best_j = -1
    best_len = 0.0
    for j, col in enumerate(collision_polygons):
        if j == idx:
            continue
        other = col["points"]
        shared = 0.0
        if obstacle_is_wall(collision_polygons[idx]) and obstacle_is_wall(col):
            if merge_two_wall_rects(poly, other):
                shared = max(shared_edge_length(poly, other), OBSTACLE_SNAP_MM)
        if shared <= 0:
            if polygons_interior_overlap(poly, other):
                continue
            _, shared = align_polygon_for_merge(poly, other)
        if shared > best_len:
            best_len = shared
            best_j = j
    if best_j >= 0 and best_len >= OBSTACLE_SNAP_MM:
        return best_j, best_len
    return -1, 0.0


def merge_pair_obstacles(idx, partner) -> bool:
    poly = collision_polygons[idx]["points"]
    other_raw = collision_polygons[partner]["points"]
    base = collision_polygons[idx]
    partner_col = collision_polygons[partner]
    is_wall = obstacle_is_wall(base)
    partner_wall = obstacle_is_wall(partner_col)
    if is_wall and partner_wall:
        merged_rect = merge_two_wall_rects(poly, other_raw)
        if merged_rect:
            push_undo()
            new_name = base["name"]
            if str(new_name).endswith("_copy") or str(partner_col["name"]).endswith("_copy"):
                new_name = re.sub(r"_copy\d*$", "", str(base["name"]))
            user_named = bool(base.get("user_named") or partner_col.get("user_named"))
            for remove_idx in sorted((idx, partner), reverse=True):
                collision_polygons.pop(remove_idx)
            entry = {
                "name": new_name,
                "points": [[int(round(x)), int(round(y))] for x, y in merged_rect],
                "kind": "wall",
            }
            if user_named:
                entry["user_named"] = True
            collision_polygons.append(entry)
            set_obstacle_selection([len(collision_polygons) - 1])
            show_toast(f"已合并墙段为「{new_name}」")
            return True
    other, shared = align_polygon_for_merge(poly, other_raw)
    merged = union_polygons(poly, other)
    if not merged:
        return False
    if not _merge_area_ok(poly, other, merged):
        return False
    overlaps, other_name = obstacle_overlaps_any(merged, idx, partner)
    if overlaps:
        show_toast(f"融合后会与「{other_name}」重叠，已取消")
        return False
    push_undo()
    new_name = base["name"]
    if partner_wall and not is_wall:
        new_name = partner_col["name"]
    for remove_idx in sorted((idx, partner), reverse=True):
        collision_polygons.pop(remove_idx)
    entry = {"name": new_name, "points": merged}
    if is_wall or partner_wall:
        entry["kind"] = "wall"
    if base.get("user_named") or partner_col.get("user_named"):
        entry["user_named"] = True
    collision_polygons.append(entry)
    set_obstacle_selection([len(collision_polygons) - 1])
    show_toast(f"已融合为 {new_name}（共边 {shared / 1000:.1f}m · {len(merged)} 顶点）")
    return True


def merge_selected_obstacle():
    if len(selected_collisions) == 2:
        a, b = selected_collisions[0], selected_collisions[1]
        if merge_pair_obstacles(a, b):
            return
        show_toast("两面选中项无法融合，请先贴边对齐")
        return
    if len(selected_collisions) != 1:
        show_toast("请选中 1 个或 2 个相邻障碍/墙体再点「融合相邻」")
        return
    idx = selected_collision
    partner, shared = find_merge_partner(idx)
    if partner < 0:
        show_toast("未找到可融合的相邻项（拖动时看蓝色对齐线，贴紧后重试）")
        return
    merge_pair_obstacles(idx, partner)


def obstacle_label_rect(col):
    pts = col["points"]
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    sx, sy = world_to_screen(cx, cy)
    label = FONT_BODY.render(col["name"], True, (0, 0, 0))
    rect = label.get_rect(center=(sx, sy))
    return rect.inflate(LABEL_HIT_PAD * 2, LABEL_HIT_PAD * 2)


def _load_display_items_cache():
    global _display_items_cache
    if _display_items_cache is not None:
        return _display_items_cache
    try:
        from display_lookup import load_display_items

        _display_items_cache = load_display_items()
    except Exception:
        _display_items_cache = []
    return _display_items_cache


def image_url_for_product(name: str) -> str:
    from display_lookup import _normalize_key

    key = _normalize_key(name)
    for item in _load_display_items_cache():
        if _normalize_key(item.product_code) == key or _normalize_key(item.product_name) == key:
            return getattr(item, "image_url", "") or ""
    return ""


def image_url_for_template(tpl) -> str:
    url = image_url_for_product(tpl.name)
    if not url and getattr(tpl, "product_family", ""):
        url = image_url_for_product(tpl.product_family)
    return url


def clear_furniture_display_cache():
    global _furniture_display_cache, _furniture_aspect_cache
    _furniture_display_cache = {}
    _furniture_aspect_cache = {}


def _furniture_aspect(name: str, family: str = "") -> float:
    fam = family or ""
    key = (name, fam)
    if key in _furniture_aspect_cache:
        return _furniture_aspect_cache[key]
    base = furniture_image_surface(name, max_px=FURNITURE_IMG_SOURCE_PX, family=fam)
    if base is None:
        return 0.75
    aspect = base.get_height() / max(base.get_width(), 1)
    _furniture_aspect_cache[key] = aspect
    return aspect


def _bucket_display_px(px: int) -> int:
    return max(
        FURNITURE_IMAGE_MIN_PX,
        int(round(px / FURNITURE_DISPLAY_BUCKET_PX)) * FURNITURE_DISPLAY_BUCKET_PX,
    )


def furniture_display_image(name: str, display_w: int, display_h: int, *, family: str = ""):
    """Return a cached, bucket-sized thumbnail; avoids per-frame smoothscale during zoom."""
    bw = _bucket_display_px(display_w)
    bh = max(FURNITURE_IMAGE_MIN_PX, int(bw * display_h / max(display_w, 1)))
    bh = _bucket_display_px(bh)
    fam = family or ""
    key = (name, fam, bw, bh)
    cached = _furniture_display_cache.get(key)
    if cached is not None:
        return cached
    base = furniture_image_surface(name, max_px=FURNITURE_IMG_SOURCE_PX, family=fam)
    if base is None:
        return None
    if base.get_width() == bw and base.get_height() == bh:
        scaled = base
    elif max(bw, bh) <= 28:
        scaled = pygame.transform.scale(base, (bw, bh))
    else:
        scaled = pygame.transform.smoothscale(base, (bw, bh))
    if len(_furniture_display_cache) >= FURNITURE_DISPLAY_CACHE_MAX:
        clear_furniture_display_cache()
    _furniture_display_cache[key] = scaled
    return scaled


def furniture_screen_bbox(furn) -> tuple[float, float, float, float]:
    pts = [world_to_screen(x, y) for x, y in furn.get_rotated_points()]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def furniture_on_screen(furn, margin: int = 48) -> bool:
    x1, y1, x2, y2 = furniture_screen_bbox(furn)
    return not (
        x2 < SIDEBAR_WIDTH - margin
        or x1 > SCREEN_WIDTH + margin
        or y2 < -margin
        or y1 > SCREEN_HEIGHT + margin
    )


def furniture_image_surface(name: str, max_px: int = 96, *, family: str = ""):
    url = image_url_for_product(name)
    if not url and family:
        url = image_url_for_product(family)
    if not url:
        return None
    try:
        from product_images import request_image

        return request_image(url, max_size=(max_px, max_px))
    except Exception:
        return None


def prefetch_template_list_images(items):
    urls = []
    for _, tpl in items:
        url = image_url_for_template(tpl)
        if url:
            urls.append(url)
    if urls:
        try:
            from product_images import prefetch_urls

            prefetch_urls(urls, limit=12)
        except Exception:
            pass


def prefetch_furniture_images():
    global _last_furniture_prefetch_ms
    now = pygame.time.get_ticks()
    if now - _last_furniture_prefetch_ms < FURNITURE_PREFETCH_INTERVAL_MS:
        return
    _last_furniture_prefetch_ms = now
    urls = []
    for furn in placed_furnitures:
        url = image_url_for_product(furn.name)
        if not url and furn.product_family:
            url = image_url_for_product(furn.product_family)
        if url:
            urls.append(url)
    if urls:
        try:
            from product_images import prefetch_urls

            prefetch_urls(urls, limit=16)
        except Exception:
            pass


def check_collision(furniture, obstacles):
    """家具与粉色障碍区不可重叠；墙体允许贴边摆放（墙有厚度，若参与碰撞会「弹开」）。"""
    furn_pts = furniture.get_rotated_points()
    if not polygon_fully_inside_store(furn_pts):
        return True
    for col in obstacles:
        if obstacle_is_wall(col):
            continue
        if polygons_interior_overlap(furn_pts, col["points"]):
            return True
    return False


def load_furniture_templates(json_path):
    if not os.path.isfile(json_path):
        raise FileNotFoundError(f"找不到 {json_path}，请确认在项目目录下运行")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    templates = []
    for item in data:
        points = shape_to_points(item)
        if points:
            family = item.get("product_family") or item.get("id", "")
            if not item.get("product_family"):
                try:
                    from sales_lookup import resolve_product_family

                    family = resolve_product_family(family) or family
                except Exception:
                    pass
            if "roi" in item:
                roi = float(item.get("roi") or 0)
            else:
                roi = lookup_roi(family)
            templates.append(Furniture(item.get("id", "unnamed"), roi, points, product_family=family))
    if not templates:
        raise ValueError(f"{json_path} 中没有有效的家具模板")
    return templates


furniture_templates = []


# ── 数据持久化 ──────────────────────────────────────────────
def ensure_layouts_dir():
    os.makedirs(LAYOUTS_DIR, exist_ok=True)
    os.makedirs(LAYOUT_TEMPLATES_DIR, exist_ok=True)


def slugify_name(name):
    safe = re.sub(r'[<>:"/\\|?*]', "", (name or "").strip())
    safe = re.sub(r"\s+", "_", safe)[:48]
    return safe or "store"


def unique_layout_path(display_name):
    ensure_layouts_dir()
    base = slugify_name(display_name)
    path = os.path.join(LAYOUTS_DIR, f"{base}.json")
    if not os.path.exists(path):
        return path
    n = 2
    while os.path.exists(os.path.join(LAYOUTS_DIR, f"{base}_{n}.json")):
        n += 1
    return os.path.join(LAYOUTS_DIR, f"{base}_{n}.json")


def layout_path_for_slug(slug):
    return os.path.join(LAYOUTS_DIR, f"{slug}.json")


def template_path_for_slug(slug):
    return os.path.join(LAYOUT_TEMPLATES_DIR, f"{slug}.json")


def catalog_name_for_slug(slug):
    for name, catalog_slug in STORE_CATALOG:
        if catalog_slug == slug:
            return name
    return slug


def catalog_slug_for_path(path):
    if not path:
        return None
    for _, slug in STORE_CATALOG:
        if os.path.abspath(path) == os.path.abspath(layout_path_for_slug(slug)):
            return slug
    return None


def remember_last_store(path):
    if not path:
        return
    try:
        payload = {"path": path, "slug": catalog_slug_for_path(path)}
        with open(LAST_STORE_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
    except OSError:
        pass


def load_last_store_path():
    if not os.path.isfile(LAST_STORE_FILE):
        return None
    try:
        with open(LAST_STORE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        path = data.get("path")
        if path and os.path.isfile(path):
            return path
        slug = data.get("slug")
        if slug:
            slug_path = layout_path_for_slug(slug)
            if os.path.isfile(slug_path):
                return slug_path
        return None
    except (OSError, json.JSONDecodeError):
        return None


def store_info_map():
    return {s["path"]: s for s in list_store_layouts()}


def read_store_summary(path):
    """Read one layout file summary, with mtime cache for fast store home."""
    if not path:
        return None
    try:
        if not os.path.isfile(path):
            return None
        mtime = os.path.getmtime(path)
        cached = _store_summary_cache.get(path)
        if cached and cached.get("_mtime") == mtime:
            return cached
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        store = data.get("store", {})
        info = {
            "_mtime": mtime,
            "path": path,
            "name": data.get("name") or os.path.splitext(os.path.basename(path))[0],
            "width": int(store.get("width_mm", 0)) / 1000,
            "height": int(store.get("height_mm", 0)) / 1000,
            "furniture_count": len(data.get("furnitures", [])),
            "obstacle_count": len(data.get("obstacles", [])),
        }
        _store_summary_cache[path] = info
        return info
    except Exception:
        return None


def invalidate_store_summary(path=None):
    if path:
        _store_summary_cache.pop(path, None)
    else:
        _store_summary_cache.clear()


def remember_store_summary(path, *, width_m, height_m, furniture_count=0, obstacle_count=0):
    if not path:
        return
    _store_summary_cache[path] = {
        "_mtime": time.time(),
        "path": path,
        "width": width_m,
        "height": height_m,
        "furniture_count": furniture_count,
        "obstacle_count": obstacle_count,
    }


def catalog_detail_from_cache(path):
    """Build store button detail from in-memory cache only (no disk access)."""
    info = _store_summary_cache.get(path)
    if not info:
        return "点击打开"
    detail = f"{info['width']:g}×{info['height']:g}m"
    if info["furniture_count"] or info["obstacle_count"]:
        detail += f" · 家具{info['furniture_count']} 障碍{info['obstacle_count']}"
    return detail


def catalog_detail_for_path(path):
    info = _store_summary_cache.get(path)
    if info:
        detail = f"{info['width']:g}×{info['height']:g}m"
        if info["furniture_count"] or info["obstacle_count"]:
            detail += f" · 家具{info['furniture_count']} 障碍{info['obstacle_count']}"
        return detail
    if os.path.isfile(path):
        return "已保存 · 点击打开"
    return "新建 20×15m"


def migrate_legacy_layout():
    if not os.path.isfile(LEGACY_LAYOUT_FILE):
        return None
    ensure_layouts_dir()
    target = os.path.join(LAYOUTS_DIR, "默认门店.json")
    if os.path.isfile(target):
        return target
    try:
        with open(LEGACY_LAYOUT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("name", "默认门店")
        with open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"已迁移旧版 saved_layout.json -> {target}")
        return target
    except Exception as exc:
        print(f"迁移 saved_layout.json 失败: {exc}")
        return None


def list_store_layouts():
    ensure_layouts_dir()
    migrate_legacy_layout()
    stores = []
    for fname in os.listdir(LAYOUTS_DIR):
        if not fname.lower().endswith(".json") or fname.startswith("_"):
            continue
        path = os.path.join(LAYOUTS_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            store = data.get("store", {})
            w = int(store.get("width_mm", 0)) / 1000
            h = int(store.get("height_mm", 0)) / 1000
            stores.append({
                "path": path,
                "name": data.get("name") or os.path.splitext(fname)[0],
                "width": w,
                "height": h,
                "furniture_count": len(data.get("furnitures", [])),
                "obstacle_count": len(data.get("obstacles", [])),
                "mtime": os.path.getmtime(path),
            })
        except Exception:
            continue
    stores.sort(key=lambda s: s["mtime"], reverse=True)
    return stores


def build_layout_data(filepath):
    return {
        "name": store_name,
        "store_slug": catalog_slug_for_path(filepath),
        "store": {"width_mm": store_width_mm, "height_mm": store_height_mm},
        "furnitures": [
            {
                "name": f.name,
                "roi": f.roi,
                "x": f.x,
                "y": f.y,
                "rotation": f.rotation,
                "points": f.points,
                "instance_id": getattr(f, "instance_id", "") or "",
                "attach_to": getattr(f, "attach_to", "") or "",
                "product_family": getattr(f, "product_family", "") or "",
            }
            for f in placed_furnitures
        ],
        "obstacles": collision_polygons,
        "markers": layout_markers,
        "heatmap": {
            "week_count": heatmap_week_count,
            "week_mode": heatmap_week_mode,
            "selected_week": (active_heatmap_week_keys()[0] if heatmap_week_mode == "single" and active_heatmap_week_keys() else ""),
        },
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def write_layout_data(filepath, data):
    ensure_layouts_dir()
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    store = data.get("store", {})
    remember_store_summary(
        filepath,
        width_m=int(store.get("width_mm", 0)) / 1000,
        height_m=int(store.get("height_mm", 0)) / 1000,
        furniture_count=len(data.get("furnitures", [])),
        obstacle_count=len(data.get("obstacles", [])),
    )


def save_layout(filepath=None, *, quiet=False):
    global current_layout_path, _pending_save_snapshot, _save_generation
    _save_generation += 1
    _pending_save_snapshot = None
    filepath = filepath or current_layout_path
    if not filepath:
        filepath = unique_layout_path(store_name)
    write_layout_data(filepath, build_layout_data(filepath))
    current_layout_path = filepath
    remember_last_store(filepath)
    if not quiet:
        show_toast(f"已保存门店: {store_name}")


def schedule_deferred_save():
    global _pending_save_snapshot
    if not current_layout_path:
        return
    _pending_save_snapshot = (
        current_layout_path,
        build_layout_data(current_layout_path),
        _save_generation,
    )


def _run_deferred_save(snapshot):
    filepath, data, generation = snapshot
    if generation != _save_generation:
        return
    try:
        write_layout_data(filepath, data)
        remember_last_store(filepath)
    except Exception as exc:
        print(f"后台保存失败: {exc}")


def flush_deferred_save(*, block=False):
    global _pending_save_snapshot, _save_thread
    if _save_thread and _save_thread.is_alive():
        if block:
            _save_thread.join()
        elif _pending_save_snapshot is None:
            return
        else:
            return
    if _pending_save_snapshot is None:
        return
    snapshot = _pending_save_snapshot
    _pending_save_snapshot = None
    if block:
        _run_deferred_save(snapshot)
        return
    _save_thread = threading.Thread(target=_run_deferred_save, args=(snapshot,), daemon=True)
    _save_thread.start()


def refresh_catalog_cache_async():
    global _catalog_refresh_thread, _catalog_refresh_ready
    if _catalog_refresh_thread and _catalog_refresh_thread.is_alive():
        return

    def worker():
        global _catalog_refresh_ready
        for _, slug in STORE_CATALOG:
            read_store_summary(layout_path_for_slug(slug))
        _catalog_refresh_ready = True

    _catalog_refresh_ready = False
    _catalog_refresh_thread = threading.Thread(target=worker, daemon=True)
    _catalog_refresh_thread.start()


def load_layout(filepath, *, keep_undo=False):
    global placed_furnitures, collision_polygons, store_width_mm, store_height_mm
    global store_name, current_layout_path, layout_markers, selected_marker_index
    global heatmap_week_count, heatmap_week_mode, heatmap_week_index, _pending_heatmap_week
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    store_name = data.get("name") or os.path.splitext(os.path.basename(filepath))[0]
    current_layout_path = filepath
    store = data.get("store", {})
    store_width_mm = int(store.get("width_mm", store_width_mm))
    store_height_mm = int(store.get("height_mm", store_height_mm))
    heatmap = data.get("heatmap") or {}
    heatmap_week_count = max(1, min(52, int(heatmap.get("week_count") or heatmap_week_count)))
    heatmap_week_mode = heatmap.get("week_mode") or heatmap_week_mode
    if heatmap_week_mode not in ("single", "range"):
        heatmap_week_mode = "single"
    clear_heatmap_cache()
    mark_heatmap_dirty()
    _pending_heatmap_week = str(heatmap.get("selected_week") or "").strip() or None
    heatmap_week_index = -1
    placed_furnitures = []
    for f in data.get("furnitures", []):
        name = f.get("name", "")
        family = str(f.get("product_family", "") or "").strip() or name
        roi = float(f.get("roi") or 0)
        furniture = Furniture(
            name,
            roi,
            f["points"],
            product_family=family,
        )
        furniture.x = f.get("x", 0)
        furniture.y = f.get("y", 0)
        furniture.rotation = f.get("rotation", 0)
        furniture.instance_id = f.get("instance_id", "") or ""
        furniture.attach_to = f.get("attach_to", "") or ""
        placed_furnitures.append(furniture)
    sync_furniture_instance_ids()
    collision_polygons = data.get("obstacles", [])
    layout_markers = normalize_layout_markers(data.get("markers", []))
    clear_furniture_display_cache()
    clear_obstacle_selection()
    selected_marker_index = None
    sync_group_id_counter()
    remember_store_summary(
        current_layout_path,
        width_m=store_width_mm / 1000,
        height_m=store_height_mm / 1000,
        furniture_count=len(placed_furnitures),
        obstacle_count=len(collision_polygons),
    )
    show_toast(
        f"已打开「{store_name}」{store_width_mm / 1000:g}×{store_height_mm / 1000:g} m, "
        f"{len(placed_furnitures)} 件家具, {len(collision_polygons)} 个障碍, {len(layout_markers)} 个图标"
    )
    slug = data.get("store_slug") or catalog_slug_for_path(filepath)
    if slug in CATALOG_LAYOUT_SPECS:
        exp_w, exp_h = CATALOG_LAYOUT_SPECS[slug]
        if store_width_mm != exp_w or store_height_mm != exp_h:
            show_toast(
                f"画布尺寸与默认户型不符（应为 {exp_w / 1000:g}×{exp_h / 1000:g} m），"
                f"请点侧栏「恢复默认」"
            )
    if not keep_undo:
        clear_undo()


def build_reset_confirm_buttons():
    cx = SCREEN_WIDTH // 2
    bw, bh = 100, 34
    y = SCREEN_HEIGHT // 2 + 36
    return {
        "ok": Button((cx - bw - 6, y, bw, bh), "确认恢复", "reset_ok", danger=True),
        "cancel": Button((cx + 6, y, bw, bh), "取消", "reset_cancel"),
    }


def cancel_reset_confirm():
    global pending_reset_confirm
    pending_reset_confirm = False


def start_reset_catalog_layout():
    global pending_reset_confirm, reset_confirm_buttons
    slug = catalog_slug_for_path(current_layout_path)
    if not slug:
        show_toast("仅内置门店可恢复默认布局")
        return
    tpl = template_path_for_slug(slug)
    if not os.path.isfile(tpl):
        show_toast("未找到默认模板，请运行 tools/generate_onehunga_layout.py")
        return
    pending_reset_confirm = True
    reset_confirm_buttons = build_reset_confirm_buttons()


def apply_reset_catalog_layout():
    global pending_reset_confirm
    slug = catalog_slug_for_path(current_layout_path)
    tpl = template_path_for_slug(slug)
    path = layout_path_for_slug(slug)
    pending_reset_confirm = False
    flush_deferred_save(block=True)
    push_undo()
    try:
        shutil.copy2(tpl, path)
    except OSError as exc:
        show_toast(f"恢复失败: {exc}")
        return
    load_layout(path, keep_undo=True)
    fit_view_to_store()
    remember_last_store(path)
    show_toast("已恢复默认布局，可按 Ctrl+Z 撤销")


def handle_reset_confirm_click(mx, my):
    mx, my = ui_pos((mx, my))
    for btn in reset_confirm_buttons.values():
        if btn.contains((mx, my)):
            if btn.action == "reset_ok":
                apply_reset_catalog_layout()
            else:
                cancel_reset_confirm()
            return True
    return False


def draw_reset_confirm_dialog(surface):
    if not pending_reset_confirm:
        return
    overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    overlay.fill((15, 23, 42, 120))
    surface.blit(overlay, (0, 0))
    box = pygame.Rect(SCREEN_WIDTH // 2 - 240, SCREEN_HEIGHT // 2 - 88, 480, 190)
    pygame.draw.rect(surface, (255, 255, 255), box, border_radius=12)
    pygame.draw.rect(surface, C_BORDER, box, 1, border_radius=12)
    surface.blit(FONT_LABEL.render("恢复默认布局？", True, C_TEXT), (box.x + 20, box.y + 16))
    lines = [
        "将用内置模板覆盖当前门店的全部障碍、墙体与家具。",
        "若只想把画面居中，请点侧栏「居中视图」。",
        "确认后仍可用 Ctrl+Z 撤销。",
    ]
    y = box.y + 48
    for line in lines:
        surface.blit(FONT_SMALL.render(line, True, C_MUTED), (box.x + 20, y))
        y += 22
    for btn in reset_confirm_buttons.values():
        btn.draw(surface)


def reset_catalog_layout():
    start_reset_catalog_layout()


def create_store_layout(name, width_m, height_m, filepath=None):
    global store_name, current_layout_path, placed_furnitures, collision_polygons, startup_active, layout_markers
    store_name = (name or "新门店").strip() or "新门店"
    current_layout_path = filepath or unique_layout_path(store_name)
    placed_furnitures = []
    collision_polygons = []
    layout_markers = []
    clear_undo()
    set_store_size(width_m, height_m)
    save_layout(current_layout_path)
    remember_last_store(current_layout_path)
    startup_active = False
    show_toast(f"已创建门店: {store_name}")


def open_catalog_store(slug):
    name = catalog_name_for_slug(slug)
    path = layout_path_for_slug(slug)
    if os.path.isfile(path):
        switch_store_layout(path)
    else:
        create_store_layout(name, DEFAULT_STORE_WIDTH_M, DEFAULT_STORE_HEIGHT_M, filepath=path)


def switch_store_layout(path):
    flush_deferred_save(block=True)
    if current_layout_path and os.path.isfile(current_layout_path):
        try:
            save_layout(current_layout_path)
        except Exception:
            pass
    load_layout(path)
    fit_view_to_store()
    remember_last_store(path)


def rename_current_store(new_name):
    global store_name, current_layout_path
    new_name = (new_name or "").strip()
    if not new_name:
        show_toast("门店名称不能为空")
        return
    if catalog_slug_for_path(current_layout_path):
        store_name = new_name
        save_layout(current_layout_path)
        show_toast(f"门店显示名称已改为: {store_name}")
        return
    old_path = current_layout_path
    store_name = new_name
    new_path = unique_layout_path(store_name)
    if old_path and os.path.abspath(old_path) != os.path.abspath(new_path):
        save_layout(new_path)
        if os.path.isfile(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass
        current_layout_path = new_path
    else:
        save_layout(current_layout_path)
    show_toast(f"门店已重命名为: {store_name}")


def save_current_layout():
    if current_layout_path:
        save_layout(current_layout_path)
    else:
        popup_save_dialog()


def popup_save_dialog():
    pygame.event.pump()
    get_tk_root().update()
    path = filedialog.asksaveasfilename(
        parent=get_tk_root(),
        initialdir=LAYOUTS_DIR,
        defaultextension=".json",
        filetypes=[("JSON", "*.json")],
        title="另存为门店布局",
    )
    if path:
        if not path.lower().endswith(".json"):
            path += ".json"
        save_layout(path)


def popup_load_dialog():
    pygame.event.pump()
    get_tk_root().update()
    path = filedialog.askopenfilename(
        parent=get_tk_root(),
        initialdir=LAYOUTS_DIR,
        defaultextension=".json",
        filetypes=[("JSON", "*.json")],
        title="打开门店布局",
    )
    if path:
        try:
            switch_store_layout(path)
        except Exception as e:
            show_toast(f"加载失败: {e}")


def _raise_tk_window(win):
    win.update_idletasks()
    w = win.winfo_width()
    h = win.winfo_height()
    x = max(0, (win.winfo_screenwidth() - w) // 2)
    y = max(0, (win.winfo_screenheight() - h) // 2)
    win.geometry(f"+{x}+{y}")
    try:
        win.attributes("-topmost", True)
        win.after(200, lambda: win.attributes("-topmost", False))
    except tk.TclError:
        pass
    win.lift()
    win.focus_force()


def _parse_store_size_fields(width_var, height_var, parent):
    try:
        width_m = float(width_var.get().strip())
        height_m = float(height_var.get().strip())
    except ValueError as exc:
        raise ValueError("请输入有效的数字（单位：米）") from exc
    if width_m <= 0 or height_m <= 0:
        raise ValueError("宽高必须大于 0")
    return width_m, height_m


def show_store_size_dialog(title="门店画布尺寸", width_m=None, height_m=None):
    width_m = DEFAULT_STORE_WIDTH_M if width_m is None else float(width_m)
    height_m = DEFAULT_STORE_HEIGHT_M if height_m is None else float(height_m)
    result = {"ok": False}

    win = tk.Toplevel(get_tk_root())
    win.title(title)
    win.resizable(False, False)
    win.transient(get_tk_root())
    win.grab_set()

    tk.Label(
        win,
        text="设置门店平面外框（米）。可摆放区域为外框内，障碍物用刨除方式挖掉。",
        wraplength=360,
        justify="left",
    ).pack(padx=16, pady=(16, 10), anchor="w")

    preset_var = tk.StringVar(value=STORE_PRESETS[1][0])
    width_var = tk.StringVar(value=f"{width_m:g}")
    height_var = tk.StringVar(value=f"{height_m:g}")

    preset_frame = tk.Frame(win)
    preset_frame.pack(fill="x", padx=16, pady=(0, 8))
    tk.Label(preset_frame, text="预设:").pack(side="left")
    preset_menu = tk.OptionMenu(
        preset_frame,
        preset_var,
        *[label for label, _, _ in STORE_PRESETS],
    )
    preset_menu.pack(side="left", padx=(8, 0))

    def apply_preset(*_):
        for label, w, h in STORE_PRESETS:
            if preset_var.get() != label:
                continue
            if w is not None and h is not None:
                width_var.set(f"{w:g}")
                height_var.set(f"{h:g}")
            break

    preset_var.trace_add("write", apply_preset)

    size_frame = tk.Frame(win)
    size_frame.pack(fill="x", padx=16, pady=8)
    tk.Label(size_frame, text="宽 (m):").grid(row=0, column=0, sticky="w", pady=4)
    tk.Entry(size_frame, textvariable=width_var, width=12).grid(row=0, column=1, padx=(8, 24), sticky="w")
    tk.Label(size_frame, text="深 (m):").grid(row=0, column=2, sticky="w", pady=4)
    tk.Entry(size_frame, textvariable=height_var, width=12).grid(row=0, column=3, padx=(8, 0), sticky="w")

    btn_frame = tk.Frame(win)
    btn_frame.pack(fill="x", padx=16, pady=(12, 16))

    def on_ok():
        try:
            result["width_m"], result["height_m"] = _parse_store_size_fields(width_var, height_var, win)
            result["ok"] = True
            win.destroy()
        except ValueError as exc:
            messagebox.showerror("输入错误", str(exc), parent=win)

    def on_cancel():
        win.destroy()

    tk.Button(btn_frame, text="确定", width=10, command=on_ok).pack(side="right")
    tk.Button(btn_frame, text="取消", width=10, command=on_cancel).pack(side="right", padx=(0, 8))

    _raise_tk_window(win)

    get_tk_root().wait_window(win)
    return result


def popup_store_size_dialog():
    start_edit_canvas_size()


def start_edit_canvas_size():
    global editing_canvas_size, canvas_w_text, canvas_h_text, canvas_size_focus, canvas_size_buttons
    global editing_wall_size
    editing_canvas_size = True
    editing_wall_size = False
    cancel_rename_dialog()
    cancel_obstacle_edit_dialog()
    canvas_w_text = f"{store_width_mm / 1000:g}"
    canvas_h_text = f"{store_height_mm / 1000:g}"
    canvas_size_focus = "width"
    canvas_size_buttons = build_canvas_size_dialog_buttons()


def build_canvas_size_dialog_buttons():
    cx = SCREEN_WIDTH // 2
    bw, bh = 88, 34
    gap = 8
    y = SCREEN_HEIGHT // 2 + 36
    buttons = {}
    presets = [("12×8", 12, 8), ("20×15", 20, 15), ("30×20", 30, 20)]
    total_w = len(presets) * bw + (len(presets) - 1) * gap
    x = cx - total_w // 2
    for i, (label, w, h) in enumerate(presets):
        buttons[f"preset_{i}"] = Button((x, y, bw, bh), label, f"size_preset:{w}:{h}")
        x += bw + gap
    y += bh + 14
    buttons["ok"] = Button((cx - bw - 6, y, bw, bh), "确定", "size_ok", primary=True)
    buttons["cancel"] = Button((cx + 6, y, bw, bh), "取消", "size_cancel")
    return buttons


def apply_canvas_size():
    global editing_canvas_size
    try:
        w = float(canvas_w_text.strip())
        h = float(canvas_h_text.strip())
    except ValueError:
        show_toast("请输入有效的宽高数字（米）")
        return
    if w <= 0 or h <= 0:
        show_toast("宽高必须大于 0")
        return
    set_store_size(w, h)
    save_current_layout()
    editing_canvas_size = False
    show_toast(f"画布已改为 {w:g}×{h:g} m")


def cancel_canvas_size_edit():
    global editing_canvas_size
    editing_canvas_size = False


def handle_canvas_size_action(action):
    if action == "size_ok":
        apply_canvas_size()
    elif action == "size_cancel":
        cancel_canvas_size_edit()
    elif action.startswith("size_preset:"):
        _, w, h = action.split(":")
        global canvas_w_text, canvas_h_text
        canvas_w_text = w
        canvas_h_text = h
        apply_canvas_size()


def handle_canvas_size_click(mx, my):
    global canvas_size_focus, canvas_w_text, canvas_h_text
    mx, my = ui_pos((mx, my))
    if canvas_size_width_rect and canvas_size_width_rect.collidepoint(mx, my):
        canvas_size_focus = "width"
        return True
    if canvas_size_height_rect and canvas_size_height_rect.collidepoint(mx, my):
        canvas_size_focus = "height"
        return True
    for btn in canvas_size_buttons.values():
        if btn.contains((mx, my)):
            handle_canvas_size_action(btn.action)
            return True
    return False


def draw_canvas_size_dialog(surface):
    global canvas_size_width_rect, canvas_size_height_rect
    overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    overlay.fill((15, 23, 42, 120))
    surface.blit(overlay, (0, 0))
    box = pygame.Rect(SCREEN_WIDTH // 2 - 220, SCREEN_HEIGHT // 2 - 130, 440, 260)
    pygame.draw.rect(surface, (255, 255, 255), box, border_radius=12)
    pygame.draw.rect(surface, C_BORDER, box, 1, border_radius=12)
    surface.blit(FONT_LABEL.render("修改画布尺寸", True, C_TEXT), (box.x + 20, box.y + 16))
    surface.blit(
        FONT_SMALL.render(f"门店: {store_name}  |  单位: 米", True, C_MUTED),
        (box.x + 20, box.y + 44),
    )
    surface.blit(FONT_SMALL.render("宽 (m)", True, C_TEXT), (box.x + 20, box.y + 78))
    canvas_size_width_rect = pygame.Rect(box.x + 20, box.y + 100, 180, 36)
    surface.blit(FONT_SMALL.render("深 (m)", True, C_TEXT), (box.x + 220, box.y + 78))
    canvas_size_height_rect = pygame.Rect(box.x + 220, box.y + 100, 180, 36)
    for rect, text, focused in (
        (canvas_size_width_rect, canvas_w_text, canvas_size_focus == "width"),
        (canvas_size_height_rect, canvas_h_text, canvas_size_focus == "height"),
    ):
        pygame.draw.rect(surface, (248, 250, 252), rect, border_radius=8)
        pygame.draw.rect(surface, C_ACCENT if focused else C_BORDER, rect, 2 if focused else 1, border_radius=8)
        surface.blit(FONT_BODY.render(text + ("|" if focused else ""), True, C_TEXT), (rect.x + 10, rect.y + 8))
    for btn in canvas_size_buttons.values():
        btn.draw(surface)


def start_edit_wall_size():
    global editing_wall_size, wall_length_text, wall_width_text, wall_size_focus, wall_size_buttons
    global editing_canvas_size, wall_size_edit_index
    editing_wall_size = True
    wall_size_edit_index = None
    editing_canvas_size = False
    cancel_rename_dialog()
    cancel_obstacle_edit_dialog()
    toggle_draw_obstacle(False)
    wall_length_text = "3"
    wall_width_text = "0.2"
    wall_size_focus = "length"
    wall_size_buttons = build_wall_size_dialog_buttons()


def start_edit_obstacle_size():
    start_edit_obstacle_dialog()


def build_obstacle_edit_dialog_buttons():
    cx = SCREEN_WIDTH // 2
    bw, bh = 88, 34
    y = SCREEN_HEIGHT // 2 + 118
    return {
        "ok": Button((cx - bw - 6, y, bw, bh), "确定", "obstacle_edit_ok", primary=True),
        "cancel": Button((cx + 6, y, bw, bh), "取消", "obstacle_edit_cancel"),
    }


def draw_inline_checkbox(surface, rect, checked, label):
    pygame.draw.rect(surface, (255, 255, 255), rect, border_radius=4)
    pygame.draw.rect(surface, C_ACCENT if checked else C_BORDER, rect, 2, border_radius=4)
    if checked:
        inner = rect.inflate(-8, -8)
        pygame.draw.rect(surface, C_ACCENT, inner, border_radius=2)
    text = FONT_SMALL.render(label, True, C_TEXT)
    surface.blit(text, (rect.right + 10, rect.centery - text.get_height() // 2))


def _sync_obstacle_edit_ime():
    try:
        if obstacle_edit_focus == "name" and obstacle_edit_name_rect:
            pygame.key.start_text_input()
            pygame.key.set_text_input_rect(obstacle_edit_name_rect)
        else:
            pygame.key.stop_text_input()
    except Exception:
        pass


def cancel_obstacle_edit_dialog():
    global editing_obstacle_dialog, obstacle_edit_index, obstacle_edit_name, obstacle_edit_length
    global obstacle_edit_width, obstacle_edit_focus, obstacle_edit_composition, obstacle_edit_show_label
    editing_obstacle_dialog = False
    obstacle_edit_index = None
    obstacle_edit_name = ""
    obstacle_edit_length = ""
    obstacle_edit_width = ""
    obstacle_edit_focus = "name"
    obstacle_edit_composition = ""
    obstacle_edit_show_label = False
    try:
        pygame.key.stop_text_input()
    except Exception:
        pass


def start_edit_obstacle_dialog(index=None):
    global editing_obstacle_dialog, obstacle_edit_index, obstacle_edit_name, obstacle_edit_length
    global obstacle_edit_width, obstacle_edit_focus, obstacle_edit_composition, obstacle_edit_buttons
    global obstacle_edit_show_label
    if index is None:
        if len(selected_collisions) != 1:
            show_toast("请单选一个长方形障碍或墙体")
            return
        index = selected_collision
    if index < 0 or index >= len(collision_polygons):
        return
    metrics = obstacle_rect_metrics(collision_polygons[index]["points"])
    if not metrics:
        show_toast("仅支持长方形障碍/墙体（多边形请重新绘制）")
        return
    cancel_rename_dialog()
    cancel_wall_size_edit()
    cancel_marker_edit_dialog()
    toggle_draw_obstacle(False)
    _, _, length_mm, width_mm = metrics
    editing_obstacle_dialog = True
    obstacle_edit_index = index
    obstacle_edit_name = collision_polygons[index].get("name", "")
    obstacle_edit_length = f"{length_mm / 1000:g}"
    obstacle_edit_width = f"{width_mm / 1000:g}"
    obstacle_edit_focus = "name"
    obstacle_edit_composition = ""
    obstacle_edit_show_label = bool(collision_polygons[index].get("user_named"))
    obstacle_edit_buttons = build_obstacle_edit_dialog_buttons()
    set_obstacle_selection([index])
    _sync_obstacle_edit_ime()
    show_toast("可修改名称与尺寸，Enter 确认")


def apply_obstacle_edit_dialog():
    global editing_obstacle_dialog, obstacle_edit_index, obstacle_edit_show_label
    if obstacle_edit_index is None or obstacle_edit_index >= len(collision_polygons):
        cancel_obstacle_edit_dialog()
        return
    name = obstacle_edit_name.strip()
    if not name:
        show_toast("名称不能为空")
        return
    for i, col in enumerate(collision_polygons):
        if i != obstacle_edit_index and col.get("name") == name:
            show_toast(f"名称「{name}」已被使用")
            return
    try:
        length_m = float(obstacle_edit_length.strip())
        width_m = float(obstacle_edit_width.strip())
    except ValueError:
        show_toast("请输入有效的长宽数字（米）")
        return
    if length_m <= 0 or width_m <= 0:
        show_toast("长宽必须大于 0")
        return
    idx = obstacle_edit_index
    col = collision_polygons[idx]
    old_name = col.get("name", "")
    metrics = obstacle_rect_metrics(col["points"])
    old_length_m = metrics[2] / 1000 if metrics else 0
    old_width_m = metrics[3] / 1000 if metrics else 0
    rename_changed = name != old_name
    size_changed = abs(length_m - old_length_m) > 0.001 or abs(width_m - old_width_m) > 0.001
    label_changed = bool(col.get("user_named")) != obstacle_edit_show_label
    if not rename_changed and not size_changed and not label_changed:
        cancel_obstacle_edit_dialog()
        return
    push_undo()
    if rename_changed:
        col["name"] = name
    if obstacle_edit_show_label:
        col["user_named"] = True
    else:
        col.pop("user_named", None)
    if size_changed and not resize_obstacle_rect(idx, length_m, width_m):
        show_toast("尺寸无效或未与门店画布重叠")
        cancel_obstacle_edit_dialog()
        return
    cancel_obstacle_edit_dialog()
    if rename_changed and size_changed:
        msg = f"已更新为「{name}」 {length_m:g}×{width_m:g} m"
        show_toast(msg)
    elif rename_changed:
        show_toast("重命名成功")
    elif label_changed:
        show_toast("已在画布显示名称" if obstacle_edit_show_label else "已隐藏画布名称")
    else:
        show_toast(f"已更新尺寸为 {length_m:g}×{width_m:g} m")


def handle_obstacle_edit_dialog_action(action):
    if action == "obstacle_edit_ok":
        apply_obstacle_edit_dialog()
    elif action == "obstacle_edit_cancel":
        cancel_obstacle_edit_dialog()


def handle_obstacle_edit_dialog_click(mx, my):
    global obstacle_edit_focus, obstacle_edit_length, obstacle_edit_width, obstacle_edit_show_label
    mx, my = ui_pos((mx, my))
    if obstacle_edit_show_label_rect:
        hit = pygame.Rect(
            obstacle_edit_show_label_rect.x,
            obstacle_edit_show_label_rect.y - 4,
            180,
            obstacle_edit_show_label_rect.height + 8,
        )
        if hit.collidepoint(mx, my):
            obstacle_edit_show_label = not obstacle_edit_show_label
            obstacle_edit_focus = "label"
            _sync_obstacle_edit_ime()
            return True
    if obstacle_edit_name_rect and obstacle_edit_name_rect.collidepoint(mx, my):
        obstacle_edit_focus = "name"
        _sync_obstacle_edit_ime()
        return True
    if obstacle_edit_length_rect and obstacle_edit_length_rect.collidepoint(mx, my):
        obstacle_edit_focus = "length"
        _sync_obstacle_edit_ime()
        return True
    if obstacle_edit_width_rect and obstacle_edit_width_rect.collidepoint(mx, my):
        obstacle_edit_focus = "width"
        _sync_obstacle_edit_ime()
        return True
    for btn in obstacle_edit_buttons.values():
        if btn.contains((mx, my)):
            handle_obstacle_edit_dialog_action(btn.action)
            return True
    return False


def handle_obstacle_edit_text_event(event):
    global obstacle_edit_name, obstacle_edit_composition
    if not editing_obstacle_dialog or obstacle_edit_focus != "name":
        return False
    if event.type == pygame.TEXTEDITING:
        obstacle_edit_composition = event.text or ""
        return True
    if event.type == pygame.TEXTINPUT:
        obstacle_edit_composition = ""
        if event.text:
            obstacle_edit_name += event.text
        return True
    return False


def _delete_obstacle_edit_char():
    global obstacle_edit_name, obstacle_edit_composition, obstacle_edit_length, obstacle_edit_width
    if obstacle_edit_focus == "name":
        if obstacle_edit_composition:
            obstacle_edit_composition = obstacle_edit_composition[:-1]
        elif obstacle_edit_name:
            obstacle_edit_name = obstacle_edit_name[:-1]
    elif obstacle_edit_focus == "length" and obstacle_edit_length:
        obstacle_edit_length = obstacle_edit_length[:-1]
    elif obstacle_edit_focus == "width" and obstacle_edit_width:
        obstacle_edit_width = obstacle_edit_width[:-1]


def _delete_rename_char():
    global input_text, rename_composition
    if rename_composition:
        rename_composition = rename_composition[:-1]
    elif input_text:
        input_text = input_text[:-1]


def _note_backspace_pressed():
    global _backspace_hold_start, _backspace_last_delete
    now = pygame.time.get_ticks()
    _backspace_hold_start = now
    _backspace_last_delete = now


def poll_dialog_backspace_repeat():
    global _backspace_hold_start, _backspace_last_delete
    if not (editing_obstacle_dialog or editing_marker_dialog or renaming_store):
        _backspace_hold_start = 0
        return
    if not pygame.key.get_pressed()[pygame.K_BACKSPACE]:
        _backspace_hold_start = 0
        return
    now = pygame.time.get_ticks()
    if _backspace_hold_start == 0:
        return
    if now - _backspace_hold_start < 400:
        return
    if _backspace_last_delete and now - _backspace_last_delete < 35:
        return
    _backspace_last_delete = now
    if editing_obstacle_dialog:
        _delete_obstacle_edit_char()
    elif editing_marker_dialog:
        _delete_marker_edit_char()
    else:
        _delete_rename_char()


def handle_obstacle_edit_dialog_key(event):
    global obstacle_edit_name, obstacle_edit_length, obstacle_edit_width
    global obstacle_edit_focus, obstacle_edit_composition
    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
        apply_obstacle_edit_dialog()
    elif event.key == pygame.K_ESCAPE:
        cancel_obstacle_edit_dialog()
    elif event.key == pygame.K_TAB:
        order = ("name", "length", "width")
        i = (order.index(obstacle_edit_focus) + 1) % len(order)
        obstacle_edit_focus = order[i]
        _sync_obstacle_edit_ime()
    elif event.key == pygame.K_BACKSPACE:
        _note_backspace_pressed()
        _delete_obstacle_edit_char()
    elif event.unicode:
        ch = event.unicode
        if obstacle_edit_focus == "name":
            return
        field = obstacle_edit_length if obstacle_edit_focus == "length" else obstacle_edit_width
        if ch.isdigit() and len(field) < 6:
            if obstacle_edit_focus == "length":
                obstacle_edit_length += ch
            else:
                obstacle_edit_width += ch
        elif ch == "." and "." not in field and len(field) < 6:
            if obstacle_edit_focus == "length":
                obstacle_edit_length += ch
            else:
                obstacle_edit_width += ch


def build_marker_edit_dialog_buttons():
    cx = SCREEN_WIDTH // 2
    bw, bh = 88, 34
    y = SCREEN_HEIGHT // 2 + 118
    return {
        "ok": Button((cx - bw - 6, y, bw, bh), "确定", "marker_edit_ok", primary=True),
        "cancel": Button((cx + 6, y, bw, bh), "取消", "marker_edit_cancel"),
    }


def cancel_marker_edit_dialog():
    global editing_marker_dialog, editing_marker_index, marker_edit_name, marker_edit_show_label
    global marker_edit_focus, marker_edit_composition, marker_edit_length, marker_edit_width
    editing_marker_dialog = False
    editing_marker_index = None
    marker_edit_name = ""
    marker_edit_show_label = False
    marker_edit_focus = "name"
    marker_edit_composition = ""
    marker_edit_length = ""
    marker_edit_width = ""
    try:
        pygame.key.stop_text_input()
    except Exception:
        pass


def _sync_marker_edit_ime():
    global marker_edit_composition
    marker_edit_composition = ""
    try:
        if marker_edit_name_rect:
            pygame.key.start_text_input()
            pygame.key.set_text_input_rect(marker_edit_name_rect)
    except Exception:
        pass


def start_edit_marker_dialog(index=None, *, focus_size=False):
    global editing_marker_dialog, editing_marker_index, marker_edit_name, marker_edit_show_label
    global marker_edit_focus, marker_edit_composition, marker_edit_buttons
    global marker_edit_length, marker_edit_width
    if index is None:
        if selected_marker_index is None:
            show_toast("请先选中一个图标")
            return
        index = selected_marker_index
    if index < 0 or index >= len(layout_markers):
        return
    cancel_obstacle_edit_dialog()
    cancel_rename_dialog()
    editing_marker_dialog = True
    editing_marker_index = index
    marker = layout_markers[index]
    marker_edit_name = marker.get("label") or marker_default_label(marker.get("kind", "entrance"))
    marker_edit_show_label = bool(marker.get("user_named"))
    marker_edit_length = f"{marker_width_mm(marker) / 1000:g}"
    marker_edit_width = f"{marker_height_mm(marker) / 1000:g}"
    marker_edit_focus = "length" if focus_size else "name"
    marker_edit_composition = ""
    marker_edit_buttons = build_marker_edit_dialog_buttons()
    set_marker_selection(index)
    _sync_marker_edit_ime()
    show_toast("可修改名称与宽×高（米），Enter 确认")


def apply_marker_edit_dialog():
    global editing_marker_dialog, editing_marker_index, marker_edit_show_label
    if editing_marker_index is None or editing_marker_index >= len(layout_markers):
        cancel_marker_edit_dialog()
        return
    name = marker_edit_name.strip()
    if not name:
        show_toast("名称不能为空")
        return
    try:
        length_m = float(marker_edit_length.strip())
        width_m = float(marker_edit_width.strip())
    except ValueError:
        show_toast("请输入有效的宽×高数字（米）")
        return
    if length_m <= 0 or width_m <= 0:
        show_toast("宽和高必须大于 0")
        return
    marker = layout_markers[editing_marker_index]
    old_name = marker.get("label") or marker_default_label(marker.get("kind", "entrance"))
    old_w = marker_width_mm(marker) / 1000
    old_h = marker_height_mm(marker) / 1000
    label_changed = bool(marker.get("user_named")) != marker_edit_show_label
    rename_changed = name != old_name
    size_changed = abs(length_m - old_w) > 0.001 or abs(width_m - old_h) > 0.001
    if not rename_changed and not label_changed and not size_changed:
        cancel_marker_edit_dialog()
        return
    push_undo()
    marker["label"] = name
    marker["width_mm"] = int(round(length_m * 1000))
    marker["height_mm"] = int(round(width_m * 1000))
    if marker_edit_show_label:
        marker["user_named"] = True
    else:
        marker.pop("user_named", None)
    cancel_marker_edit_dialog()
    if size_changed and rename_changed:
        show_toast(f"已更新为「{name}」 {length_m:g}×{width_m:g} m")
    elif size_changed:
        show_toast(f"已更新尺寸为 {length_m:g}×{width_m:g} m")
    elif label_changed:
        show_toast("已在画布显示名称" if marker_edit_show_label else "已隐藏画布名称")
    else:
        show_toast("重命名成功")


def handle_marker_edit_dialog_action(action):
    if action == "marker_edit_ok":
        apply_marker_edit_dialog()
    elif action == "marker_edit_cancel":
        cancel_marker_edit_dialog()


def handle_marker_edit_dialog_click(mx, my):
    global marker_edit_focus, marker_edit_show_label
    mx, my = ui_pos((mx, my))
    if marker_edit_show_label_rect:
        hit = pygame.Rect(
            marker_edit_show_label_rect.x,
            marker_edit_show_label_rect.y - 4,
            180,
            marker_edit_show_label_rect.height + 8,
        )
        if hit.collidepoint(mx, my):
            marker_edit_show_label = not marker_edit_show_label
            marker_edit_focus = "label"
            _sync_marker_edit_ime()
            return True
    if marker_edit_name_rect and marker_edit_name_rect.collidepoint(mx, my):
        marker_edit_focus = "name"
        _sync_marker_edit_ime()
        return True
    if marker_edit_length_rect and marker_edit_length_rect.collidepoint(mx, my):
        marker_edit_focus = "length"
        _sync_marker_edit_ime()
        return True
    if marker_edit_width_rect and marker_edit_width_rect.collidepoint(mx, my):
        marker_edit_focus = "width"
        _sync_marker_edit_ime()
        return True
    for btn in marker_edit_buttons.values():
        if btn.contains((mx, my)):
            handle_marker_edit_dialog_action(btn.action)
            return True
    return False


def handle_marker_edit_text_event(event):
    global marker_edit_name, marker_edit_composition
    if not editing_marker_dialog or marker_edit_focus != "name":
        return False
    if event.type == pygame.TEXTEDITING:
        marker_edit_composition = event.text or ""
        return True
    if event.type == pygame.TEXTINPUT:
        marker_edit_composition = ""
        if event.text:
            marker_edit_name += event.text
        return True
    return False


def _delete_marker_edit_char():
    global marker_edit_name, marker_edit_composition, marker_edit_length, marker_edit_width
    if marker_edit_focus == "name":
        if marker_edit_composition:
            marker_edit_composition = marker_edit_composition[:-1]
        elif marker_edit_name:
            marker_edit_name = marker_edit_name[:-1]
    elif marker_edit_focus == "length" and marker_edit_length:
        marker_edit_length = marker_edit_length[:-1]
    elif marker_edit_focus == "width" and marker_edit_width:
        marker_edit_width = marker_edit_width[:-1]


def handle_marker_edit_dialog_key(event):
    global marker_edit_focus, marker_edit_composition, marker_edit_length, marker_edit_width
    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
        apply_marker_edit_dialog()
    elif event.key == pygame.K_ESCAPE:
        cancel_marker_edit_dialog()
    elif event.key == pygame.K_TAB:
        order = ("name", "length", "width")
        i = (order.index(marker_edit_focus) + 1) % len(order) if marker_edit_focus in order else 0
        marker_edit_focus = order[i]
        _sync_marker_edit_ime()
    elif event.key == pygame.K_BACKSPACE:
        _note_backspace_pressed()
        _delete_marker_edit_char()
    elif event.unicode:
        ch = event.unicode
        if marker_edit_focus == "name":
            return
        field = marker_edit_length if marker_edit_focus == "length" else marker_edit_width
        if ch.isdigit() and len(field) < 6:
            if marker_edit_focus == "length":
                marker_edit_length += ch
            else:
                marker_edit_width += ch
        elif ch == "." and "." not in field and len(field) < 6:
            if marker_edit_focus == "length":
                marker_edit_length += ch
            else:
                marker_edit_width += ch


def draw_marker_edit_dialog(surface):
    global marker_edit_name_rect, marker_edit_show_label_rect
    global marker_edit_length_rect, marker_edit_width_rect
    if not editing_marker_dialog or editing_marker_index is None:
        marker_edit_name_rect = None
        marker_edit_show_label_rect = None
        marker_edit_length_rect = marker_edit_width_rect = None
        return
    marker = layout_markers[editing_marker_index]
    kind_label = MARKER_KINDS.get(marker.get("kind"), "图标")
    overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    overlay.fill((15, 23, 42, 120))
    surface.blit(overlay, (0, 0))
    box = pygame.Rect(SCREEN_WIDTH // 2 - 220, SCREEN_HEIGHT // 2 - 130, 440, 300)
    pygame.draw.rect(surface, (255, 255, 255), box, border_radius=12)
    pygame.draw.rect(surface, C_BORDER, box, 1, border_radius=12)
    surface.blit(FONT_LABEL.render(f"编辑{kind_label}", True, C_TEXT), (box.x + 20, box.y + 16))
    surface.blit(
        FONT_SMALL.render("宽×高按图标朝向；楼梯建议设实际踏步宽度", True, C_MUTED),
        (box.x + 20, box.y + 42),
    )
    surface.blit(FONT_SMALL.render("名称", True, C_MUTED), (box.x + 20, box.y + 66))
    marker_edit_name_rect = pygame.Rect(box.x + 20, box.y + 84, box.width - 40, 36)
    pygame.draw.rect(surface, (248, 250, 252), marker_edit_name_rect, border_radius=8)
    border = C_ACCENT if marker_edit_focus == "name" else C_BORDER
    pygame.draw.rect(surface, border, marker_edit_name_rect, 2, border_radius=8)
    name_text = marker_edit_name + (marker_edit_composition if marker_edit_focus == "name" else "")
    if marker_edit_focus == "name":
        name_text += "|"
    surface.blit(
        FONT_BODY.render(name_text, True, C_TEXT),
        (marker_edit_name_rect.x + 10, marker_edit_name_rect.y + 8),
    )
    surface.blit(FONT_SMALL.render("宽 (m)", True, C_TEXT), (box.x + 20, box.y + 130))
    marker_edit_length_rect = pygame.Rect(box.x + 20, box.y + 150, 180, 36)
    surface.blit(FONT_SMALL.render("高 (m)", True, C_TEXT), (box.x + 220, box.y + 130))
    marker_edit_width_rect = pygame.Rect(box.x + 220, box.y + 150, 180, 36)
    for rect, text, focused in (
        (marker_edit_length_rect, marker_edit_length, marker_edit_focus == "length"),
        (marker_edit_width_rect, marker_edit_width, marker_edit_focus == "width"),
    ):
        pygame.draw.rect(surface, (248, 250, 252), rect, border_radius=8)
        pygame.draw.rect(surface, C_ACCENT if focused else C_BORDER, rect, 2 if focused else 1, border_radius=8)
        surface.blit(FONT_BODY.render(text + ("|" if focused else ""), True, C_TEXT), (rect.x + 10, rect.y + 8))
    marker_edit_show_label_rect = pygame.Rect(box.x + 20, box.y + 198, 20, 20)
    pygame.draw.rect(surface, (248, 250, 252), marker_edit_show_label_rect, border_radius=4)
    pygame.draw.rect(surface, C_BORDER, marker_edit_show_label_rect, 1, border_radius=4)
    if marker_edit_show_label:
        pygame.draw.line(
            surface,
            C_ACCENT,
            (marker_edit_show_label_rect.x + 4, marker_edit_show_label_rect.centery),
            (marker_edit_show_label_rect.centerx - 1, marker_edit_show_label_rect.bottom - 5),
            2,
        )
        pygame.draw.line(
            surface,
            C_ACCENT,
            (marker_edit_show_label_rect.centerx - 1, marker_edit_show_label_rect.bottom - 5),
            (marker_edit_show_label_rect.right - 4, marker_edit_show_label_rect.y + 5),
            2,
        )
    surface.blit(
        FONT_SMALL.render("在画布显示名称", True, C_TEXT),
        (marker_edit_show_label_rect.right + 8, marker_edit_show_label_rect.y + 1),
    )
    for btn in marker_edit_buttons.values():
        btn.draw(surface)


def draw_obstacle_edit_dialog(surface):
    global obstacle_edit_name_rect, obstacle_edit_length_rect, obstacle_edit_width_rect
    global obstacle_edit_show_label_rect
    if not editing_obstacle_dialog or obstacle_edit_index is None:
        obstacle_edit_name_rect = obstacle_edit_length_rect = obstacle_edit_width_rect = None
        obstacle_edit_show_label_rect = None
        return
    col = collision_polygons[obstacle_edit_index]
    is_wall = obstacle_is_wall(col)
    overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    overlay.fill((15, 23, 42, 120))
    surface.blit(overlay, (0, 0))
    box = pygame.Rect(SCREEN_WIDTH // 2 - 220, SCREEN_HEIGHT // 2 - 130, 440, 300)
    pygame.draw.rect(surface, (255, 255, 255), box, border_radius=12)
    pygame.draw.rect(surface, C_BORDER, box, 1, border_radius=12)
    title = "编辑墙体" if is_wall else "编辑障碍物"
    surface.blit(FONT_LABEL.render(title, True, C_TEXT), (box.x + 20, box.y + 16))
    surface.blit(
        FONT_SMALL.render("勾选后在画布显示名称；单击选中时仍会临时显示", True, C_MUTED),
        (box.x + 20, box.y + 42),
    )
    surface.blit(FONT_SMALL.render("名称", True, C_TEXT), (box.x + 20, box.y + 72))
    obstacle_edit_name_rect = pygame.Rect(box.x + 20, box.y + 92, box.width - 40, 36)
    pygame.draw.rect(surface, (248, 250, 252), obstacle_edit_name_rect, border_radius=8)
    pygame.draw.rect(
        surface,
        C_ACCENT if obstacle_edit_focus == "name" else C_BORDER,
        obstacle_edit_name_rect,
        2 if obstacle_edit_focus == "name" else 1,
        border_radius=8,
    )
    name_text = obstacle_edit_name + (obstacle_edit_composition if obstacle_edit_focus == "name" else "")
    if obstacle_edit_focus == "name":
        name_text += "|"
    surface.blit(FONT_BODY.render(name_text, True, C_TEXT), (obstacle_edit_name_rect.x + 10, obstacle_edit_name_rect.y + 8))
    surface.blit(FONT_SMALL.render("长 (m)", True, C_TEXT), (box.x + 20, box.y + 138))
    obstacle_edit_length_rect = pygame.Rect(box.x + 20, box.y + 158, 180, 36)
    surface.blit(FONT_SMALL.render("宽 (m)", True, C_TEXT), (box.x + 220, box.y + 138))
    obstacle_edit_width_rect = pygame.Rect(box.x + 220, box.y + 158, 180, 36)
    for rect, text, focused in (
        (obstacle_edit_length_rect, obstacle_edit_length, obstacle_edit_focus == "length"),
        (obstacle_edit_width_rect, obstacle_edit_width, obstacle_edit_focus == "width"),
    ):
        pygame.draw.rect(surface, (248, 250, 252), rect, border_radius=8)
        pygame.draw.rect(surface, C_ACCENT if focused else C_BORDER, rect, 2 if focused else 1, border_radius=8)
        surface.blit(FONT_BODY.render(text + ("|" if focused else ""), True, C_TEXT), (rect.x + 10, rect.y + 8))
    label_text = "在画布显示名称"
    obstacle_edit_show_label_rect = pygame.Rect(box.x + 20, box.y + 206, 22, 22)
    draw_inline_checkbox(surface, obstacle_edit_show_label_rect, obstacle_edit_show_label, label_text)
    for btn in obstacle_edit_buttons.values():
        btn.draw(surface)


def build_wall_size_dialog_buttons():
    cx = SCREEN_WIDTH // 2
    bw, bh = 88, 34
    y = SCREEN_HEIGHT // 2 + 36
    ok_label = "确定" if wall_size_edit_index is not None else "放置"
    return {
        "ok": Button((cx - bw - 6, y, bw, bh), ok_label, "wall_ok", primary=True),
        "cancel": Button((cx + 6, y, bw, bh), "取消", "wall_cancel"),
    }


def apply_wall_obstacle():
    global editing_wall_size, wall_size_edit_index
    try:
        length_m = float(wall_length_text.strip())
        width_m = float(wall_width_text.strip())
    except ValueError:
        show_toast("请输入有效的长宽数字（米）")
        return
    if length_m <= 0 or width_m <= 0:
        show_toast("长宽必须大于 0")
        return
    if wall_size_edit_index is not None:
        push_undo()
        name = collision_polygons[wall_size_edit_index].get("name", "障碍物")
        if resize_obstacle_rect(wall_size_edit_index, length_m, width_m):
            editing_wall_size = False
            wall_size_edit_index = None
            show_toast(f"已更新 {name} 尺寸为 {length_m:g}×{width_m:g} m")
        return
    length_mm = length_m * 1000
    width_mm = width_m * 1000
    cx = store_width_mm / 2
    cy = store_height_mm / 2
    points = clip_obstacle_points(rect_points_centered(cx, cy, length_mm, width_mm))
    if len(points) < 3 or polygon_area(points) <= 1.0:
        show_toast("墙体与门店画布无有效重叠，请缩小尺寸")
        return
    push_undo()
    wall_count = sum(1 for c in collision_polygons if c.get("kind") == "wall" or str(c.get("name", "")).startswith("墙体"))
    obstacle = {
        "name": f"墙体{wall_count + 1}",
        "points": points,
        "kind": "wall",
    }
    collision_polygons.append(obstacle)
    set_obstacle_selection([len(collision_polygons) - 1])
    editing_wall_size = False
    show_toast(f"已放置墙体 {length_m:g}×{width_m:g} m，可拖动调整位置")


def cancel_wall_size_edit():
    global editing_wall_size, wall_size_edit_index
    editing_wall_size = False
    wall_size_edit_index = None


def handle_wall_size_action(action):
    if action == "wall_ok":
        apply_wall_obstacle()
    elif action == "wall_cancel":
        cancel_wall_size_edit()


def handle_wall_size_click(mx, my):
    global wall_size_focus, wall_length_text, wall_width_text
    mx, my = ui_pos((mx, my))
    if wall_length_rect and wall_length_rect.collidepoint(mx, my):
        wall_size_focus = "length"
        return True
    if wall_width_rect and wall_width_rect.collidepoint(mx, my):
        wall_size_focus = "width"
        return True
    for btn in wall_size_buttons.values():
        if btn.contains((mx, my)):
            handle_wall_size_action(btn.action)
            return True
    return False


def draw_wall_size_dialog(surface):
    global wall_length_rect, wall_width_rect
    overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    overlay.fill((15, 23, 42, 120))
    surface.blit(overlay, (0, 0))
    box = pygame.Rect(SCREEN_WIDTH // 2 - 220, SCREEN_HEIGHT // 2 - 120, 440, 240)
    pygame.draw.rect(surface, (255, 255, 255), box, border_radius=12)
    pygame.draw.rect(surface, C_BORDER, box, 1, border_radius=12)
    if wall_size_edit_index is not None:
        title = "修改障碍/墙体尺寸"
        hint = "输入新的长宽（米），中心位置不变"
    else:
        title = "添加墙体"
        hint = "输入长方形长宽（米），将放置在门店中心，可拖动调整"
    surface.blit(FONT_LABEL.render(title, True, C_TEXT), (box.x + 20, box.y + 16))
    surface.blit(FONT_SMALL.render(hint, True, C_MUTED), (box.x + 20, box.y + 44))
    surface.blit(FONT_SMALL.render("长 (m)", True, C_TEXT), (box.x + 20, box.y + 78))
    wall_length_rect = pygame.Rect(box.x + 20, box.y + 100, 180, 36)
    surface.blit(FONT_SMALL.render("宽 (m)", True, C_TEXT), (box.x + 220, box.y + 78))
    wall_width_rect = pygame.Rect(box.x + 220, box.y + 100, 180, 36)
    for rect, text, focused in (
        (wall_length_rect, wall_length_text, wall_size_focus == "length"),
        (wall_width_rect, wall_width_text, wall_size_focus == "width"),
    ):
        pygame.draw.rect(surface, (248, 250, 252), rect, border_radius=8)
        pygame.draw.rect(surface, C_ACCENT if focused else C_BORDER, rect, 2 if focused else 1, border_radius=8)
        surface.blit(FONT_BODY.render(text + ("|" if focused else ""), True, C_TEXT), (rect.x + 10, rect.y + 8))
    for btn in wall_size_buttons.values():
        btn.draw(surface)


def go_to_store_home():
    global startup_active, store_picker_active, force_rebuild_startup, editing_canvas_size, editing_wall_size
    global startup_buttons, wall_size_edit_index
    startup_active = True
    store_picker_active = False
    editing_canvas_size = False
    editing_wall_size = False
    wall_size_edit_index = None
    cancel_obstacle_edit_dialog()
    cancel_reset_confirm()
    force_rebuild_startup = False
    if current_layout_path:
        remember_store_summary(
            current_layout_path,
            width_m=store_width_mm / 1000,
            height_m=store_height_mm / 1000,
            furniture_count=len(placed_furnitures),
            obstacle_count=len(collision_polygons),
        )
    startup_buttons = build_store_catalog_ui(fast=True, cache_only=True)
    show_toast("请选择门店")
    pygame.event.post(pygame.event.Event(EVENT_HOME_DEFERRED))


def handle_home_deferred():
    if current_layout_path:
        schedule_deferred_save()
    refresh_catalog_cache_async()


def build_store_catalog_ui(*, picker_mode=False, fast=False, cache_only=False):
    cx = SCREEN_WIDTH // 2
    btn_w = 400 if picker_mode else 360
    btn_h = 44
    gap = 10
    y = 118 if picker_mode else 130
    buttons = {}
    for i, (name, slug) in enumerate(STORE_CATALOG):
        path = layout_path_for_slug(slug)
        if cache_only or fast:
            detail = catalog_detail_from_cache(path)
        else:
            info = read_store_summary(path)
            if info:
                detail = f"{info['width']:g}×{info['height']:g}m"
                if info["furniture_count"] or info["obstacle_count"]:
                    detail += f" · 家具{info['furniture_count']} 障碍{info['obstacle_count']}"
            else:
                detail = "新建 20×15m"
        mark = " ●" if picker_mode and path == current_layout_path else ""
        label = f"{name}{mark}  ({detail})"
        buttons[f"cat_{i}"] = Button(
            (cx - btn_w // 2, y, btn_w, btn_h),
            label,
            f"catalog:{slug}",
            primary=(path == current_layout_path),
        )
        y += btn_h + gap
    if picker_mode:
        buttons["picker_close"] = Button((cx - btn_w // 2, SCREEN_HEIGHT - 64, btn_w, 38), "关闭", "picker_close")
    else:
        y += 6
        buttons["custom"] = Button((cx - btn_w // 2, y, btn_w, btn_h), "其他尺寸 / 自定义门店...", "custom")
    return buttons


def build_startup_ui():
    return build_store_catalog_ui(picker_mode=False)


def draw_startup_screen(surface, buttons):
    surface.fill(C_BG)
    title = FONT_TITLE.render("选择门店", True, C_TEXT)
    surface.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 48)))
    sub = FONT_SMALL.render("单击门店进入编辑  |  返回前已自动保存", True, C_MUTED)
    surface.blit(sub, sub.get_rect(center=(SCREEN_WIDTH // 2, 82)))
    hint = FONT_BODY.render("单击门店名称进入", True, C_ACCENT)
    surface.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, 108)))
    for btn in buttons.values():
        btn.draw(surface)
    ver = FONT_MARK.render(f"v{APP_VERSION}", True, C_MUTED)
    surface.blit(ver, (SCREEN_WIDTH - ver.get_width() - 12, SCREEN_HEIGHT - ver.get_height() - 8))


def _startup_hit_button(mx, my, btn):
    return btn.rect.inflate(20, 16).collidepoint(ui_pos((mx, my)))


def handle_startup_mouseup(mx, my, buttons):
    """松开鼠标进入（常规单击操作）。"""
    for btn in buttons.values():
        if _startup_hit_button(mx, my, btn):
            handle_startup_action(btn.action)
            return True
    return False


def handle_startup_action(action):
    global startup_active, placed_furnitures, collision_polygons

    if action.startswith("catalog:"):
        flush_deferred_save(block=True)
        open_catalog_store(action.split(":", 1)[1])
        startup_active = False
        return

    if action.startswith("open:"):
        flush_deferred_save(block=True)
        path = action[5:]
        switch_store_layout(path)
        startup_active = False
        return

    if action.startswith("preset:"):
        _, w_m, h_m, short_name = action.split(":", 3)
        stores = list_store_layouts()
        name = short_name
        if any(s["name"] == name for s in stores):
            name = f"{short_name}{len(stores) + 1}"
        create_store_layout(name, float(w_m), float(h_m))
        return

    if action == "custom":
        pygame.event.pump()
        get_tk_root().update()
        result = show_store_size_dialog(title="新建门店画布")
        if not result.get("ok"):
            return
        stores = list_store_layouts()
        name = f"门店{len(stores) + 1}"
        create_store_layout(name, result["width_m"], result["height_m"])
        return

    if action == "load_file":
        pygame.event.pump()
        get_tk_root().update()
        path = filedialog.askopenfilename(
            parent=get_tk_root(),
            initialdir=LAYOUTS_DIR,
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            title="打开门店布局",
        )
        if not path:
            return
        try:
            flush_deferred_save(block=True)
            switch_store_layout(path)
            startup_active = False
        except Exception as e:
            messagebox.showerror("加载失败", str(e), parent=get_tk_root())


# ── 操作 ────────────────────────────────────────────────────
def add_furniture_to_canvas():
    global selected_furniture, selected_feature, selected_collision, selected_marker_index
    tpl = furniture_templates[selected_template_index]
    new_furn = Furniture(tpl.name, tpl.roi, [tuple(p) for p in tpl.points], product_family=tpl.product_family)
    new_furn.instance_id = _alloc_furniture_instance_id()
    wx, wy = viewport_world_center()
    find_clear_furniture_position(new_furn, wx, wy)
    push_undo()
    placed_furnitures.append(new_furn)
    selected_furniture = new_furn
    selected_feature = new_furn
    selected_marker_index = None
    clear_obstacle_selection()
    if furniture_overlaps_zone(new_furn):
        show_toast(f"已添加: {tpl.name}（在障碍区内，请拖到卖场区域）")
    else:
        show_toast(f"已添加: {tpl.name}（已放在当前视图中心，可拖动调整）")
    recompute_heatmap_metrics()
    mark_heatmap_clean()


def delete_selected():
    global selected_furniture, selected_feature, selected_marker_index
    if selected_furniture is not None:
        push_undo()
        name = selected_furniture.name
        removed_id = getattr(selected_furniture, "instance_id", "")
        placed_furnitures.remove(selected_furniture)
        if removed_id:
            for furn in placed_furnitures:
                if furn.attach_to == removed_id:
                    furn.attach_to = ""
        selected_furniture = selected_feature = None
        show_toast(f"已删除家具: {name}")
    elif selected_marker_index is not None:
        push_undo()
        marker = layout_markers[selected_marker_index]
        label = marker.get("label") or marker_default_label(marker.get("kind", "entrance"))
        layout_markers.pop(selected_marker_index)
        selected_marker_index = None
        show_toast(f"已删除图标: {label}")
    elif selected_collisions:
        push_undo()
        names = [collision_polygons[i]["name"] for i in selected_collisions]
        for i in sorted(selected_collisions, reverse=True):
            collision_polygons.pop(i)
        clear_obstacle_selection()
        if len(names) == 1:
            show_toast(f"已删除障碍物: {names[0]}")
        else:
            show_toast(f"已删除 {len(names)} 个障碍/墙体")
    else:
        show_toast("请先选中要删除的对象")


def toggle_draw_obstacle(active=None):
    global drawing_polygon, current_polygon, preview_point, editing_wall_size
    if active is None:
        drawing_polygon = not drawing_polygon
    else:
        drawing_polygon = active
    if drawing_polygon:
        editing_wall_size = False
        current_polygon = []
        preview_point = None
        show_toast("刨除障碍: 碰边即停为拐点，之后可向内/沿边/向外转 | Shift 垂直水平 | Enter 完成")
    else:
        current_polygon = []
        preview_point = None


def finish_obstacle():
    global drawing_polygon, current_polygon, preview_point, selected_collision
    snapped = [snap_world_point(x, y) for x, y in current_polygon]
    if len(snapped) >= 3:
        clipped = clip_obstacle_points(snapped)
        if len(clipped) >= 3 and polygon_area(clipped) > 1.0:
            overlaps, other_name = zone_overlaps_any(clipped)
            if overlaps:
                show_toast(f"障碍不能与「{other_name}」重叠")
            else:
                push_undo()
                collision_polygons.append({
                    "name": f"障碍物{len(collision_polygons) + 1}",
                    "points": clipped,
                })
                idx = len(collision_polygons) - 1
                set_obstacle_selection([idx])
                show_toast(f"障碍区域已刨除（0.1m 对齐，画布内 {len(clipped)} 个顶点）")
        else:
            show_toast("障碍区域与门店画布无有效重叠，请重新绘制")
    else:
        show_toast("至少需要 3 个顶点")
    current_polygon = []
    drawing_polygon = False
    preview_point = None


def rotate_selected(direction):
    """direction: -1 左转, +1 右转。支持家具、图标与障碍/墙体（含多选）。"""
    step = rotation_step_degrees() * direction
    if selected_marker_index is not None:
        push_undo()
        marker = layout_markers[selected_marker_index]
        marker["rotation"] = (marker.get("rotation", 0) + step) % 360
        kind_label = MARKER_KINDS.get(marker.get("kind"), "图标")
        show_toast(f"{kind_label} 旋转至 {marker['rotation']:.0f}°（{rotation_mode_label()}）")
        return
    if selected_feature:
        push_undo()
        selected_feature.rotate_by(step)
        show_toast(f"旋转至 {selected_feature.rotation:.0f}°（{rotation_mode_label()}）")
        return
    if selected_collisions:
        push_undo()
        all_pts = []
        for i in selected_collisions:
            all_pts.extend(collision_polygons[i]["points"])
        ox = sum(p[0] for p in all_pts) / len(all_pts)
        oy = sum(p[1] for p in all_pts) / len(all_pts)
        originals = {i: collision_polygons[i]["points"][:] for i in selected_collisions}
        trials = {}
        for i in selected_collisions:
            rotated = rotate_polygon_points(originals[i], step, (ox, oy))
            if polygon_fully_inside_store(originals[i]) and not polygon_fully_inside_store(rotated):
                show_toast("旋转后会移出门店画布")
                return
            trials[i] = rotated
        for i, pts in trials.items():
            collision_polygons[i]["points"] = [[int(round(x)), int(round(y))] for x, y in pts]
        if len(selected_collisions) == 1:
            show_toast(f"已旋转 {collision_polygons[selected_collisions[0]].get('name', '障碍物')}（{rotation_mode_label()}）")
        else:
            show_toast(f"已旋转 {len(selected_collisions)} 项（{rotation_mode_label()}）")
        return
    show_toast("请先选中家具、图标、障碍或墙体")


def build_rename_dialog_buttons():
    cx = SCREEN_WIDTH // 2
    bw, bh = 88, 34
    y = SCREEN_HEIGHT // 2 + 42
    return {
        "ok": Button((cx - bw - 6, y, bw, bh), "确定", "rename_ok", primary=True),
        "cancel": Button((cx + 6, y, bw, bh), "取消", "rename_cancel"),
    }


def cancel_rename_dialog():
    global renaming_obstacle, renaming_store, input_text, rename_collision_index, rename_composition
    renaming_obstacle = False
    renaming_store = False
    rename_collision_index = None
    input_text = ""
    rename_composition = ""
    try:
        pygame.key.stop_text_input()
    except Exception:
        pass


def _start_rename_text_input():
    global rename_composition
    rename_composition = ""
    try:
        rect = pygame.Rect(SCREEN_WIDTH // 2 - 200, SCREEN_HEIGHT // 2 + 18, 400, 36)
        pygame.key.start_text_input()
        pygame.key.set_text_input_rect(rect)
    except Exception:
        pass


def handle_rename_text_event(event):
    global input_text, rename_composition
    if not renaming_store:
        return False
    if event.type == pygame.TEXTEDITING:
        rename_composition = event.text or ""
        return True
    if event.type == pygame.TEXTINPUT:
        rename_composition = ""
        if event.text:
            input_text += event.text
        return True
    return False


def apply_rename_obstacle():
    global renaming_obstacle, input_text, rename_collision_index
    if rename_collision_index is None or rename_collision_index >= len(collision_polygons):
        cancel_rename_dialog()
        return
    name = input_text.strip()
    if not name:
        show_toast("名称不能为空")
        return
    for i, col in enumerate(collision_polygons):
        if i != rename_collision_index and col.get("name") == name:
            show_toast(f"名称「{name}」已被使用")
            return
    old_name = collision_polygons[rename_collision_index].get("name", "")
    if name != old_name:
        push_undo()
        collision_polygons[rename_collision_index]["name"] = name
    cancel_rename_dialog()
    show_toast("重命名成功")


def apply_rename_store_dialog():
    global renaming_store, input_text
    if not input_text.strip():
        show_toast("门店名称不能为空")
        return
    rename_current_store(input_text.strip())
    cancel_rename_dialog()


def handle_rename_dialog_action(action):
    if action == "rename_ok":
        apply_rename_store_dialog()
    elif action == "rename_cancel":
        cancel_rename_dialog()


def handle_rename_dialog_click(mx, my):
    global rename_input_rect
    mx, my = ui_pos((mx, my))
    if rename_input_rect and rename_input_rect.collidepoint(mx, my):
        return True
    for btn in rename_dialog_buttons.values():
        if btn.contains((mx, my)):
            handle_rename_dialog_action(btn.action)
            return True
    return False


def handle_rename_dialog_key(event):
    global input_text, rename_composition
    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
        apply_rename_store_dialog()
    elif event.key == pygame.K_ESCAPE:
        cancel_rename_dialog()
    elif event.key == pygame.K_BACKSPACE:
        _note_backspace_pressed()
        _delete_rename_char()


def start_rename_obstacle():
    start_edit_obstacle_dialog()


def start_rename_store():
    global renaming_store, renaming_obstacle, input_text, rename_collision_index, rename_dialog_buttons
    renaming_store = True
    renaming_obstacle = False
    rename_collision_index = None
    input_text = store_name
    rename_dialog_buttons = build_rename_dialog_buttons()
    _start_rename_text_input()
    show_toast("可输入中文名称，Enter 确认")


def open_store_picker():
    global store_picker_active
    store_picker_active = True


def close_store_picker():
    global store_picker_active
    store_picker_active = False


def build_store_picker_ui():
    return build_store_catalog_ui(picker_mode=True)


def draw_store_picker(surface, buttons):
    overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    overlay.fill((15, 23, 42, 170))
    surface.blit(overlay, (0, 0))
    title = FONT_TITLE.render("切换门店画布", True, (255, 255, 255))
    surface.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 72)))
    sub = FONT_SMALL.render(f"当前: {store_name}  |  切换前会自动保存", True, (203, 213, 225))
    surface.blit(sub, sub.get_rect(center=(SCREEN_WIDTH // 2, 102)))
    for btn in buttons.values():
        btn.draw(surface)


def handle_store_picker_mouseup(mx, my, buttons):
    for btn in buttons.values():
        if _startup_hit_button(mx, my, btn):
            handle_store_picker_action(btn.action)
            return True
    return False


def handle_store_picker_action(action):
    global store_picker_active, startup_active
    if action == "picker_close":
        close_store_picker()
    elif action.startswith("catalog:"):
        open_catalog_store(action.split(":", 1)[1])
        close_store_picker()


def template_families():
    families = sorted({(getattr(t, "product_family", "") or "未分类") for t in furniture_templates})
    return families


def cycle_family_filter(buttons=None):
    global template_family_filter, template_scroll_offset
    options = [""] + template_families()
    try:
        idx = options.index(template_family_filter)
    except ValueError:
        idx = 0
    template_family_filter = options[(idx + 1) % len(options)]
    template_scroll_offset = 0
    label = template_family_filter or "全部"
    show_toast(f"系列筛选: {label}")
    if buttons and "family_filter" in buttons:
        buttons["family_filter"].label = f"系列: {label}"


def filtered_templates():
    items = list(enumerate(furniture_templates))
    if template_family_filter:
        items = [
            (i, t)
            for i, t in items
            if (getattr(t, "product_family", "") or "未分类") == template_family_filter
        ]
    q = search_text.strip().lower()
    if q:
        items = [
            (i, t)
            for i, t in items
            if q in t.name.lower()
            or q in (getattr(t, "product_family", "") or "").lower()
        ]
    return items


def template_visible_count(template_list_top):
    bottom = SCREEN_HEIGHT - 112
    avail = bottom - template_list_top - 56
    return max(1, avail // TEMPLATE_ROW_H)


# ── 绘制 ────────────────────────────────────────────────────
def _grid_step(span_mm, max_lines=160):
    step = GRID_SPACING
    while span_mm > 0 and span_mm // step > max_lines:
        step *= 2
    return step


def draw_grid(surface):
    start_x = int(offset_x // GRID_SPACING * GRID_SPACING)
    end_x = int((offset_x + CANVAS_RECT.width / scale) // GRID_SPACING * GRID_SPACING + GRID_SPACING)
    start_y = int(offset_y // GRID_SPACING * GRID_SPACING)
    end_y = int((offset_y + SCREEN_HEIGHT / scale) // GRID_SPACING * GRID_SPACING + GRID_SPACING)
    x_step = _grid_step(max(GRID_SPACING, end_x - start_x))
    y_step = _grid_step(max(GRID_SPACING, end_y - start_y))
    x = start_x - (start_x % x_step)
    while x <= end_x:
        sx = world_to_screen(x, 0)[0]
        if SIDEBAR_WIDTH <= sx <= SCREEN_WIDTH:
            pygame.draw.line(surface, C_GRID, (sx, 0), (sx, SCREEN_HEIGHT))
        x += x_step
    y = start_y - (start_y % y_step)
    while y <= end_y:
        sy = world_to_screen(0, y)[1]
        if 0 <= sy <= SCREEN_HEIGHT:
            pygame.draw.line(surface, C_GRID, (SIDEBAR_WIDTH, sy), (SCREEN_WIDTH, sy))
        y += y_step


def obstacle_screen_rect(col) -> pygame.Rect:
    pts = [world_to_screen(x, y) for x, y in col["points"]]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return pygame.Rect(int(min(xs)), int(min(ys)), int(max(xs) - min(xs)), int(max(ys) - min(ys)))


def obstacle_length_mm(col) -> float:
    metrics = obstacle_rect_metrics(col["points"])
    if metrics:
        return metrics[2]
    xs = [p[0] for p in col["points"]]
    ys = [p[1] for p in col["points"]]
    return max(max(xs) - min(xs), max(ys) - min(ys))


def format_length_m(length_mm) -> str:
    meters = length_mm / 1000.0
    if abs(meters - round(meters)) < 0.05:
        return f"{round(meters):g} m"
    return f"{meters:.1f} m"


def wall_screen_length_px(col) -> float:
    return obstacle_length_mm(col) * scale


def wall_label_text(col, *, show_name=True) -> str:
    length_str = format_length_m(obstacle_length_mm(col))
    if not show_name or wall_screen_length_px(col) < WALL_LABEL_NAME_MIN_PX:
        return length_str
    name = str(col.get("name", "")).strip()
    if name.startswith("墙体"):
        name = name[2:].lstrip("-· ")
    return f"{name}\n{length_str}" if name else length_str


def obstacle_label_display_name(col) -> str:
    return str(col.get("name", "")).strip()


def should_show_obstacle_label(col, idx, selected) -> bool:
    """默认不显示名称；选中项或 user_named 标记后才在画布上显示标签。"""
    if len(selected_collisions) > 1:
        return False
    is_wall = obstacle_is_wall(col)
    if selected:
        if is_wall:
            return wall_screen_length_px(col) >= WALL_LABEL_MIN_PX
        return True
    if not col.get("user_named"):
        return False
    if is_wall:
        return wall_screen_length_px(col) >= WALL_LABEL_MIN_PX
    rect = obstacle_screen_rect(col)
    return rect.width >= LABEL_MIN_W and rect.height >= LABEL_MIN_H


def draw_furniture_metric_tag(
    surface,
    name: str,
    metric: str,
    cx: float,
    bottom_y: float,
    heat_color: tuple[int, int, int],
    *,
    selected: bool = False,
) -> pygame.Rect:
    """SKU + 坪效：底部色块标签，不压在产品图上。"""
    pad_x, pad_y = 7, 5
    name_font = FONT_LABEL if selected else FONT_SMALL
    name_surf = name_font.render(name, True, (30, 41, 59))
    metric_surf = FONT_METRIC.render(metric, True, _shade_color(heat_color, 0.22))
    inner_w = max(name_surf.get_width(), metric_surf.get_width())
    pill_w = inner_w + pad_x * 2 + 6
    pill_h = name_surf.get_height() + metric_surf.get_height() + pad_y * 2 + 3
    pill = pygame.Rect(0, 0, pill_w, pill_h)
    pill.centerx = int(cx)
    pill.bottom = int(bottom_y)
    pill.clamp_ip(CANVAS_RECT.inflate(4, 4))

    overlay = pygame.Surface((pill.width, pill.height), pygame.SRCALPHA)
    overlay.fill((255, 255, 255, 244))
    pygame.draw.rect(overlay, (*heat_color, 255), (0, 0, 5, pill.height), border_radius=6)
    surface.blit(overlay, pill.topleft)
    border_c = C_SELECTION if selected else _shade_color(heat_color, 0.38)
    pygame.draw.rect(surface, border_c, pill, 2, border_radius=6)
    tx = pill.x + pad_x + 5
    ty = pill.y + pad_y
    surface.blit(name_surf, (tx, ty))
    surface.blit(metric_surf, (tx, ty + name_surf.get_height() + 2))
    return pill


def draw_label_pill(surface, text, center, *, font=None, fg=C_TEXT, bg=(255, 255, 255, 230)):
    font = font or FONT_SMALL
    lines = text.split("\n")
    if len(lines) == 1:
        rendered = [font.render(lines[0], True, fg)]
    else:
        rendered = [font.render(line, True, fg) for line in lines]
    line_gap = 2
    total_h = sum(r.get_height() for r in rendered) + line_gap * (len(rendered) - 1)
    max_w = max(r.get_width() for r in rendered)
    cx, cy = int(center[0]), int(center[1])
    pad_x, pad_y = 5, 3
    pill = pygame.Rect(0, 0, max_w + pad_x * 2, total_h + pad_y * 2)
    pill.center = (cx, cy)
    overlay = pygame.Surface((pill.width, pill.height), pygame.SRCALPHA)
    overlay.fill(bg)
    surface.blit(overlay, pill.topleft)
    pygame.draw.rect(surface, C_BORDER, pill, 1, border_radius=4)
    y = pill.top + pad_y
    for label in rendered:
        rect = label.get_rect(midtop=(pill.centerx, y))
        surface.blit(label, rect)
        y += label.get_height() + line_gap


def draw_store_floor(surface):
    floor_pts = [world_to_screen(x, y) for x, y in store_rect_points()]
    pygame.draw.polygon(surface, C_FLOOR, floor_pts)
    pygame.draw.polygon(surface, C_WALL, floor_pts, 4)
    label = FONT_SMALL.render(
        f"{store_name}  ·  {store_width_mm / 1000:g}×{store_height_mm / 1000:g} m",
        True,
        C_WALL,
    )
    tl = world_to_screen(0, 0)
    surface.blit(label, (tl[0] + 8, tl[1] + 8))


def draw_obstacles(surface):
    for idx, col in enumerate(collision_polygons):
        pts = [world_to_screen(x, y) for x, y in col["points"]]
        selected = idx in selected_collisions
        is_wall = obstacle_is_wall(col)
        if is_wall:
            fill = (210, 218, 228) if not selected else (180, 195, 215)
            border = C_WALL
            label_color = C_WALL
        else:
            fill = C_OBSTACLE_SEL if selected else (254, 202, 202)
            border = C_DANGER if selected else (185, 28, 28)
            label_color = (127, 29, 29)
        pygame.draw.polygon(surface, fill, pts)
        pygame.draw.polygon(surface, border, pts, 3 if selected else 2)
        if should_show_obstacle_label(col, idx, selected):
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
            if is_wall:
                show_name = selected or col.get("user_named")
                label_text = wall_label_text(col, show_name=show_name)
                span_px = wall_screen_length_px(col)
                font = FONT_SMALL if span_px >= WALL_LABEL_NAME_MIN_PX else FONT_TINY
                pill_bg = (255, 255, 255, 210) if not selected else (232, 240, 255, 235)
                draw_label_pill(surface, label_text, (cx, cy), font=font, fg=label_color, bg=pill_bg)
            else:
                draw_label_pill(surface, obstacle_label_display_name(col), (cx, cy), font=FONT_BODY, fg=label_color)


def draw_selection_overlay(surface):
    draw_wall_endpoint_handles(surface)
    if len(selected_collisions) < 2:
        return
    all_pts = []
    for i in selected_collisions:
        all_pts.extend(collision_polygons[i]["points"])
    xs = [p[0] for p in all_pts]
    ys = [p[1] for p in all_pts]
    tl = world_to_screen(min(xs), min(ys))
    br = world_to_screen(max(xs), max(ys))
    rect = pygame.Rect(int(tl[0]), int(tl[1]), int(br[0] - tl[0]), int(br[1] - tl[1]))
    overlay = pygame.Surface((max(1, rect.width), max(1, rect.height)), pygame.SRCALPHA)
    overlay.fill((37, 99, 235, 28))
    surface.blit(overlay, rect.topleft)
    pygame.draw.rect(surface, C_ACCENT, rect, 2)


def draw_marquee(surface):
    if not marquee_active or marquee_start is None or marquee_current is None:
        return
    x1, y1 = marquee_start
    x2, y2 = marquee_current
    left, right = sorted([x1, x2])
    top, bottom = sorted([y1, y2])
    rect = pygame.Rect(left, top, right - left, bottom - top)
    if rect.width < 1 or rect.height < 1:
        return
    overlay = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    overlay.fill((37, 99, 235, 40))
    surface.blit(overlay, rect.topleft)
    pygame.draw.rect(surface, C_ACCENT, rect, 1)


def draw_polygon_preview(surface):
    if not drawing_polygon or not current_polygon:
        return
    screen_pts = [world_to_screen(x, y) for x, y in current_polygon]
    preview = preview_point
    if preview:
        screen_pts.append(world_to_screen(*preview))
    if len(screen_pts) >= 2:
        pygame.draw.lines(surface, C_ACCENT, False, screen_pts, 2)
    for pt in screen_pts:
        pygame.draw.circle(surface, C_ACCENT, (int(pt[0]), int(pt[1])), 5)

    for wx, wy in current_polygon:
        if point_in_store(wx, wy) or min(
            wx, wy, store_width_mm - wx, store_height_mm - wy
        ) < OBSTACLE_SNAP_MM * 2:
            sx, sy = world_to_screen(wx, wy)
            pygame.draw.circle(surface, C_DANGER, (int(sx), int(sy)), 7, 2)
            tag = FONT_SMALL.render(boundary_corner_label(wx, wy), True, C_DANGER)
            surface.blit(tag, (sx + 8, sy - 18))

    if len(current_polygon) >= 1 and preview:
        last = current_polygon[-1]
        dist_m = snap_world_mm(math.hypot(preview[0] - last[0], preview[1] - last[1])) / 1000
        if dist_m > 0:
            mid = world_to_screen((last[0] + preview[0]) / 2, (last[1] + preview[1]) / 2)
            tag = FONT_SMALL.render(f"{dist_m:.1f} m", True, C_ACCENT)
            surface.blit(tag, (mid[0] + 8, mid[1] - 10))

        if is_on_store_boundary(preview) or _points_near(preview, last):
            sx, sy = world_to_screen(*preview)
            pygame.draw.circle(surface, C_DANGER, (int(sx), int(sy)), 8)
            pygame.draw.circle(surface, (255, 255, 255), (int(sx), int(sy)), 8, 2)
            label = FONT_SMALL.render(boundary_corner_label(*preview), True, C_DANGER)
            surface.blit(label, label.get_rect(center=(sx, sy - 22)))
        else:
            for cx, cy in segment_store_boundary_crossings(last, preview):
                sx, sy = world_to_screen(cx, cy)
                pygame.draw.circle(surface, C_DANGER, (int(sx), int(sy)), 8)
                pygame.draw.circle(surface, (255, 255, 255), (int(sx), int(sy)), 8, 2)
                label = FONT_SMALL.render(boundary_corner_label(cx, cy), True, C_DANGER)
                surface.blit(label, label.get_rect(center=(sx, sy - 22)))


def draw_scale_bar(surface):
    px_per_m = scale * 1000
    if px_per_m <= 0:
        return
    candidates_m = [0.5, 1, 2, 5, 10, 20, 50, 100]
    target_px = 90
    chosen_m = 1
    bar_len = px_per_m
    best_err = float("inf")
    for m in candidates_m:
        length_px = m * px_per_m
        if 50 <= length_px <= 140:
            chosen_m, bar_len = m, length_px
            break
        err = abs(length_px - target_px)
        if err < best_err:
            best_err = err
            chosen_m, bar_len = m, length_px
    bar_len = max(20, int(round(bar_len)))
    label = f"{chosen_m:g} m"
    x0, y0 = SIDEBAR_WIDTH + 24, SCREEN_HEIGHT - 36
    pygame.draw.line(surface, C_TEXT, (x0, y0), (x0 + bar_len, y0), 3)
    pygame.draw.line(surface, C_TEXT, (x0, y0 - 4), (x0, y0 + 4), 2)
    pygame.draw.line(surface, C_TEXT, (x0 + bar_len, y0 - 4), (x0 + bar_len, y0 + 4), 2)
    surface.blit(FONT_SMALL.render(label, True, C_TEXT), (x0, y0 - 18))


def draw_heatmap_legend(surface):
    if not placed_furnitures or not sales_data_ready():
        return
    ensure_heatmap_metrics()
    bar_w, bar_h = 18, 128
    pad = 10
    box_w = 148
    box_h = bar_h + 44
    x0 = SCREEN_WIDTH - box_w - 12
    y0 = SCREEN_HEIGHT - box_h - 12
    box = pygame.Rect(x0, y0, box_w, box_h)
    overlay = pygame.Surface((box.width, box.height), pygame.SRCALPHA)
    overlay.fill((255, 255, 255, 230))
    surface.blit(overlay, box.topleft)
    pygame.draw.rect(surface, C_BORDER, box, 1, border_radius=6)
    step = heatmap_color_step
    surface.blit(FONT_MARK.render("周均 元/㎡", True, C_TEXT), (box.x + pad, box.y + 6))
    surface.blit(
        FONT_MARK.render("淡=低 · 浓=高", True, C_MUTED),
        (box.x + pad, box.y + 20),
    )
    bx = box.right - pad - bar_w
    by = box.y + 36
    checker = pygame.Surface((bar_w, bar_h), pygame.SRCALPHA)
    for y in range(bar_h):
        for x in range(bar_w):
            c = 210 if (x // 4 + y // 4) % 2 == 0 else 235
            checker.set_at((x, y), (c, c, c, 255))
    surface.blit(checker, (bx, by))
    grad = pygame.Surface((bar_w, bar_h), pygame.SRCALPHA)
    for i in range(bar_h):
        t = 1.0 - (i / max(1, bar_h - 1))
        probe = heatmap_vmin + (heatmap_vmax - heatmap_vmin) * t
        rgba = revenue_per_sqm_to_rgba(probe, heatmap_vmin, heatmap_vmax, step=step)
        pygame.draw.line(grad, rgba, (0, i), (bar_w, i))
    surface.blit(grad, (bx, by))
    pygame.draw.rect(surface, C_BORDER, pygame.Rect(bx, by, bar_w, bar_h), 1)
    high_txt = format_revenue_per_sqm(heatmap_vmax)
    low_txt = format_revenue_per_sqm(heatmap_vmin if heatmap_vmax > heatmap_vmin else 0)
    surface.blit(FONT_MARK.render("高", True, heatmap_color_for_value(heatmap_vmax)), (box.x + pad, by))
    surface.blit(FONT_MARK.render(high_txt, True, C_MUTED), (box.x + pad + 18, by))
    surface.blit(FONT_MARK.render("低", True, heatmap_color_for_value(heatmap_vmin)), (box.x + pad, by + bar_h - FONT_MARK.get_height()))
    surface.blit(
        FONT_MARK.render(low_txt, True, C_MUTED),
        (box.x + pad + 18, by + bar_h - FONT_MARK.get_height()),
    )


def draw_heatmap_week_bar(surface):
    """周次操作仅在侧栏，画布不再遮挡。"""
    global heatmap_week_bar_rects
    heatmap_week_bar_rects = {}


def handle_heatmap_week_bar_click(mx, my, buttons=None) -> bool:
    return False


def draw_banner(surface):
    if drawing_polygon:
        rect = pygame.Rect(SIDEBAR_WIDTH + 16, 12, CANVAS_RECT.width - 32, 36)
        pygame.draw.rect(surface, C_ACCENT_LIGHT, rect, border_radius=8)
        pygame.draw.rect(surface, C_ACCENT, rect, 1, border_radius=8)
        text = FONT_SMALL.render("刨除障碍 — 碰边停 | 拐点后可向内转 | Shift 水平/垂直 | Enter 完成", True, C_ACCENT)
        surface.blit(text, text.get_rect(center=rect.center))
    elif pending_bind_child is not None:
        rect = pygame.Rect(SIDEBAR_WIDTH + 16, 12, CANVAS_RECT.width - 32, 36)
        pygame.draw.rect(surface, C_SUCCESS_LIGHT, rect, border_radius=8)
        pygame.draw.rect(surface, C_SUCCESS, rect, 1, border_radius=8)
        text = FONT_SMALL.render(
            f"绑定父件：子件 {pending_bind_child.name} — 请点击父件（床架）  |  Esc 取消",
            True,
            C_SUCCESS,
        )
        surface.blit(text, text.get_rect(center=rect.center))


def draw_toast(surface):
    if pygame.time.get_ticks() > toast_until or not toast_message:
        return
    text = FONT_BODY.render(toast_message, True, (255, 255, 255))
    pad = 14
    rect = text.get_rect()
    rect.width += pad * 2
    rect.height += pad
    rect.centerx = SIDEBAR_WIDTH + CANVAS_RECT.width // 2
    rect.y = 56 if drawing_polygon else 16
    pygame.draw.rect(surface, (30, 41, 59), rect, border_radius=10)
    surface.blit(text, (rect.x + pad, rect.y + pad // 2))


def draw_rename_dialog(surface):
    global rename_input_rect
    if not renaming_store:
        rename_input_rect = None
        return
    overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    overlay.fill((15, 23, 42, 120))
    surface.blit(overlay, (0, 0))
    box = pygame.Rect(SCREEN_WIDTH // 2 - 220, SCREEN_HEIGHT // 2 - 90, 440, 170)
    pygame.draw.rect(surface, (255, 255, 255), box, border_radius=12)
    pygame.draw.rect(surface, C_BORDER, box, 1, border_radius=12)
    surface.blit(FONT_LABEL.render("重命名门店", True, C_TEXT), (box.x + 20, box.y + 16))
    surface.blit(
        FONT_SMALL.render("Enter 确认  |  Esc 取消", True, C_MUTED),
        (box.x + 20, box.y + 42),
    )
    rename_input_rect = pygame.Rect(box.x + 20, box.y + 68, box.width - 40, 36)
    pygame.draw.rect(surface, (248, 250, 252), rename_input_rect, border_radius=8)
    pygame.draw.rect(surface, C_ACCENT, rename_input_rect, 2, border_radius=8)
    surface.blit(
        FONT_BODY.render(input_text + rename_composition + "|", True, C_TEXT),
        (rename_input_rect.x + 10, rename_input_rect.y + 8),
    )
    for btn in rename_dialog_buttons.values():
        btn.draw(surface)


def build_sidebar_ui():
    pad = 16
    w = SIDEBAR_WIDTH - pad * 2
    y = 16
    buttons = {}
    input_box = InputBox((pad, 0, w, 36), placeholder="搜索家具模板...")
    y += 52

    # toolbar row 1
    bw = (w - 8) // 2
    buttons["save"] = Button((pad, y, bw, 34), "保存", "save")
    buttons["home"] = Button((pad + bw + 8, y, bw, 34), "返回门店选择", "home")
    y += 42
    buttons["rename_store"] = Button((pad, y, w, 34), "重命名门店", "rename_store")
    y += 42
    buttons["store"] = Button((pad, y, w, 34), "修改画布尺寸", "store")
    y += 42
    buttons["fit_view"] = Button((pad, y, bw, 34), "居中视图", "fit_view")
    buttons["reset_layout"] = Button((pad + bw + 8, y, bw, 34), "恢复默认", "reset_layout")
    y += 42
    buttons["obstacle"] = Button((pad, y, bw, 34), "刨除障碍", "obstacle", toggle=True)
    buttons["wall"] = Button((pad + bw + 8, y, bw, 34), "添加墙体", "wall")
    y += 42
    buttons["add_entrance"] = Button((pad, y, bw, 34), "入口", "add_entrance")
    buttons["add_stairs"] = Button((pad + bw + 8, y, bw, 34), "楼梯", "add_stairs")
    y += 42
    buttons["add_cashier"] = Button((pad, y, bw, 34), "收银台", "add_cashier")
    buttons["add_fire_exit"] = Button((pad + bw + 8, y, bw, 34), "消防出口", "add_fire_exit")
    y += 42
    buttons["merge"] = Button((pad, y, w, 34), "融合相邻", "merge")
    y += 42
    buttons["select_all"] = Button((pad, y, bw, 34), "全选", "select_all")
    buttons["group"] = Button((pad + bw + 8, y, bw, 34), "成组", "group")
    y += 42
    buttons["ungroup"] = Button((pad, y, w, 34), "解组", "ungroup")
    y += 42
    buttons["add"] = Button((pad, y, w, 40), "＋ 添加到画布", "add", primary=True)
    y += 48
    buttons["rotate_l"] = Button((pad, y, bw, 34), "左转", "rotate_l")
    buttons["rotate_r"] = Button((pad + bw + 8, y, bw, 34), "右转", "rotate_r")
    y += 42
    buttons["rotate_mode"] = Button((pad, y, w, 30), "旋转: 微调 15°", "rotate_mode", toggle=True)
    y += 38
    buttons["layer_front"] = Button((pad, y, bw, 34), "置顶", "layer_front")
    buttons["layer_back"] = Button((pad + bw + 8, y, bw, 34), "置底", "layer_back")
    y += 42
    buttons["bind_parent"] = Button((pad, y, bw, 34), "绑定父件", "bind_parent")
    buttons["unbind"] = Button((pad + bw + 8, y, bw, 34), "解绑", "unbind")
    y += 42
    buttons["roi_overlap"] = Button((pad, y, w, 30), "ROI重叠闪烁", "roi_overlap", toggle=True)
    y += 36
    buttons["week_prev"] = Button((pad, y, bw, 34), "◀ 上周", "week_prev")
    buttons["week_next"] = Button((pad + bw + 8, y, bw, 34), "下周 ▶", "week_next")
    y += 40
    buttons["week_mode"] = Button((pad, y, w - 84, 34), "单周查看", "week_mode", toggle=True)
    buttons["range_less"] = Button((pad + w - 76, y, 36, 34), "−", "range_less")
    buttons["range_more"] = Button((pad + w - 36, y, 36, 34), "+", "range_more")
    y += 40
    buttons["resize"] = Button((pad, y, w, 34), "修改尺寸", "resize")
    y += 42
    buttons["rename"] = Button((pad, y, bw, 34), "重命名", "rename")
    buttons["delete"] = Button((pad + bw + 8, y, bw, 34), "删除", "delete", danger=True)
    y += 42
    buttons["family_filter"] = Button((pad, y, w, 28), "系列: 全部", "family_filter")
    template_list_top = y + 38
    return buttons, input_box, template_list_top


def draw_sidebar(buttons, input_box, template_list_top):
    ensure_heatmap_metrics()
    global template_scroll_offset
    surface = screen
    pygame.draw.rect(surface, C_SIDEBAR, (0, 0, SIDEBAR_WIDTH, SCREEN_HEIGHT))
    pygame.draw.line(surface, C_BORDER, (SIDEBAR_WIDTH - 1, 0), (SIDEBAR_WIDTH - 1, SCREEN_HEIGHT))

    surface.blit(FONT_TITLE.render("坪效布局编辑器", True, C_TEXT), (16, 16))
    name_surf = FONT_SMALL.render(store_name, True, C_ACCENT)
    surface.blit(name_surf, (16, 40))

    input_box.rect.y = 58
    input_box.draw(surface)

    for key in (
        "save", "home", "rename_store", "store", "fit_view", "reset_layout", "obstacle", "wall",
        "add_entrance", "add_stairs", "add_cashier", "add_fire_exit", "merge",
        "select_all", "group", "ungroup", "add", "rotate_l", "rotate_r",
        "rotate_mode", "layer_front", "layer_back", "bind_parent", "unbind", "roi_overlap",
        "week_prev", "week_next", "week_mode", "range_less", "range_more",
        "resize", "rename", "delete", "family_filter",
    ):
        buttons[key].draw(surface)
    buttons["obstacle"].active = drawing_polygon
    buttons["rotate_mode"].active = rotation_mode == "90"
    buttons["rotate_mode"].label = f"旋转: {rotation_mode_label()}"
    if "roi_overlap" in buttons:
        buttons["roi_overlap"].active = show_roi_overlap_mode
    sync_heatmap_week_ui(buttons)
    if "week_prev" in buttons:
        pr = buttons["week_prev"].rect
        nr = buttons["week_next"].rect
        cap = heatmap_week_caption()
        if len(cap) > 22:
            cap = cap[:20] + "…"
        cap_surf = FONT_MARK.render(cap, True, C_ACCENT)
        gap = pygame.Rect(pr.right + 2, pr.y, nr.left - pr.right - 4, pr.height)
        surface.blit(cap_surf, cap_surf.get_rect(center=gap.center))
        pygame.draw.line(surface, C_BORDER, (12, pr.y - 8), (SIDEBAR_WIDTH - 12, pr.y - 8), 1)
        surface.blit(FONT_MARK.render("坪效周次", True, C_MUTED), (16, pr.y - 22))
    fam = template_family_filter or "全部"
    if "family_filter" in buttons:
        buttons["family_filter"].label = f"系列: {fam}"

    y = template_list_top
    surface.blit(FONT_LABEL.render("家具模板", True, C_TEXT), (16, y))
    y += 24
    filtered = filtered_templates()
    visible_n = template_visible_count(template_list_top)
    max_scroll = max(0, len(filtered) - visible_n)
    template_scroll_offset = min(template_scroll_offset, max_scroll)
    visible = filtered[template_scroll_offset : template_scroll_offset + visible_n]
    prefetch_template_list_images(visible)
    count_label = f"{len(filtered)} 项" + (f" · 显示 {template_scroll_offset + 1}-{template_scroll_offset + len(visible)}" if len(filtered) > visible_n else "")
    surface.blit(FONT_SMALL.render(count_label, True, C_MUTED), (16, y))
    y += 20
    for i, (idx, tpl) in enumerate(visible):
        row = pygame.Rect(12, y + i * TEMPLATE_ROW_H, SIDEBAR_WIDTH - 24, TEMPLATE_ROW_H - 4)
        selected = idx == selected_template_index
        bg = C_ACCENT_LIGHT if selected else (248, 250, 252)
        pygame.draw.rect(surface, bg, row, border_radius=8)
        if selected:
            pygame.draw.rect(surface, C_ACCENT, row, 2, border_radius=8)
        thumb = pygame.Rect(row.x + 6, row.centery - TEMPLATE_THUMB // 2, TEMPLATE_THUMB, TEMPLATE_THUMB)
        pygame.draw.rect(surface, (255, 255, 255), thumb, border_radius=6)
        pygame.draw.rect(surface, C_BORDER, thumb, 1, border_radius=6)
        img = furniture_image_surface(tpl.name, TEMPLATE_THUMB - 4, family=tpl.product_family)
        if img is not None:
            scaled = pygame.transform.smoothscale(img, (TEMPLATE_THUMB - 8, TEMPLATE_THUMB - 8))
            surface.blit(scaled, scaled.get_rect(center=thumb.center))
        else:
            area = polygon_area(tpl.points)
            _, rps = template_sidebar_metrics(tpl.name, tpl.product_family, area)
            color_dot = revenue_per_sqm_to_color(rps, heatmap_vmin, heatmap_vmax)
            pygame.draw.circle(surface, color_dot, thumb.center, 10)
        tx = row.x + TEMPLATE_THUMB + 10
        family = getattr(tpl, "product_family", "") or "未分类"
        area = polygon_area(tpl.points)
        _, rps = template_sidebar_metrics(tpl.name, tpl.product_family, area)
        surface.blit(FONT_BODY.render(tpl.name, True, C_TEXT), (tx, row.y + 6))
        surface.blit(
            FONT_SMALL.render(f"{family}  ·  {format_revenue_per_sqm(rps)}", True, C_MUTED),
            (tx, row.y + 26),
        )

    y = SCREEN_HEIGHT - 110
    pygame.draw.line(surface, C_BORDER, (16, y), (SIDEBAR_WIDTH - 16, y))
    y += 12
    if selected_marker_index is not None:
        marker = layout_markers[selected_marker_index]
        kind_label = MARKER_KINDS.get(marker.get("kind"), "图标")
        label = marker.get("label") or kind_label
        surface.blit(FONT_SMALL.render(f"选中图标: {label} ({kind_label})", True, C_ACCENT), (16, y))
        y += 20
        surface.blit(
            FONT_SMALL.render(
                f"旋转 {marker.get('rotation', 0):.0f}°  |  "
                f"{marker_width_mm(marker) / 1000:g}×{marker_height_mm(marker) / 1000:g} m  |  "
                f"模式 {rotation_mode_label()}",
                True,
                C_MUTED,
            ),
            (16, y),
        )
    elif selected_feature:
        surface.blit(FONT_SMALL.render(f"选中: {selected_feature.name}", True, C_ACCENT), (16, y))
        y += 20
        layer_idx = placed_furnitures.index(selected_feature) + 1 if selected_feature in placed_furnitures else 0
        parent = furniture_by_instance_id(getattr(selected_feature, "attach_to", ""))
        parent_txt = f"  |  绑定→{parent.name}" if parent else ""
        surface.blit(
            FONT_SMALL.render(
                f"旋转 {selected_feature.rotation:.0f}°  |  {format_revenue_per_sqm(selected_feature.revenue_per_sqm)}  |  层 {layer_idx}/{len(placed_furnitures)}{parent_txt}",
                True,
                C_MUTED,
            ),
            (16, y),
        )
    elif selected_collisions:
        if len(selected_collisions) == 1:
            name = collision_polygons[selected_collision]["name"]
            surface.blit(FONT_SMALL.render(f"选中障碍物: {name}", True, C_DANGER), (16, y))
        else:
            surface.blit(
                FONT_SMALL.render(f"已选 {len(selected_collisions)} 个障碍/墙体", True, C_DANGER),
                (16, y),
            )
        y += 20
        gids = sorted({
            collision_polygons[i].get("group_id")
            for i in selected_collisions
            if collision_polygons[i].get("group_id")
        })
        metrics = None
        if len(selected_collisions) == 1:
            metrics = obstacle_rect_metrics(collision_polygons[selected_collision]["points"])
        dim_text = ""
        wall_hint = ""
        if metrics:
            _, _, length_mm, width_mm = metrics
            dim_text = f"  |  {length_mm / 1000:g}×{width_mm / 1000:g} m"
            if len(selected_collisions) == 1 and obstacle_is_wall(collision_polygons[selected_collision]):
                wall_hint = "  |  拖蓝色角标调长度"
        extra = f"  |  组 {', '.join(gids)}" if gids else ""
        surface.blit(
            FONT_SMALL.render(
                f"可旋转/拖动{dim_text}{wall_hint}{extra}  |  模式 {rotation_mode_label()}",
                True,
                C_MUTED,
            ),
            (16, y),
        )
    else:
        surface.blit(FONT_SMALL.render("未选中对象", True, C_MUTED), (16, y))

    y += 28
    hints = "墙体名仅选中显示 | 可拖窗口边缘最大化 | 滚轮翻页模板"
    surface.blit(FONT_SMALL.render(hints, True, C_MUTED), (16, y))
    y += 18
    surface.blit(
        FONT_SMALL.render(
            f"{store_name}  |  {store_width_mm / 1000:g}×{store_height_mm / 1000:g} m  |  家具 {len(placed_furnitures)}  |  障碍 {len(collision_polygons)}  |  图标 {len(layout_markers)}  |  v{APP_VERSION}",
            True,
            C_MUTED,
        ),
        (16, SCREEN_HEIGHT - 24),
    )


def handle_toolbar_click(action, buttons):
    if action == "save":
        save_current_layout()
    elif action == "home":
        go_to_store_home()
    elif action == "rename_store":
        start_rename_store()
    elif action == "store":
        start_edit_canvas_size()
    elif action == "fit_view":
        fit_view_to_store()
        show_toast("视图已居中到门店")
    elif action == "reset_layout":
        reset_catalog_layout()
    elif action == "obstacle":
        toggle_draw_obstacle()
        buttons["obstacle"].active = drawing_polygon
    elif action == "wall":
        start_edit_wall_size()
    elif action == "add_entrance":
        add_marker_to_canvas("entrance")
    elif action == "add_stairs":
        add_marker_to_canvas("stairs")
    elif action == "add_cashier":
        add_marker_to_canvas("cashier")
    elif action == "add_fire_exit":
        add_marker_to_canvas("fire_exit")
    elif action == "merge":
        merge_selected_obstacle()
    elif action == "select_all":
        select_all_obstacles()
    elif action == "group":
        group_selected_obstacles()
    elif action == "ungroup":
        ungroup_selected_obstacles()
    elif action == "add":
        add_furniture_to_canvas()
    elif action == "rotate_l":
        rotate_selected(-1)
    elif action == "rotate_r":
        rotate_selected(1)
    elif action == "rotate_mode":
        toggle_rotation_mode()
    elif action == "layer_front":
        if selected_furniture is not None:
            bring_furniture_to_front(selected_furniture)
        else:
            show_toast("请先选中家具")
    elif action == "layer_back":
        if selected_furniture is not None:
            send_furniture_to_back(selected_furniture)
        else:
            show_toast("请先选中家具")
    elif action == "bind_parent":
        start_bind_to_parent()
    elif action == "unbind":
        unbind_furniture()
    elif action == "roi_overlap":
        toggle_roi_overlap_mode(buttons)
    elif action == "week_prev":
        navigate_heatmap_week(-1, buttons)
    elif action == "week_next":
        navigate_heatmap_week(1, buttons)
    elif action == "week_mode":
        toggle_heatmap_week_mode(buttons)
    elif action == "range_less":
        change_heatmap_range_weeks(-1, buttons)
    elif action == "range_more":
        change_heatmap_range_weeks(1, buttons)
    elif action == "resize":
        if selected_marker_index is not None:
            start_edit_marker_dialog(focus_size=True)
        else:
            start_edit_obstacle_size()
    elif action == "rename":
        if selected_marker_index is not None:
            start_edit_marker_dialog()
        else:
            start_rename_obstacle()
    elif action == "delete":
        delete_selected()
    elif action == "family_filter":
        cycle_family_filter(buttons)


def handle_sidebar_click(mx, my, buttons, input_box, template_list_top):
    global search_box_active, selected_template_index, template_scroll_offset

    if buttons is None or input_box is None:
        return

    mx, my = ui_pos((mx, my))

    if input_box.contains((mx, my)):
        search_box_active = True
        return
    search_box_active = False

    for btn in buttons.values():
        if btn.contains((mx, my)):
            handle_toolbar_click(btn.action, buttons)
            return

    filtered = filtered_templates()
    visible_n = template_visible_count(template_list_top)
    list_y = template_list_top + 44
    for i, (idx, tpl) in enumerate(filtered[template_scroll_offset : template_scroll_offset + visible_n]):
        row = pygame.Rect(12, list_y + i * TEMPLATE_ROW_H, SIDEBAR_WIDTH - 24, TEMPLATE_ROW_H - 4)
        if row.collidepoint(mx, my):
            selected_template_index = idx
            fam = getattr(tpl, "product_family", "") or ""
            show_toast(f"已选: {tpl.name}" + (f" ({fam})" if fam else ""))
            return


def finish_marquee_selection():
    global marquee_active, marquee_start, marquee_current
    if not marquee_active or marquee_start is None or marquee_current is None:
        marquee_active = False
        marquee_start = None
        marquee_current = None
        return
    x1, y1 = marquee_start
    x2, y2 = marquee_current
    if abs(x2 - x1) < 5 and abs(y2 - y1) < 5:
        clear_obstacle_selection()
    else:
        hits = obstacles_in_screen_rect(x1, y1, x2, y2)
        if hits:
            set_obstacle_selection(expand_group_members(hits))
        else:
            clear_obstacle_selection()
    marquee_active = False
    marquee_start = None
    marquee_current = None


def handle_canvas_click(mx, my, button, shift=False, double=False):
    global selected_furniture, selected_feature, selected_marker_index
    global dragging_furniture, dragging_collision, collision_drag_offset, collision_drag_snapshot, multi_drag_snapshots
    global current_polygon, preview_point, dragging_marker, marker_drag_offset
    global dragging_wall_endpoint, wall_endpoint_snapshot, furniture_drag_snapshot, pending_bind_child

    wx, wy = screen_to_world(mx, my)

    if button == 3:
        return "pan"

    if drawing_polygon:
        last = current_polygon[-1] if current_polygon else None
        verts = obstacle_vertices_for_click(last, wx, wy)
        append_obstacle_vertices(verts)
        preview_point = None
        return

    def try_open_marker_editor(i):
        if not double:
            return False
        start_edit_marker_dialog(i)
        return True

    def try_open_obstacle_editor(i):
        if not double:
            return False
        metrics = obstacle_rect_metrics(collision_polygons[i]["points"])
        if not metrics:
            return False
        start_edit_obstacle_dialog(i)
        return True

    def start_obstacle_drag(indices):
        global dragging_collision, collision_drag_offset, collision_drag_snapshot, multi_drag_snapshots
        indices = expand_group_members(indices)
        set_obstacle_selection(indices)
        push_undo()
        dragging_collision = True
        multi_drag_snapshots = {
            i: [tuple(p) for p in collision_polygons[i]["points"]] for i in indices
        }
        collision_drag_snapshot = multi_drag_snapshots.get(selected_collision)
        all_pts = []
        for i in indices:
            all_pts.extend(collision_polygons[i]["points"])
        cx = sum(p[0] for p in all_pts) / len(all_pts)
        cy = sum(p[1] for p in all_pts) / len(all_pts)
        collision_drag_offset = (cx - wx, cy - wy)

    def toggle_obstacle_selection(i):
        cur = set(selected_collisions)
        expanded = set(expand_group_members([i]))
        if expanded <= cur:
            cur -= expanded
        else:
            cur |= expanded
        set_obstacle_selection(cur)

    for i in reversed(range(len(layout_markers))):
        if marker_hit_test(mx, my, layout_markers[i]):
            if try_open_marker_editor(i):
                return
            set_marker_selection(i)
            push_undo()
            dragging_marker = True
            marker = layout_markers[i]
            marker_drag_offset = (marker["x_mm"] - wx, marker["y_mm"] - wy)
            return

    for i in reversed(range(len(collision_polygons))):
        if not obstacle_is_wall(collision_polygons[i]):
            continue
        end_hit = wall_endpoint_hit_test(mx, my, i)
        if end_hit is not None:
            set_obstacle_selection([i])
            push_undo()
            dragging_wall_endpoint = (i, end_hit)
            wall_endpoint_snapshot = [list(p) for p in collision_polygons[i]["points"]]
            return

    for i in reversed(range(len(collision_polygons))):
        col = collision_polygons[i]
        if obstacle_label_rect(col).collidepoint(mx, my):
            if try_open_obstacle_editor(i):
                return
            if shift:
                toggle_obstacle_selection(i)
            else:
                start_obstacle_drag([i])
            return

    for f in reversed(placed_furnitures):
        if f.is_label_clicked(mx, my) or f.is_clicked(mx, my):
            if pending_bind_child is not None:
                complete_bind_to_parent(f)
                return
            dragging_furniture = f
            f.dragging = True
            selected_furniture = f
            selected_feature = f
            selected_marker_index = None
            clear_obstacle_selection()
            furniture_drag_snapshot = {
                item.instance_id: (item.x, item.y)
                for item in furniture_drag_pack(f)
            }
            return

    for i, col in enumerate(collision_polygons):
        if point_in_poly(wx, wy, col["points"]):
            if try_open_obstacle_editor(i):
                return
            if shift:
                toggle_obstacle_selection(i)
            else:
                start_obstacle_drag([i])
            return

    selected_furniture = selected_feature = None
    selected_marker_index = None
    return "marquee"


def main():
    global offset_x, offset_y, scale, dragging_view, last_mouse_pos
    global drawing_polygon, current_polygon, preview_point
    global selected_collision, selected_collisions, selected_furniture, dragging_furniture, selected_feature
    global placed_furnitures, collision_polygons, selected_template_index, dragging_collision, collision_drag_offset
    global renaming_obstacle, renaming_store, input_text, search_text, search_box_active, mouse_pos
    global furniture_templates, startup_active, store_picker_active
    global editing_canvas_size, canvas_w_text, canvas_h_text, canvas_size_focus, force_rebuild_startup
    global editing_wall_size, wall_length_text, wall_width_text, wall_size_focus
    global editing_obstacle_dialog, obstacle_edit_name, obstacle_edit_length, obstacle_edit_width, obstacle_edit_focus
    global canvas_last_click_time, canvas_last_click_pos, pending_reset_confirm
    global startup_buttons, _catalog_refresh_ready, collision_drag_snapshot, multi_drag_snapshots
    global active_alignment_guides
    global marquee_active, marquee_start, marquee_current, template_scroll_offset, template_family_filter
    global layout_markers, selected_marker_index, dragging_marker, marker_drag_offset
    global editing_marker_dialog, marker_edit_name, marker_edit_focus
    global marker_edit_length, marker_edit_width
    global dragging_wall_endpoint, wall_endpoint_snapshot

    try:
        furniture_templates = load_furniture_templates("furniture_templates.json")
    except Exception as e:
        messagebox.showerror("启动失败", f"无法加载家具模板:\n{e}\n\n当前目录:\n{os.getcwd()}")
        raise SystemExit(1) from e

    ensure_layouts_dir()
    init_display()
    print("坪效布局编辑器已启动。")
    refresh_catalog_cache_async()

    last_path = load_last_store_path()
    if last_path:
        try:
            switch_store_layout(last_path)
            startup_active = False
            print(f"已打开上次门店: {store_name}")
        except Exception as e:
            print(f"打开上次门店失败: {e}")
            startup_active = True
    else:
        startup_active = True
        print("请选择门店。")

    startup_buttons = build_store_catalog_ui(fast=True, cache_only=True) if startup_active else None
    store_picker_buttons = None
    editor_buttons, input_box, template_list_top = (None, None, 0)
    if not startup_active:
        editor_buttons, input_box, template_list_top = build_sidebar_ui()
    running = True

    while running:
        mouse_pos = pygame.mouse.get_pos()
        if not startup_active and editor_buttons is None:
            editor_buttons, input_box, template_list_top = build_sidebar_ui()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                if current_layout_path and not startup_active:
                    save_layout(current_layout_path, quiet=True)
                running = False
                continue

            if event.type == pygame.VIDEORESIZE and not startup_active:
                handle_window_resize(event.w, event.h)
                continue

            if event.type == EVENT_HOME_DEFERRED:
                handle_home_deferred()
                continue

            if store_picker_active:
                if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    handle_store_picker_mouseup(*event.pos, store_picker_buttons)
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    close_store_picker()
                continue

            if pending_reset_confirm and not startup_active:
                if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    handle_reset_confirm_click(*event.pos)
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        cancel_reset_confirm()
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        apply_reset_catalog_layout()
                continue

            if editing_obstacle_dialog and not startup_active:
                if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    handle_obstacle_edit_dialog_click(*event.pos)
                elif event.type in (pygame.TEXTINPUT, pygame.TEXTEDITING):
                    handle_obstacle_edit_text_event(event)
                elif event.type == pygame.KEYDOWN:
                    handle_obstacle_edit_dialog_key(event)
                continue

            if editing_marker_dialog and not startup_active:
                if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    handle_marker_edit_dialog_click(*event.pos)
                elif event.type in (pygame.TEXTINPUT, pygame.TEXTEDITING):
                    handle_marker_edit_text_event(event)
                elif event.type == pygame.KEYDOWN:
                    handle_marker_edit_dialog_key(event)
                continue

            if editing_wall_size and not startup_active:
                if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    handle_wall_size_click(*event.pos)
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        cancel_wall_size_edit()
                    elif event.key == pygame.K_TAB:
                        wall_size_focus = "width" if wall_size_focus == "length" else "length"
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        apply_wall_obstacle()
                    elif event.key == pygame.K_BACKSPACE:
                        if wall_size_focus == "length":
                            wall_length_text = wall_length_text[:-1]
                        else:
                            wall_width_text = wall_width_text[:-1]
                    elif event.unicode:
                        field = wall_length_text if wall_size_focus == "length" else wall_width_text
                        ch = event.unicode
                        if ch.isdigit() and len(field) < 5:
                            if wall_size_focus == "length":
                                wall_length_text += ch
                            else:
                                wall_width_text += ch
                        elif ch == "." and "." not in field and len(field) < 5:
                            if wall_size_focus == "length":
                                wall_length_text += ch
                            else:
                                wall_width_text += ch
                continue

            if editing_canvas_size and not startup_active:
                if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    handle_canvas_size_click(*event.pos)
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        cancel_canvas_size_edit()
                    elif event.key == pygame.K_TAB:
                        canvas_size_focus = "height" if canvas_size_focus == "width" else "width"
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        apply_canvas_size()
                    elif event.key == pygame.K_BACKSPACE:
                        if canvas_size_focus == "width":
                            canvas_w_text = canvas_w_text[:-1]
                        else:
                            canvas_h_text = canvas_h_text[:-1]
                    elif event.unicode:
                        field = canvas_w_text if canvas_size_focus == "width" else canvas_h_text
                        ch = event.unicode
                        if ch.isdigit() and len(field) < 5:
                            if canvas_size_focus == "width":
                                canvas_w_text += ch
                            else:
                                canvas_h_text += ch
                        elif ch == "." and "." not in field and len(field) < 5:
                            if canvas_size_focus == "width":
                                canvas_w_text += ch
                            else:
                                canvas_h_text += ch
                continue

            if renaming_store and not startup_active:
                if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    handle_rename_dialog_click(*event.pos)
                elif event.type in (pygame.TEXTINPUT, pygame.TEXTEDITING):
                    handle_rename_text_event(event)
                elif event.type == pygame.KEYDOWN:
                    handle_rename_dialog_key(event)
                continue

            if startup_active:
                if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    handle_startup_mouseup(*event.pos, startup_buttons)
                continue

            if event.type == pygame.MOUSEWHEEL:
                mx, my = mouse_pos
                if mx < SIDEBAR_WIDTH and not startup_active and template_list_top:
                    filtered = filtered_templates()
                    visible_n = template_visible_count(template_list_top)
                    max_scroll = max(0, len(filtered) - visible_n)
                    template_scroll_offset = max(0, min(max_scroll, template_scroll_offset - event.y))
                else:
                    wx, wy = screen_to_world(mx, my)
                    scale = max(MIN_SCALE, min(MAX_SCALE, scale * (ZOOM_IN if event.y > 0 else ZOOM_OUT)))
                    offset_x = wx - (mx - SIDEBAR_WIDTH) / scale
                    offset_y = wy - my / scale

            elif event.type in (pygame.TEXTINPUT, pygame.TEXTEDITING):
                if search_box_active and event.type == pygame.TEXTINPUT and event.text:
                    search_text += event.text
                    template_scroll_offset = 0

            elif event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = ui_pos(event.pos)
                if mx < SIDEBAR_WIDTH and event.button == 1 and editor_buttons:
                    home_btn = editor_buttons.get("home")
                    if home_btn and home_btn.contains((mx, my)):
                        go_to_store_home()
                        continue
                if mx >= SIDEBAR_WIDTH and event.button == 1:
                    mods = pygame.key.get_mods()
                    shift = bool(mods & pygame.KMOD_SHIFT)
                    is_double = False
                    now = pygame.time.get_ticks()
                    if (
                        canvas_last_click_pos is not None
                        and abs(mx - canvas_last_click_pos[0]) < 10
                        and abs(my - canvas_last_click_pos[1]) < 10
                        and now - canvas_last_click_time < DOUBLE_CLICK_MS
                    ):
                        is_double = True
                    canvas_last_click_time = now
                    canvas_last_click_pos = (mx, my)
                    result = handle_canvas_click(mx, my, event.button, shift=shift, double=is_double)
                    if result == "pan":
                        dragging_view = True
                        last_mouse_pos = event.pos
                    elif result == "marquee":
                        marquee_active = True
                        marquee_start = (mx, my)
                        marquee_current = (mx, my)
                elif event.button == 3:
                    dragging_view = True
                    last_mouse_pos = event.pos

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    mx, my = ui_pos(event.pos)
                    if marquee_active:
                        marquee_current = (mx, my)
                        finish_marquee_selection()
                    elif mx >= SIDEBAR_WIDTH and handle_heatmap_week_bar_click(event.pos[0], event.pos[1], editor_buttons):
                        pass
                    elif mx < SIDEBAR_WIDTH:
                        home_btn = editor_buttons.get("home") if editor_buttons else None
                        if home_btn and home_btn.contains((mx, my)):
                            pass
                        else:
                            handle_sidebar_click(mx, my, editor_buttons, input_box, template_list_top)
                if event.button in (1, 3):
                    dragging_view = False
                if event.button == 1:
                    if dragging_furniture:
                        dragging_furniture.dragging = False
                        dragging_furniture = None
                    furniture_drag_snapshot = {}
                    if dragging_marker and selected_marker_index is not None:
                        marker = layout_markers[selected_marker_index]
                        marker["x_mm"], marker["y_mm"] = snap_world_point(
                            marker["x_mm"], marker["y_mm"]
                        )
                        dragging_marker = False
                    if dragging_wall_endpoint is not None and wall_endpoint_snapshot is not None:
                        idx, end_idx = dragging_wall_endpoint
                        wx, wy = screen_to_world(*ui_pos(event.pos))
                        collision_polygons[idx]["points"] = [list(p) for p in wall_endpoint_snapshot]
                        if not resize_wall_by_endpoint(idx, end_idx, wx, wy):
                            collision_polygons[idx]["points"] = [list(p) for p in wall_endpoint_snapshot]
                            show_toast("墙段长度无效或超出画布")
                        dragging_wall_endpoint = None
                        wall_endpoint_snapshot = None
                    if selected_collisions and not drawing_polygon and dragging_collision and multi_drag_snapshots:
                        reverted = False
                        for i in selected_collisions:
                            snap = multi_drag_snapshots.get(i)
                            if (
                                snap
                                and polygon_fully_inside_store(snap)
                                and not polygon_fully_inside_store(collision_polygons[i]["points"])
                            ):
                                for j, pts in multi_drag_snapshots.items():
                                    collision_polygons[j]["points"] = [list(p) for p in pts]
                                show_toast("障碍不能移出门店画布")
                                reverted = True
                                break
                        if not reverted and batch_has_zone_overlap(selected_collisions):
                            for j, pts in multi_drag_snapshots.items():
                                collision_polygons[j]["points"] = [list(p) for p in pts]
                            show_toast("障碍区域之间不能重叠，已恢复位置")
                            reverted = True
                        if (
                            not reverted
                            and len(selected_collisions) == 1
                            and obstacle_is_wall(collision_polygons[selected_collision])
                        ):
                            partner, _ = find_merge_partner(selected_collision)
                            if partner >= 0:
                                show_toast("墙段已对齐，可点「融合相邻」合并为一整段")
                    active_alignment_guides = []
                    dragging_collision = False
                    collision_drag_snapshot = None
                    multi_drag_snapshots = {}

            elif event.type == pygame.MOUSEMOTION:
                mx, my = ui_pos(event.pos)
                wx, wy = screen_to_world(mx, my)
                if dragging_view:
                    offset_x += (last_mouse_pos[0] - mx) / scale
                    offset_y += (last_mouse_pos[1] - my) / scale
                    last_mouse_pos = (mx, my)
                elif marquee_active:
                    marquee_current = (mx, my)
                elif dragging_furniture and dragging_furniture.dragging:
                    old_x, old_y = dragging_furniture.x, dragging_furniture.y
                    dragging_furniture.x, dragging_furniture.y = wx, wy
                    dx, dy = dragging_furniture.x - old_x, dragging_furniture.y - old_y
                    for child in furniture_attached_descendants(dragging_furniture):
                        child.x += dx
                        child.y += dy
                    if check_collision(dragging_furniture, collision_polygons):
                        for iid, (ox, oy) in furniture_drag_snapshot.items():
                            item = furniture_by_instance_id(iid)
                            if item is not None:
                                item.x, item.y = ox, oy
                elif dragging_marker and selected_marker_index is not None:
                    marker = layout_markers[selected_marker_index]
                    marker["x_mm"] = int(round(wx + marker_drag_offset[0]))
                    marker["y_mm"] = int(round(wy + marker_drag_offset[1]))
                elif dragging_wall_endpoint is not None and wall_endpoint_snapshot is not None:
                    idx, end_idx = dragging_wall_endpoint
                    collision_polygons[idx]["points"] = [list(p) for p in wall_endpoint_snapshot]
                    resize_wall_by_endpoint(idx, end_idx, wx, wy)
                elif dragging_collision and selected_collisions:
                    all_pts = []
                    for i in selected_collisions:
                        all_pts.extend(collision_polygons[i]["points"])
                    cx = sum(p[0] for p in all_pts) / len(all_pts)
                    cy = sum(p[1] for p in all_pts) / len(all_pts)
                    ncx = wx + collision_drag_offset[0]
                    ncy = wy + collision_drag_offset[1]
                    dx, dy = ncx - cx, ncy - cy
                    try_move_obstacles_batch(selected_collisions, dx, dy)
                elif drawing_polygon:
                    last = current_polygon[-1] if current_polygon else None
                    preview_point = obstacle_draw_target(last, wx, wy)
                else:
                    preview_point = None

            elif event.type == pygame.KEYDOWN:
                if search_box_active:
                    if event.key == pygame.K_BACKSPACE:
                        search_text = search_text[:-1]
                        template_scroll_offset = 0
                    elif event.key == pygame.K_ESCAPE:
                        search_box_active = False
                elif drawing_polygon:
                    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        finish_obstacle()
                        editor_buttons["obstacle"].active = False
                    elif event.key == pygame.K_ESCAPE:
                        toggle_draw_obstacle(False)
                        editor_buttons["obstacle"].active = False
                else:
                    if event.key == pygame.K_ESCAPE and pending_bind_child is not None:
                        cancel_bind_to_parent()
                        show_toast("已取消绑定")
                        continue
                    mods = pygame.key.get_mods()
                    if not search_box_active and not renaming_store and not editing_obstacle_dialog and not editing_marker_dialog:
                        if event.key == pygame.K_z and mods & pygame.KMOD_CTRL:
                            undo_layout()
                            continue
                        if event.key == pygame.K_a and mods & pygame.KMOD_CTRL:
                            select_all_obstacles()
                            continue
                        if event.key == pygame.K_g and mods & pygame.KMOD_CTRL:
                            if mods & pygame.KMOD_SHIFT:
                                ungroup_selected_obstacles()
                            else:
                                group_selected_obstacles()
                            continue
                        if event.key == pygame.K_c and mods & pygame.KMOD_CTRL:
                            copy_selected_obstacle()
                            continue
                        if event.key == pygame.K_v and mods & pygame.KMOD_CTRL:
                            paste_obstacle()
                            continue
                    if event.key in (pygame.K_DELETE, pygame.K_BACKSPACE):
                        delete_selected()
                    elif event.key == pygame.K_s and mods & pygame.KMOD_CTRL:
                        popup_save_dialog()
                    elif event.key == pygame.K_o and mods & pygame.KMOD_CTRL:
                        popup_load_dialog()
                    elif event.key in (pygame.K_LEFT, pygame.K_q):
                        rotate_selected(-1)
                    elif event.key in (pygame.K_RIGHT, pygame.K_e):
                        rotate_selected(1)
                    elif event.key == pygame.K_p:
                        toggle_draw_obstacle()
                        editor_buttons["obstacle"].active = drawing_polygon

        if startup_active:
            if force_rebuild_startup or startup_buttons is None:
                startup_buttons = build_store_catalog_ui(fast=True, cache_only=True)
                force_rebuild_startup = False
                editor_buttons = None
            draw_startup_screen(screen, startup_buttons)
        else:
            if editor_buttons is None:
                editor_buttons, input_box, template_list_top = build_sidebar_ui()
            screen.fill(C_OUTSIDE)
            pygame.draw.rect(screen, C_OUTSIDE, CANVAS_RECT)
            draw_grid(screen)
            draw_store_floor(screen)
            draw_obstacles(screen)
            draw_layout_markers(screen)
            draw_alignment_guides(screen)
            if sales_data_ready() and placed_furnitures:
                ensure_heatmap_metrics()
            for f in furniture_draw_order():
                if f is not selected_furniture:
                    f.draw(screen, selected=False)
            if selected_furniture is not None:
                selected_furniture.draw(screen, selected=True)
            draw_furniture_roi_overlaps(screen)
            prefetch_furniture_images()
            draw_selection_overlay(screen)
            draw_marquee(screen)
            draw_polygon_preview(screen)
            draw_scale_bar(screen)
            draw_heatmap_legend(screen)
            draw_heatmap_week_bar(screen)
            draw_banner(screen)
            draw_sidebar(editor_buttons, input_box, template_list_top)
            draw_toast(screen)
            if store_picker_active:
                if store_picker_buttons is None:
                    store_picker_buttons = build_store_picker_ui()
                draw_store_picker(screen, store_picker_buttons)
            else:
                store_picker_buttons = None
            if pending_reset_confirm:
                draw_reset_confirm_dialog(screen)
            if renaming_store:
                draw_rename_dialog(screen)
            if editing_obstacle_dialog:
                draw_obstacle_edit_dialog(screen)
            if editing_marker_dialog:
                draw_marker_edit_dialog(screen)
            if editing_canvas_size:
                draw_canvas_size_dialog(screen)
            if editing_wall_size:
                draw_wall_size_dialog(screen)
        pygame.display.flip()
        flush_deferred_save()
        if startup_active and _catalog_refresh_ready:
            _catalog_refresh_ready = False
            startup_buttons = build_store_catalog_ui(fast=True, cache_only=True)
        clock.tick(60)
        poll_dialog_backspace_repeat()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("\n程序启动失败:")
        traceback.print_exc()
        try:
            messagebox.showerror("启动失败", f"{exc}\n\n请运行 python check_env.py 检查环境")
        except Exception:
            pass
        if sys.platform == "win32":
            input("\n按 Enter 退出...")
        raise SystemExit(1) from exc
