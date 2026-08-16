try:
    import pygame
except ModuleNotFoundError:
    print("未找到 pygame。Python 3.14 请安装: python -m pip install pygame-ce")
    raise SystemExit(1) from None

import json
import math
import os
import re
import sys
import threading
import time
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox

from roi_lookup import lookup_roi

# 无论从哪启动，都切换到脚本所在目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

os.environ.setdefault("SDL_VIDEO_CENTERED", "1")
if sys.platform == "win32":
    os.environ.setdefault("SDL_WINDOWS_DPI_AWARENESS", "permonitorv2")

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
LEGACY_LAYOUT_FILE = os.path.join(SCRIPT_DIR, "saved_layout.json")
LAST_STORE_FILE = os.path.join(LAYOUTS_DIR, "_last.json")
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
APP_VERSION = "1.6.0"
OBSTACLE_SNAP_MM = 100  # 0.1 m grid for obstacle vertices
LABEL_HIT_PAD = 18  # 屏幕像素：点文字即可选中
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
FONT_LABEL = load_font(14, bold=True)
FONT_MARK = load_font(12)

screen = None
clock = None


def init_display():
    global screen, clock
    if screen is not None:
        return
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("坪效布局编辑器")
    clock = pygame.time.Clock()
    pygame.mouse.set_visible(True)
    pygame.event.set_grab(False)
    pygame.event.clear()


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
collision_polygons = []
selected_furniture = None
dragging_furniture = None
selected_feature = None
placed_furnitures = []
renaming_obstacle = False
input_text = ""
selected_template_index = 0
dragging_collision = False
collision_drag_offset = (0, 0)
collision_drag_snapshot = None
_last_furniture_pick = {"name": None, "time": 0}
product_preview = None  # {"name", "url", "opened_at"}
_display_items_cache = None
search_text = ""
search_box_active = False
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
force_rebuild_startup = False
_store_summary_cache = {}
_pending_save_snapshot = None
_save_thread = None
_save_generation = 0
_catalog_refresh_thread = None
_catalog_refresh_ready = False


def show_toast(msg, duration_ms=2500):
    global toast_message, toast_until
    toast_message = msg
    toast_until = pygame.time.get_ticks() + duration_ms
    print(msg)


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


def rect_points_centered(cx, cy, length_mm, width_mm):
    hl, hw = length_mm / 2.0, width_mm / 2.0
    return [
        (cx - hl, cy - hw),
        (cx + hl, cy - hw),
        (cx + hl, cy + hw),
        (cx - hl, cy + hw),
    ]


def roi_to_color(roi):
    roi = max(0, min(10, roi))
    start, end = (173, 216, 230), (178, 34, 34)
    t = roi / 10
    return tuple(int(start[i] + t * (end[i] - start[i])) for i in range(3))


def shape_to_points(item):
    shape_type = item.get("type", "")
    if shape_type == "polygon":
        return [tuple(p) for p in item.get("points", [])]
    if shape_type == "rectangle":
        w, h = item.get("width", 0), item.get("height", 0)
        return [(0, 0), (w, 0), (w, h), (0, h)]
    if shape_type == "circle":
        r = item.get("radius", 0)
        return [(r * math.cos(2 * math.pi * i / 24), r * math.sin(2 * math.pi * i / 24)) for i in range(24)]
    if shape_type == "l_shape":
        w, h = item.get("width", 0), item.get("height", 0)
        cw, ch = item.get("cut_width", 0), item.get("cut_height", 0)
        return [(0, 0), (w, 0), (w, ch), (cw, ch), (cw, h), (0, h)]
    return []


# ── 家具 ────────────────────────────────────────────────────
class Furniture:
    def __init__(self, name, roi, points, x=0, y=0, rotation=0):
        self.name = name
        self.roi = roi
        self.points = points
        self.x = x
        self.y = y
        self.rotation = rotation
        self.dragging = False

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
        pts = [world_to_screen(x, y) for x, y in self.get_rotated_points()]
        fill = roi_to_color(self.roi)
        pygame.draw.polygon(surface, fill, pts)
        border_w = 3 if selected else 2
        border_c = C_SELECTION if selected else (30, 41, 59)
        pygame.draw.polygon(surface, border_c, pts, border_w)
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        name_surf = FONT_MARK.render(self.name, True, C_TEXT)
        roi_surf = FONT_MARK.render(f"ROI {self.roi:.1f}", True, C_MUTED)
        name_rect = name_surf.get_rect(midbottom=(cx, cy - 2))
        roi_rect = roi_surf.get_rect(midtop=(cx, cy + 2))
        surface.blit(name_surf, name_rect)
        surface.blit(roi_surf, roi_rect)
        self._label_rect = name_rect.union(roi_rect).inflate(LABEL_HIT_PAD * 2, LABEL_HIT_PAD * 2)

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


def _shrink_polygon(points, factor=0.985):
    if len(points) < 3:
        return points
    cx = sum(p[0] for p in points) / len(points)
    cy = sum(p[1] for p in points) / len(points)
    return [(cx + (x - cx) * factor, cy + (y - cy) * factor) for x, y in points]


def polygons_interior_overlap(poly_a, poly_b):
    """仅检测面积重叠，贴边相邻不算重叠。"""
    return polygons_overlap(_shrink_polygon(poly_a), _shrink_polygon(poly_b))


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


def _edge_is_axis_aligned(p1, p2, tol=5):
    return abs(p1[0] - p2[0]) <= tol or abs(p1[1] - p2[1]) <= tol


def is_orthogonal_polygon(points, tol=5):
    if len(points) < 3:
        return False
    for p1, p2 in _polygon_edges(points):
        if not _edge_is_axis_aligned(p1, p2, tol):
            return False
    return True


def _undirected_edge_key(p1, p2):
    a = _snap_vertex(p1)
    b = _snap_vertex(p2)
    return (a, b) if a <= b else (b, a)


def _segment_overlap_on_axis(p1, p2, q1, q2, tol=OBSTACLE_SNAP_MM):
    if abs(p1[1] - p2[1]) <= tol and abs(q1[1] - q2[1]) <= tol and abs(p1[1] - q1[1]) <= tol:
        lo1, hi1 = sorted([p1[0], p2[0]])
        lo2, hi2 = sorted([q1[0], q2[0]])
        overlap = min(hi1, hi2) - max(lo1, lo2)
        return max(0.0, overlap)
    if abs(p1[0] - p2[0]) <= tol and abs(q1[0] - q2[0]) <= tol and abs(p1[0] - q1[0]) <= tol:
        lo1, hi1 = sorted([p1[1], p2[1]])
        lo2, hi2 = sorted([q1[1], q2[1]])
        overlap = min(hi1, hi2) - max(lo1, lo2)
        return max(0.0, overlap)
    return 0.0


def shared_edge_length(poly_a, poly_b):
    total = 0.0
    for a1, a2 in _polygon_edges(poly_a):
        for b1, b2 in _polygon_edges(poly_b):
            total += _segment_overlap_on_axis(a1, a2, b1, b2)
    return total


def union_orthogonal_polygons(poly_a, poly_b):
    edges = []
    for poly in (poly_a, poly_b):
        n = len(poly)
        for i in range(n):
            p1 = _snap_vertex(poly[i])
            p2 = _snap_vertex(poly[(i + 1) % n])
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
    adj = {}
    for p1, p2 in outer:
        adj.setdefault(p1, []).append(p2)
        adj.setdefault(p2, []).append(p1)
    start = outer[0][0]
    path = [start]
    prev = None
    cur = start
    for _ in range(len(outer) + 8):
        nbrs = [n for n in adj.get(cur, []) if n != prev]
        if not nbrs:
            break
        nxt = nbrs[0]
        if nxt == start and len(path) >= 3:
            break
        path.append(nxt)
        prev, cur = cur, nxt
    if len(path) < 3:
        return None
    clipped = clip_obstacle_points(path)
    return clipped if len(clipped) >= 3 and polygon_area(clipped) > 1.0 else None


def find_merge_partner(idx):
    poly = collision_polygons[idx]["points"]
    best_j = -1
    best_len = OBSTACLE_SNAP_MM
    for j, col in enumerate(collision_polygons):
        if j == idx:
            continue
        other = col["points"]
        if polygons_interior_overlap(poly, other):
            continue
        shared = shared_edge_length(poly, other)
        if shared > best_len:
            best_len = shared
            best_j = j
    return best_j, best_len


def merge_selected_obstacle():
    global selected_collision
    if selected_collision is None:
        show_toast("请先选中要融合的障碍或墙体")
        return
    idx = selected_collision
    poly = collision_polygons[idx]["points"]
    if not is_orthogonal_polygon(poly):
        show_toast("仅支持直角多边形的融合（墙体或正交障碍）")
        return
    partner, shared = find_merge_partner(idx)
    if partner < 0:
        show_toast("未找到可贴边融合的相邻障碍/墙体")
        return
    other = collision_polygons[partner]["points"]
    if not is_orthogonal_polygon(other):
        show_toast("相邻对象不是直角多边形，无法融合")
        return
    merged = union_orthogonal_polygons(poly, other)
    if not merged:
        show_toast("融合失败，请确认两边贴边且无重叠")
        return
    overlaps, other_name = obstacle_overlaps_any(merged, idx, partner)
    if overlaps:
        show_toast(f"融合后会与「{other_name}」重叠，已取消")
        return
    base = collision_polygons[idx]
    partner_name = collision_polygons[partner]["name"]
    is_wall = base.get("kind") == "wall" or str(base.get("name", "")).startswith("墙体")
    partner_wall = collision_polygons[partner].get("kind") == "wall" or str(
        collision_polygons[partner].get("name", "")
    ).startswith("墙体")
    new_name = base["name"]
    if partner_wall and not is_wall:
        new_name = partner_name
    for remove_idx in sorted((idx, partner), reverse=True):
        collision_polygons.pop(remove_idx)
    entry = {"name": new_name, "points": merged}
    if is_wall or partner_wall:
        entry["kind"] = "wall"
    collision_polygons.append(entry)
    selected_collision = len(collision_polygons) - 1
    show_toast(f"已融合为 {new_name}（{len(merged)} 个顶点）")


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


def open_product_preview(name: str):
    global product_preview
    url = image_url_for_product(name)
    if not url:
        show_toast(f"未找到 {name} 的产品图（请先 grab_display）")
        return
    product_preview = {"name": name, "url": url, "opened_at": pygame.time.get_ticks()}
    try:
        from product_images import request_image

        request_image(url, max_size=(480, 360))
    except Exception:
        pass
    show_toast(f"加载产品图: {name}")


def close_product_preview():
    global product_preview
    product_preview = None


def check_collision(furniture, obstacles):
    store_poly = store_rect_points()
    furn_pts = furniture.get_rotated_points()
    for px, py in furn_pts:
        if not point_in_poly(px, py, store_poly):
            return True
    for col in obstacles:
        if polygons_overlap(furn_pts, col["points"]):
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
            roi = item.get("roi", 0) or lookup_roi(family)
            templates.append(Furniture(item.get("id", "unnamed"), roi, points))
    if not templates:
        raise ValueError(f"{json_path} 中没有有效的家具模板")
    return templates


furniture_templates = []


# ── 数据持久化 ──────────────────────────────────────────────
def ensure_layouts_dir():
    os.makedirs(LAYOUTS_DIR, exist_ok=True)


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
            {"name": f.name, "roi": f.roi, "x": f.x, "y": f.y, "rotation": f.rotation, "points": f.points}
            for f in placed_furnitures
        ],
        "obstacles": collision_polygons,
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


def load_layout(filepath):
    global placed_furnitures, collision_polygons, store_width_mm, store_height_mm
    global store_name, current_layout_path
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    store_name = data.get("name") or os.path.splitext(os.path.basename(filepath))[0]
    current_layout_path = filepath
    store = data.get("store", {})
    store_width_mm = int(store.get("width_mm", store_width_mm))
    store_height_mm = int(store.get("height_mm", store_height_mm))
    placed_furnitures = []
    for f in data.get("furnitures", []):
        furniture = Furniture(f["name"], f["roi"], f["points"])
        furniture.x = f.get("x", 0)
        furniture.y = f.get("y", 0)
        furniture.rotation = f.get("rotation", 0)
        placed_furnitures.append(furniture)
    collision_polygons = data.get("obstacles", [])
    remember_store_summary(
        current_layout_path,
        width_m=store_width_mm / 1000,
        height_m=store_height_mm / 1000,
        furniture_count=len(placed_furnitures),
        obstacle_count=len(collision_polygons),
    )
    show_toast(
        f"已打开「{store_name}」{store_width_mm / 1000:g}×{store_height_mm / 1000:g} m, "
        f"{len(placed_furnitures)} 件家具, {len(collision_polygons)} 个障碍"
    )


def create_store_layout(name, width_m, height_m, filepath=None):
    global store_name, current_layout_path, placed_furnitures, collision_polygons, startup_active
    store_name = (name or "新门店").strip() or "新门店"
    current_layout_path = filepath or unique_layout_path(store_name)
    placed_furnitures = []
    collision_polygons = []
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
    global renaming_store, renaming_obstacle, editing_wall_size
    editing_canvas_size = True
    editing_wall_size = False
    renaming_store = renaming_obstacle = False
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
    global renaming_store, renaming_obstacle, editing_canvas_size
    editing_wall_size = True
    editing_canvas_size = False
    renaming_store = renaming_obstacle = False
    toggle_draw_obstacle(False)
    wall_length_text = "3"
    wall_width_text = "0.2"
    wall_size_focus = "length"
    wall_size_buttons = build_wall_size_dialog_buttons()


def build_wall_size_dialog_buttons():
    cx = SCREEN_WIDTH // 2
    bw, bh = 88, 34
    y = SCREEN_HEIGHT // 2 + 36
    return {
        "ok": Button((cx - bw - 6, y, bw, bh), "放置", "wall_ok", primary=True),
        "cancel": Button((cx + 6, y, bw, bh), "取消", "wall_cancel"),
    }


def apply_wall_obstacle():
    global editing_wall_size, selected_collision
    try:
        length_m = float(wall_length_text.strip())
        width_m = float(wall_width_text.strip())
    except ValueError:
        show_toast("请输入有效的长宽数字（米）")
        return
    if length_m <= 0 or width_m <= 0:
        show_toast("长宽必须大于 0")
        return
    length_mm = length_m * 1000
    width_mm = width_m * 1000
    cx = store_width_mm / 2
    cy = store_height_mm / 2
    points = clip_obstacle_points(rect_points_centered(cx, cy, length_mm, width_mm))
    if len(points) < 3 or polygon_area(points) <= 1.0:
        show_toast("墙体与门店画布无有效重叠，请缩小尺寸")
        return
    overlaps, other_name = obstacle_overlaps_any(points)
    if overlaps:
        show_toast(f"墙体不能与「{other_name}」重叠")
        return
    wall_count = sum(1 for c in collision_polygons if c.get("kind") == "wall" or str(c.get("name", "")).startswith("墙体"))
    obstacle = {
        "name": f"墙体{wall_count + 1}",
        "points": points,
        "kind": "wall",
    }
    collision_polygons.append(obstacle)
    selected_collision = len(collision_polygons) - 1
    editing_wall_size = False
    show_toast(f"已放置墙体 {length_m:g}×{width_m:g} m，可拖动调整位置")


def cancel_wall_size_edit():
    global editing_wall_size
    editing_wall_size = False


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
    surface.blit(FONT_LABEL.render("添加墙体", True, C_TEXT), (box.x + 20, box.y + 16))
    surface.blit(
        FONT_SMALL.render("输入长方形长宽（米），将放置在门店中心，可拖动调整", True, C_MUTED),
        (box.x + 20, box.y + 44),
    )
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
    global startup_buttons
    startup_active = True
    store_picker_active = False
    editing_canvas_size = False
    editing_wall_size = False
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
    global selected_furniture, selected_feature, selected_collision
    tpl = furniture_templates[selected_template_index]
    new_furn = Furniture(tpl.name, tpl.roi, [tuple(p) for p in tpl.points])
    new_furn.x = store_width_mm / 2
    new_furn.y = store_height_mm / 2
    placed_furnitures.append(new_furn)
    selected_furniture = new_furn
    selected_feature = new_furn
    selected_collision = None
    show_toast(f"已添加: {tpl.name}（可拖动到合适位置）")


def delete_selected():
    global selected_furniture, selected_feature, selected_collision
    if selected_furniture is not None:
        name = selected_furniture.name
        placed_furnitures.remove(selected_furniture)
        selected_furniture = selected_feature = None
        show_toast(f"已删除家具: {name}")
    elif selected_collision is not None:
        name = collision_polygons[selected_collision]["name"]
        collision_polygons.pop(selected_collision)
        selected_collision = None
        show_toast(f"已删除障碍物: {name}")
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
            overlaps, other_name = obstacle_overlaps_any(clipped)
            if overlaps:
                show_toast(f"障碍不能与「{other_name}」重叠")
            else:
                collision_polygons.append({
                    "name": f"障碍物{len(collision_polygons) + 1}",
                    "points": clipped,
                })
                selected_collision = len(collision_polygons) - 1
                show_toast(f"障碍区域已刨除（0.1m 对齐，画布内 {len(clipped)} 个顶点）")
        else:
            show_toast("障碍区域与门店画布无有效重叠，请重新绘制")
    else:
        show_toast("至少需要 3 个顶点")
    current_polygon = []
    drawing_polygon = False
    preview_point = None


def rotate_selected(delta):
    if selected_feature:
        selected_feature.rotate_by(delta)
        show_toast(f"旋转至 {selected_feature.rotation:.0f}°")


def start_rename_obstacle():
    global renaming_obstacle, renaming_store, input_text
    if selected_collision is not None:
        renaming_obstacle = True
        renaming_store = False
        input_text = collision_polygons[selected_collision]["name"]
        show_toast("输入障碍物新名称后按 Enter")


def start_rename_store():
    global renaming_store, renaming_obstacle, input_text
    renaming_store = True
    renaming_obstacle = False
    input_text = store_name
    show_toast("输入门店新名称后按 Enter")


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


def filtered_templates():
    if not search_text.strip():
        return list(enumerate(furniture_templates))
    q = search_text.strip().lower()
    return [(i, t) for i, t in enumerate(furniture_templates) if q in t.name.lower()]


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
        selected = idx == selected_collision
        is_wall = col.get("kind") == "wall" or str(col.get("name", "")).startswith("墙体")
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
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        label = FONT_BODY.render(col["name"], True, label_color)
        surface.blit(label, label.get_rect(center=(cx, cy)))


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
    ppm = scale * 1000
    if ppm > 400:
        bar_len, label = 120, "10 m"
    elif ppm < 8:
        bar_len, label = max(20, int(ppm * 100)), "1 m"
    else:
        bar_len, label = int(min(ppm, 120)), "1 m"
    x0, y0 = SIDEBAR_WIDTH + 24, SCREEN_HEIGHT - 36
    pygame.draw.line(surface, C_TEXT, (x0, y0), (x0 + bar_len, y0), 3)
    surface.blit(FONT_SMALL.render(label, True, C_TEXT), (x0, y0 - 18))


def draw_banner(surface):
    if drawing_polygon:
        rect = pygame.Rect(SIDEBAR_WIDTH + 16, 12, CANVAS_RECT.width - 32, 36)
        pygame.draw.rect(surface, C_ACCENT_LIGHT, rect, border_radius=8)
        pygame.draw.rect(surface, C_ACCENT, rect, 1, border_radius=8)
        text = FONT_SMALL.render("刨除障碍 — 碰边停 | 拐点后可向内转 | Shift 水平/垂直 | Enter 完成", True, C_ACCENT)
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


def product_preview_box():
    box_w, box_h = 520, 420
    return pygame.Rect((SCREEN_WIDTH - box_w) // 2, (SCREEN_HEIGHT - box_h) // 2, box_w, box_h)


def draw_product_preview_dialog(surface):
    if not product_preview:
        return
    from product_images import is_image_failed, request_image

    overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    overlay.fill((15, 23, 42, 165))
    surface.blit(overlay, (0, 0))
    box = product_preview_box()
    pygame.draw.rect(surface, (255, 255, 255), box, border_radius=12)
    pygame.draw.rect(surface, C_BORDER, box, 1, border_radius=12)
    name = product_preview["name"]
    url = product_preview["url"]
    surface.blit(FONT_LABEL.render(name, True, C_TEXT), (box.x + 20, box.y + 16))
    surface.blit(FONT_SMALL.render("Esc 或点击空白处关闭", True, C_MUTED), (box.x + 20, box.y + 42))
    img_rect = pygame.Rect(box.x + 20, box.y + 72, box.width - 40, box.height - 110)
    pygame.draw.rect(surface, (248, 250, 252), img_rect, border_radius=8)
    surf = request_image(url, max_size=(img_rect.width, img_rect.height))
    if surf is not None:
        surface.blit(surf, surf.get_rect(center=img_rect.center))
    elif is_image_failed(url):
        msg = FONT_BODY.render("图片加载失败", True, C_DANGER)
        surface.blit(msg, msg.get_rect(center=img_rect.center))
    else:
        msg = FONT_BODY.render("加载中…", True, C_MUTED)
        surface.blit(msg, msg.get_rect(center=img_rect.center))


def draw_rename_dialog(surface):
    if not renaming_obstacle and not renaming_store:
        return
    box = pygame.Rect(SIDEBAR_WIDTH + 80, 120, 420, 110)
    pygame.draw.rect(surface, (255, 255, 255), box, border_radius=12)
    pygame.draw.rect(surface, C_BORDER, box, 1, border_radius=12)
    title = "重命名门店" if renaming_store else "重命名障碍物"
    surface.blit(FONT_LABEL.render(title, True, C_TEXT), (box.x + 16, box.y + 14))
    input_rect = pygame.Rect(box.x + 16, box.y + 48, box.width - 32, 36)
    pygame.draw.rect(surface, (248, 250, 252), input_rect, border_radius=8)
    pygame.draw.rect(surface, C_ACCENT, input_rect, 2, border_radius=8)
    surface.blit(FONT_BODY.render(input_text + "|", True, C_TEXT), (input_rect.x + 10, input_rect.y + 8))


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
    buttons["obstacle"] = Button((pad, y, bw, 34), "刨除障碍", "obstacle", toggle=True)
    buttons["wall"] = Button((pad + bw + 8, y, bw, 34), "添加墙体", "wall")
    y += 42
    buttons["merge"] = Button((pad, y, w, 34), "融合相邻", "merge")
    y += 42
    buttons["add"] = Button((pad, y, w, 40), "＋ 添加到画布", "add", primary=True)
    y += 48
    buttons["rotate_l"] = Button((pad, y, bw, 34), "左转", "rotate_l")
    buttons["rotate_r"] = Button((pad + bw + 8, y, bw, 34), "右转", "rotate_r")
    y += 42
    buttons["rename"] = Button((pad, y, bw, 34), "重命名", "rename")
    buttons["delete"] = Button((pad + bw + 8, y, bw, 34), "删除", "delete", danger=True)
    template_list_top = y + 50
    return buttons, input_box, template_list_top


def draw_sidebar(buttons, input_box, template_list_top):
    surface = screen
    pygame.draw.rect(surface, C_SIDEBAR, (0, 0, SIDEBAR_WIDTH, SCREEN_HEIGHT))
    pygame.draw.line(surface, C_BORDER, (SIDEBAR_WIDTH - 1, 0), (SIDEBAR_WIDTH - 1, SCREEN_HEIGHT))

    surface.blit(FONT_TITLE.render("坪效布局编辑器", True, C_TEXT), (16, 16))
    name_surf = FONT_SMALL.render(store_name, True, C_ACCENT)
    surface.blit(name_surf, (16, 40))

    input_box.rect.y = 58
    input_box.draw(surface)

    for key in ("save", "home", "rename_store", "store", "obstacle", "wall", "merge", "add", "rotate_l", "rotate_r", "rename", "delete"):
        buttons[key].draw(surface)
    buttons["obstacle"].active = drawing_polygon

    y = template_list_top
    surface.blit(FONT_LABEL.render("家具模板", True, C_TEXT), (16, y))
    y += 28

    filtered = filtered_templates()
    row_h = 44
    for i, (idx, tpl) in enumerate(filtered[:6]):
        row = pygame.Rect(12, y + i * row_h, SIDEBAR_WIDTH - 24, row_h - 6)
        selected = idx == selected_template_index
        bg = C_ACCENT_LIGHT if selected else (248, 250, 252)
        pygame.draw.rect(surface, bg, row, border_radius=8)
        if selected:
            pygame.draw.rect(surface, C_ACCENT, row, 2, border_radius=8)
        color_dot = roi_to_color(tpl.roi)
        pygame.draw.circle(surface, color_dot, (row.x + 16, row.centery), 8)
        surface.blit(FONT_BODY.render(tpl.name, True, C_TEXT), (row.x + 32, row.centery - 10))
        surface.blit(FONT_SMALL.render(f"ROI {tpl.roi:.1f}", True, C_MUTED), (row.x + 32, row.centery + 6))

    y = SCREEN_HEIGHT - 110
    pygame.draw.line(surface, C_BORDER, (16, y), (SIDEBAR_WIDTH - 16, y))
    y += 12
    if selected_feature:
        surface.blit(FONT_SMALL.render(f"选中: {selected_feature.name}", True, C_ACCENT), (16, y))
        y += 20
        surface.blit(FONT_SMALL.render(f"旋转 {selected_feature.rotation:.0f}°  |  ROI {selected_feature.roi:.1f}", True, C_MUTED), (16, y))
    elif selected_collision is not None:
        name = collision_polygons[selected_collision]["name"]
        surface.blit(FONT_SMALL.render(f"选中障碍物: {name}", True, C_DANGER), (16, y))
    else:
        surface.blit(FONT_SMALL.render("未选中对象", True, C_MUTED), (16, y))

    y += 28
    hints = "右键拖动画布 | 滚轮缩放 | 点文字可选中 | 双击家具看图"
    surface.blit(FONT_SMALL.render(hints, True, C_MUTED), (16, y))
    y += 18
    surface.blit(
        FONT_SMALL.render(
            f"{store_name}  |  {store_width_mm / 1000:g}×{store_height_mm / 1000:g} m  |  家具 {len(placed_furnitures)}  |  障碍 {len(collision_polygons)}  |  v{APP_VERSION}",
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
    elif action == "obstacle":
        toggle_draw_obstacle()
        buttons["obstacle"].active = drawing_polygon
    elif action == "wall":
        start_edit_wall_size()
    elif action == "merge":
        merge_selected_obstacle()
    elif action == "add":
        add_furniture_to_canvas()
    elif action == "rotate_l":
        rotate_selected(-15)
    elif action == "rotate_r":
        rotate_selected(15)
    elif action == "rename":
        start_rename_obstacle()
    elif action == "delete":
        delete_selected()


def handle_sidebar_click(mx, my, buttons, input_box, template_list_top):
    global search_box_active, selected_template_index

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
    row_h = 44
    for i, (idx, tpl) in enumerate(filtered[:6]):
        row = pygame.Rect(12, template_list_top + 28 + i * row_h, SIDEBAR_WIDTH - 24, row_h - 6)
        if row.collidepoint(mx, my):
            selected_template_index = idx
            show_toast(f"已选模板: {tpl.name}")
            return


def handle_canvas_click(mx, my, button):
    global selected_furniture, selected_feature, selected_collision
    global dragging_furniture, dragging_collision, collision_drag_offset, collision_drag_snapshot
    global current_polygon, preview_point, _last_furniture_pick

    wx, wy = screen_to_world(mx, my)

    if button == 3:
        return "pan"

    if drawing_polygon:
        last = current_polygon[-1] if current_polygon else None
        verts = obstacle_vertices_for_click(last, wx, wy)
        append_obstacle_vertices(verts)
        preview_point = None
        return

    for i in reversed(range(len(collision_polygons))):
        col = collision_polygons[i]
        if obstacle_label_rect(col).collidepoint(mx, my):
            selected_collision = i
            selected_furniture = selected_feature = None
            dragging_collision = True
            collision_drag_snapshot = [tuple(p) for p in col["points"]]
            pts = col["points"]
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
            collision_drag_offset = (cx - wx, cy - wy)
            show_toast(f"选中: {col['name']}")
            return

    for f in reversed(placed_furnitures):
        if f.is_label_clicked(mx, my) or f.is_clicked(mx, my):
            now = pygame.time.get_ticks()
            is_double = (
                f.name == _last_furniture_pick["name"]
                and now - _last_furniture_pick["time"] < 400
            )
            _last_furniture_pick = {"name": f.name, "time": now}
            dragging_furniture = f
            f.dragging = True
            selected_furniture = f
            selected_feature = f
            selected_collision = None
            if is_double:
                open_product_preview(f.name)
            return

    for i, col in enumerate(collision_polygons):
        if point_in_poly(wx, wy, col["points"]):
            selected_collision = i
            selected_furniture = selected_feature = None
            dragging_collision = True
            collision_drag_snapshot = [tuple(p) for p in col["points"]]
            pts = col["points"]
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
            collision_drag_offset = (cx - wx, cy - wy)
            show_toast(f"选中: {col['name']}")
            return

    selected_furniture = selected_feature = None
    selected_collision = None
    _last_furniture_pick = {"name": None, "time": 0}


def main():
    global offset_x, offset_y, scale, dragging_view, last_mouse_pos
    global drawing_polygon, current_polygon, preview_point
    global selected_collision, selected_furniture, dragging_furniture, selected_feature
    global placed_furnitures, collision_polygons, selected_template_index, dragging_collision, collision_drag_offset
    global renaming_obstacle, renaming_store, input_text, search_text, search_box_active, mouse_pos
    global furniture_templates, startup_active, store_picker_active
    global editing_canvas_size, canvas_w_text, canvas_h_text, canvas_size_focus, force_rebuild_startup
    global editing_wall_size, wall_length_text, wall_width_text, wall_size_focus
    global startup_buttons, _catalog_refresh_ready, product_preview, collision_drag_snapshot

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

            if event.type == EVENT_HOME_DEFERRED:
                handle_home_deferred()
                continue

            if store_picker_active:
                if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    handle_store_picker_mouseup(*event.pos, store_picker_buttons)
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    close_store_picker()
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

            if startup_active:
                if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    handle_startup_mouseup(*event.pos, startup_buttons)
                continue

            if event.type == pygame.MOUSEWHEEL:
                mx, my = mouse_pos
                wx, wy = screen_to_world(mx, my)
                scale = max(MIN_SCALE, min(MAX_SCALE, scale * (ZOOM_IN if event.y > 0 else ZOOM_OUT)))
                offset_x = wx - (mx - SIDEBAR_WIDTH) / scale
                offset_y = wy - my / scale

            elif event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = ui_pos(event.pos)
                if product_preview and event.button == 1:
                    if not product_preview_box().collidepoint(mx, my):
                        close_product_preview()
                    continue
                if mx < SIDEBAR_WIDTH and event.button == 1 and editor_buttons:
                    home_btn = editor_buttons.get("home")
                    if home_btn and home_btn.contains((mx, my)):
                        go_to_store_home()
                        continue
                if mx >= SIDEBAR_WIDTH and event.button == 1:
                    result = handle_canvas_click(mx, my, event.button)
                    if result == "pan":
                        dragging_view = True
                        last_mouse_pos = event.pos
                elif event.button == 3:
                    dragging_view = True
                    last_mouse_pos = event.pos

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    mx, my = ui_pos(event.pos)
                    if mx < SIDEBAR_WIDTH:
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
                    if selected_collision is not None and not drawing_polygon:
                        was_dragging = dragging_collision
                        poly = collision_polygons[selected_collision]
                        clipped = clip_obstacle_points(poly["points"])
                        if len(clipped) >= 3 and polygon_area(clipped) > 1.0:
                            overlaps, other_name = obstacle_overlaps_any(
                                clipped, selected_collision
                            )
                            if overlaps and collision_drag_snapshot is not None:
                                poly["points"] = collision_drag_snapshot
                                show_toast(f"不能与「{other_name}」重叠")
                            else:
                                poly["points"] = clipped
                        elif was_dragging and collision_drag_snapshot is not None:
                            poly["points"] = collision_drag_snapshot
                            show_toast("障碍物已移出画布，请拖回店内")
                    dragging_collision = False
                    collision_drag_snapshot = None

            elif event.type == pygame.MOUSEMOTION:
                mx, my = event.pos
                wx, wy = screen_to_world(mx, my)
                if dragging_view:
                    offset_x += (last_mouse_pos[0] - mx) / scale
                    offset_y += (last_mouse_pos[1] - my) / scale
                    last_mouse_pos = (mx, my)
                elif dragging_furniture and dragging_furniture.dragging:
                    old_x, old_y = dragging_furniture.x, dragging_furniture.y
                    dragging_furniture.x, dragging_furniture.y = wx, wy
                    if check_collision(dragging_furniture, collision_polygons):
                        dragging_furniture.x, dragging_furniture.y = old_x, old_y
                elif dragging_collision and selected_collision is not None:
                    poly = collision_polygons[selected_collision]
                    old = poly["points"]
                    cx = sum(p[0] for p in old) / len(old)
                    cy = sum(p[1] for p in old) / len(old)
                    ncx = wx + collision_drag_offset[0]
                    ncy = wy + collision_drag_offset[1]
                    dx, dy = ncx - cx, ncy - cy
                    poly["points"] = [(x + dx, y + dy) for x, y in old]
                elif drawing_polygon:
                    last = current_polygon[-1] if current_polygon else None
                    preview_point = obstacle_draw_target(last, wx, wy)
                else:
                    preview_point = None

            elif event.type == pygame.KEYDOWN:
                if product_preview and event.key == pygame.K_ESCAPE:
                    close_product_preview()
                    continue
                if renaming_store:
                    if event.key == pygame.K_RETURN and input_text.strip():
                        rename_current_store(input_text.strip())
                        renaming_store = False
                        input_text = ""
                    elif event.key == pygame.K_ESCAPE:
                        renaming_store = False
                        input_text = ""
                    elif event.key == pygame.K_BACKSPACE:
                        input_text = input_text[:-1]
                    elif event.unicode and event.unicode.isprintable():
                        input_text += event.unicode
                elif renaming_obstacle:
                    if event.key == pygame.K_RETURN and selected_collision is not None and input_text.strip():
                        collision_polygons[selected_collision]["name"] = input_text.strip()
                        show_toast("重命名成功")
                        renaming_obstacle = False
                        input_text = ""
                    elif event.key == pygame.K_ESCAPE:
                        renaming_obstacle = False
                        input_text = ""
                    elif event.key == pygame.K_BACKSPACE:
                        input_text = input_text[:-1]
                    elif event.unicode and event.unicode.isprintable():
                        input_text += event.unicode
                elif search_box_active:
                    if event.key == pygame.K_BACKSPACE:
                        search_text = search_text[:-1]
                    elif event.key == pygame.K_ESCAPE:
                        search_box_active = False
                    elif event.unicode and event.unicode.isprintable():
                        search_text += event.unicode
                elif drawing_polygon:
                    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        finish_obstacle()
                        editor_buttons["obstacle"].active = False
                    elif event.key == pygame.K_ESCAPE:
                        toggle_draw_obstacle(False)
                        editor_buttons["obstacle"].active = False
                else:
                    mods = pygame.key.get_mods()
                    if event.key in (pygame.K_DELETE, pygame.K_BACKSPACE):
                        delete_selected()
                    elif event.key == pygame.K_s and mods & pygame.KMOD_CTRL:
                        popup_save_dialog()
                    elif event.key == pygame.K_o and mods & pygame.KMOD_CTRL:
                        popup_load_dialog()
                    elif event.key == pygame.K_LEFT:
                        rotate_selected(-15)
                    elif event.key == pygame.K_RIGHT:
                        rotate_selected(15)
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
            for f in placed_furnitures:
                f.draw(screen, selected=(f is selected_furniture))
            draw_obstacles(screen)
            draw_polygon_preview(screen)
            draw_scale_bar(screen)
            draw_banner(screen)
            draw_rename_dialog(screen)
            draw_sidebar(editor_buttons, input_box, template_list_top)
            draw_toast(screen)
            draw_product_preview_dialog(screen)
            if store_picker_active:
                if store_picker_buttons is None:
                    store_picker_buttons = build_store_picker_ui()
                draw_store_picker(screen, store_picker_buttons)
            else:
                store_picker_buttons = None
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
