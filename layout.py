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
STORE_PRESETS = [
    ("小型店 12×8 m", 12.0, 8.0),
    ("中型店 20×15 m", 20.0, 15.0),
    ("大型店 30×20 m", 30.0, 20.0),
    ("自定义", None, None),
]

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


def to_surface_pos(pos):
    """Windows 高 DPI 下窗口坐标与画布坐标可能不一致，统一转换。"""
    if screen is None:
        return int(pos[0]), int(pos[1])
    try:
        win_w, win_h = pygame.display.get_window_size()
        surf_w, surf_h = screen.get_size()
        if win_w > 0 and win_h > 0 and (win_w, win_h) != (surf_w, surf_h):
            return (
                int(pos[0] * surf_w / win_w),
                int(pos[1] * surf_h / win_h),
            )
    except (AttributeError, pygame.error):
        pass
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
search_text = ""
search_box_active = False
toast_message = ""
toast_until = 0
mouse_pos = (0, 0)
store_width_mm = int(DEFAULT_STORE_WIDTH_M * 1000)
store_height_mm = int(DEFAULT_STORE_HEIGHT_M * 1000)
startup_active = True
has_saved_layout = False
store_name = "新门店"
current_layout_path = None
store_picker_active = False
renaming_store = False


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
        mx, my = to_surface_pos(pos)
        return self.rect.collidepoint(mx, my)

    def draw(self, surface):
        hover = self.enabled and self.rect.collidepoint(to_surface_pos(mouse_pos))
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
        return self.rect.collidepoint(pos)

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


def point_in_store(x, y):
    return 0 <= x <= store_width_mm and 0 <= y <= store_height_mm


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
        surface.blit(name_surf, name_surf.get_rect(midbottom=(cx, cy - 2)))
        surface.blit(roi_surf, roi_surf.get_rect(midtop=(cx, cy + 2)))

    def is_clicked(self, mx, my):
        wx, wy = screen_to_world(mx, my)
        return point_in_poly(wx, wy, self.get_rotated_points())


def check_collision(furniture, obstacles):
    store_poly = store_rect_points()
    for px, py in furniture.get_rotated_points():
        if not point_in_poly(px, py, store_poly):
            return True
    for col in obstacles:
        for px, py in furniture.get_rotated_points():
            if point_in_poly(px, py, col["points"]):
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


def save_layout(filepath=None):
    global current_layout_path
    filepath = filepath or current_layout_path
    if not filepath:
        filepath = unique_layout_path(store_name)
    ensure_layouts_dir()
    data = {
        "name": store_name,
        "store": {"width_mm": store_width_mm, "height_mm": store_height_mm},
        "furnitures": [
            {"name": f.name, "roi": f.roi, "x": f.x, "y": f.y, "rotation": f.rotation, "points": f.points}
            for f in placed_furnitures
        ],
        "obstacles": collision_polygons,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    current_layout_path = filepath
    show_toast(f"已保存门店: {store_name}")


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
    show_toast(
        f"已打开「{store_name}」{store_width_mm / 1000:g}×{store_height_mm / 1000:g} m, "
        f"{len(placed_furnitures)} 件家具, {len(collision_polygons)} 个障碍"
    )


def create_store_layout(name, width_m, height_m):
    global store_name, current_layout_path, placed_furnitures, collision_polygons, startup_active
    store_name = (name or "新门店").strip() or "新门店"
    current_layout_path = unique_layout_path(store_name)
    placed_furnitures = []
    collision_polygons = []
    set_store_size(width_m, height_m)
    save_layout(current_layout_path)
    startup_active = False
    show_toast(f"已创建门店: {store_name}")


def switch_store_layout(path):
    if current_layout_path and os.path.isfile(current_layout_path):
        try:
            save_layout(current_layout_path)
        except Exception:
            pass
    load_layout(path)
    fit_view_to_store()


def rename_current_store(new_name):
    global store_name, current_layout_path
    new_name = (new_name or "").strip()
    if not new_name:
        show_toast("门店名称不能为空")
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
    try:
        pygame.event.pump()
        get_tk_root().update()
        result = show_store_size_dialog(
            title="调整门店画布",
            width_m=store_width_mm / 1000,
            height_m=store_height_mm / 1000,
        )
        if result.get("ok"):
            set_store_size(result["width_m"], result["height_m"])
            show_toast(f"画布已设为 {result['width_m']:g}×{result['height_m']:g} m")
    except Exception as e:
        show_toast(f"设置失败: {e}")


def build_startup_ui():
    cx = SCREEN_WIDTH // 2
    btn_w, btn_h = 300, 40
    gap = 8
    y = 188
    buttons = {}
    stores = list_store_layouts()
    if stores:
        for i, store in enumerate(stores[:6]):
            label = f"打开: {store['name']}  ({store['width']:g}×{store['height']:g}m)"
            buttons[f"open_{i}"] = Button(
                (cx - btn_w // 2, y, btn_w, btn_h),
                label,
                f"open:{store['path']}",
                primary=(i == 0),
            )
            y += btn_h + gap
        y += 6
    for i, (label, w_m, h_m) in enumerate(STORE_PRESETS):
        if w_m is None:
            continue
        short = label.split()[0]
        buttons[f"preset_{i}"] = Button(
            (cx - btn_w // 2, y, btn_w, btn_h),
            f"新建 {label}",
            f"preset:{w_m}:{h_m}:{short}",
            primary=(i == 1 and not stores),
        )
        y += btn_h + gap
    buttons["custom"] = Button((cx - btn_w // 2, y, btn_w, btn_h), "新建自定义尺寸...", "custom")
    y += btn_h + gap
    buttons["load_file"] = Button((cx - btn_w // 2, y, btn_w, btn_h), "从其他文件打开...", "load_file")
    return buttons


def draw_startup_screen(surface, buttons):
    surface.fill(C_BG)
    title = FONT_TITLE.render("坪效布局 - 快速开始", True, C_TEXT)
    surface.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 72)))
    lines = [
        "1. 选择门店画布尺寸（浅色可行走区域）",
        "2. 点击「刨除障碍」画出墙体 / 柱位等不可摆放区域",
        "3. 从左侧模板添加家具并摆放",
    ]
    for i, line in enumerate(lines):
        surf = FONT_SMALL.render(line, True, C_MUTED)
        surface.blit(surf, surf.get_rect(center=(SCREEN_WIDTH // 2, 108 + i * 22)))
    hint = FONT_SMALL.render("快捷键: 1/2/3 新建 | Enter 中型店 | 点已有门店或预设按钮", True, C_ACCENT)
    surface.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, 178)))
    for btn in buttons.values():
        btn.draw(surface)


def handle_startup_key(event):
    key_map = {
        pygame.K_1: "preset:12.0:8.0:小型店",
        pygame.K_2: "preset:20.0:15.0:中型店",
        pygame.K_3: "preset:30.0:20.0:大型店",
    }
    if event.key in key_map:
        handle_startup_action(key_map[event.key])
    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
        handle_startup_action("preset:20.0:15.0:中型店")


def handle_startup_click(mx, my, buttons, allow_fallback=True):
    mx, my = to_surface_pos((mx, my))
    for btn in buttons.values():
        hit = btn.rect.inflate(12, 12)
        if hit.collidepoint(mx, my):
            print(f"启动选项: {btn.label}")
            handle_startup_action(btn.action)
            return True
    if allow_fallback and my >= 190:
        print("启动选项: 默认中型店 20×15 m（点击兜底）")
        handle_startup_action("preset:20.0:15.0:中型店")
        return True
    return False


_startup_keys_prev = set()
_startup_mouse_prev = False


def poll_startup_input(buttons):
    """每帧轮询键鼠，不依赖事件队列（Windows 上更可靠）。"""
    global _startup_keys_prev, _startup_mouse_prev

    pygame.event.pump()
    mouse_pos_now = to_surface_pos(pygame.mouse.get_pos())
    mouse_down = pygame.mouse.get_pressed(3)[0]
    if mouse_down and not _startup_mouse_prev:
        handle_startup_click(mouse_pos_now[0], mouse_pos_now[1], buttons, allow_fallback=True)
    _startup_mouse_prev = mouse_down

    key_actions = {
        pygame.K_1: "preset:12.0:8.0:小型店",
        pygame.K_2: "preset:20.0:15.0:中型店",
        pygame.K_3: "preset:30.0:20.0:大型店",
        pygame.K_RETURN: "preset:20.0:15.0:中型店",
        pygame.K_KP_ENTER: "preset:20.0:15.0:中型店",
        pygame.K_SPACE: "preset:20.0:15.0:中型店",
    }
    pressed_now = set()
    keys = pygame.key.get_pressed()
    for key, action in key_actions.items():
        if keys[key]:
            pressed_now.add(key)
            if key not in _startup_keys_prev:
                print(f"启动选项: 键盘 {pygame.key.name(key)}")
                handle_startup_action(action)
                return
    _startup_keys_prev = pressed_now


def handle_startup_action(action):
    global startup_active, placed_furnitures, collision_polygons

    if action.startswith("open:"):
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
    show_toast(f"已添加: {tpl.name}")


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
    global drawing_polygon, current_polygon, preview_point
    drawing_polygon = not drawing_polygon if active is None else active
    if drawing_polygon:
        current_polygon = []
        preview_point = None
        show_toast("刨除障碍: 在可行走区域内画出要挖掉的区域 | Enter 完成 | Esc 取消")
    else:
        current_polygon = []
        preview_point = None


def finish_obstacle():
    global drawing_polygon, current_polygon, preview_point
    if len(current_polygon) >= 3:
        collision_polygons.append({
            "name": f"障碍物{len(collision_polygons) + 1}",
            "points": current_polygon.copy(),
        })
        show_toast(f"障碍区域已刨除 ({len(current_polygon)} 个顶点)")
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
    stores = list_store_layouts()
    cx = SCREEN_WIDTH // 2
    btn_w, btn_h = 420, 40
    gap = 8
    y = 130
    buttons = {}
    buttons["picker_new"] = Button((cx - btn_w // 2, y, btn_w, btn_h), "＋ 新建门店", "picker_new", primary=True)
    y += btn_h + gap + 8
    for i, store in enumerate(stores[:10]):
        mark = " ●" if store["path"] == current_layout_path else ""
        label = f"{store['name']}{mark}  ({store['width']:g}×{store['height']:g}m)"
        buttons[f"picker_{i}"] = Button(
            (cx - btn_w // 2, y, btn_w, btn_h),
            label,
            f"picker_open:{store['path']}",
        )
        y += btn_h + gap
    buttons["picker_close"] = Button((cx - btn_w // 2, SCREEN_HEIGHT - 70, btn_w, 36), "关闭", "picker_close")
    return buttons


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


def handle_store_picker_click(mx, my, buttons):
    mx, my = to_surface_pos((mx, my))
    for btn in buttons.values():
        if btn.rect.collidepoint(mx, my):
            handle_store_picker_action(btn.action)
            return True
    return False


def handle_store_picker_action(action):
    global store_picker_active, startup_active
    if action == "picker_close":
        close_store_picker()
    elif action == "picker_new":
        close_store_picker()
        startup_active = True
    elif action.startswith("picker_open:"):
        path = action[len("picker_open:"):]
        switch_store_layout(path)
        close_store_picker()


def filtered_templates():
    if not search_text.strip():
        return list(enumerate(furniture_templates))
    q = search_text.strip().lower()
    return [(i, t) for i, t in enumerate(furniture_templates) if q in t.name.lower()]


# ── 绘制 ────────────────────────────────────────────────────
def draw_grid(surface):
    start_x = int(offset_x // GRID_SPACING * GRID_SPACING)
    end_x = int((offset_x + CANVAS_RECT.width / scale) // GRID_SPACING * GRID_SPACING + GRID_SPACING)
    start_y = int(offset_y // GRID_SPACING * GRID_SPACING)
    end_y = int((offset_y + SCREEN_HEIGHT / scale) // GRID_SPACING * GRID_SPACING + GRID_SPACING)
    for x in range(start_x, end_x, GRID_SPACING):
        sx = world_to_screen(x, 0)[0]
        pygame.draw.line(surface, C_GRID, (sx, 0), (sx, SCREEN_HEIGHT))
    for y in range(start_y, end_y, GRID_SPACING):
        sy = world_to_screen(0, y)[1]
        pygame.draw.line(surface, C_GRID, (SIDEBAR_WIDTH, sy), (SCREEN_WIDTH, sy))


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


def _draw_excavation_hatch(surface, pts):
    if len(pts) < 3:
        return
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    min_x, max_x = int(min(xs)), int(max(xs))
    min_y, max_y = int(min(ys)), int(max(ys))
    step = 14
    hatch_color = (185, 28, 28, 80)
    for i in range(min_x - max_y, max_x + max_y, step):
        line = [(i, min_y - 20), (i + (max_y - min_y) + 40, max_y + 20)]
        pygame.draw.lines(surface, hatch_color[:3], False, line, 1)


def draw_obstacles(surface):
    for idx, col in enumerate(collision_polygons):
        pts = [world_to_screen(x, y) for x, y in col["points"]]
        selected = idx == selected_collision
        fill = C_OBSTACLE_SEL if selected else (254, 202, 202)
        border = C_DANGER if selected else (185, 28, 28)
        pygame.draw.polygon(surface, fill, pts)
        _draw_excavation_hatch(surface, pts)
        pygame.draw.polygon(surface, border, pts, 3 if selected else 2)
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        label = FONT_BODY.render(col["name"], True, (127, 29, 29))
        surface.blit(label, label.get_rect(center=(cx, cy)))


def draw_polygon_preview(surface):
    if not drawing_polygon or not current_polygon:
        return
    screen_pts = [world_to_screen(x, y) for x, y in current_polygon]
    if preview_point:
        screen_pts.append(world_to_screen(*preview_point))
    if len(screen_pts) >= 2:
        pygame.draw.lines(surface, C_ACCENT, False, screen_pts, 2)
    for pt in screen_pts:
        pygame.draw.circle(surface, C_ACCENT, (int(pt[0]), int(pt[1])), 5)
    if len(current_polygon) >= 1 and preview_point:
        last = current_polygon[-1]
        dist_m = math.hypot(preview_point[0] - last[0], preview_point[1] - last[1]) / 1000
        mid = world_to_screen((last[0] + preview_point[0]) / 2, (last[1] + preview_point[1]) / 2)
        tag = FONT_SMALL.render(f"{dist_m:.2f} m", True, C_ACCENT)
        surface.blit(tag, (mid[0] + 8, mid[1] - 10))


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
        text = FONT_SMALL.render("刨除障碍中 — 在浅色可行走区内画出要挖掉的区域 | Enter 完成 | Esc 取消", True, C_ACCENT)
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
    buttons["switch"] = Button((pad + bw + 8, y, bw, 34), "切换门店", "switch")
    y += 42
    buttons["rename_store"] = Button((pad, y, w, 34), "重命名门店", "rename_store")
    y += 42
    buttons["store"] = Button((pad, y, w, 34), "门店画布尺寸", "store")
    y += 42
    buttons["obstacle"] = Button((pad, y, w, 34), "刨除障碍", "obstacle", toggle=True)
    y += 42
    buttons["add"] = Button((pad, y, w, 40), "＋ 添加到画布", "add", primary=True)
    y += 48
    buttons["rotate_l"] = Button((pad, y, bw, 34), "↺ 左转", "rotate_l")
    buttons["rotate_r"] = Button((pad + bw + 8, y, bw, 34), "↻ 右转", "rotate_r")
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

    for key in ("save", "switch", "rename_store", "store", "obstacle", "add", "rotate_l", "rotate_r", "rename", "delete"):
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
    hints = "右键拖动画布 | 滚轮缩放 | 浅色=可行走 | 红色=刨除障碍"
    surface.blit(FONT_SMALL.render(hints, True, C_MUTED), (16, y))
    y += 18
    surface.blit(
        FONT_SMALL.render(
            f"{store_name}  |  {store_width_mm / 1000:g}×{store_height_mm / 1000:g} m  |  家具 {len(placed_furnitures)}  |  障碍 {len(collision_polygons)}",
            True,
            C_MUTED,
        ),
        (16, SCREEN_HEIGHT - 24),
    )


def handle_toolbar_click(action, buttons):
    if action == "save":
        save_current_layout()
    elif action == "switch":
        open_store_picker()
    elif action == "rename_store":
        start_rename_store()
    elif action == "store":
        popup_store_size_dialog()
    elif action == "obstacle":
        toggle_draw_obstacle()
        buttons["obstacle"].active = drawing_polygon
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
    global dragging_furniture, dragging_collision, collision_drag_offset
    global current_polygon, preview_point

    wx, wy = screen_to_world(mx, my)

    if button == 3:
        return "pan"

    if drawing_polygon:
        if not point_in_store(wx, wy):
            show_toast("请在门店画布内绘制障碍区域")
            return
        if current_polygon:
            last = current_polygon[-1]
            keys = pygame.key.get_pressed()
            if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
                if abs(wx - last[0]) > abs(wy - last[1]):
                    wy = last[1]
                else:
                    wx = last[0]
        current_polygon.append((wx, wy))
        return

    for f in reversed(placed_furnitures):
        if f.is_clicked(mx, my):
            dragging_furniture = f
            f.dragging = True
            selected_furniture = f
            selected_feature = f
            selected_collision = None
            return

    for i, col in enumerate(collision_polygons):
        if point_in_poly(wx, wy, col["points"]):
            selected_collision = i
            selected_furniture = selected_feature = None
            dragging_collision = True
            pts = col["points"]
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
            collision_drag_offset = (cx - wx, cy - wy)
            show_toast(f"选中: {col['name']}")
            return

    selected_furniture = selected_feature = None
    selected_collision = None


def main():
    global offset_x, offset_y, scale, dragging_view, last_mouse_pos
    global drawing_polygon, current_polygon, preview_point
    global selected_collision, selected_furniture, dragging_furniture, selected_feature
    global placed_furnitures, collision_polygons, selected_template_index, dragging_collision, collision_drag_offset
    global renaming_obstacle, renaming_store, input_text, search_text, search_box_active, mouse_pos
    global furniture_templates, startup_active, store_picker_active

    try:
        furniture_templates = load_furniture_templates("furniture_templates.json")
    except Exception as e:
        messagebox.showerror("启动失败", f"无法加载家具模板:\n{e}\n\n当前目录:\n{os.getcwd()}")
        raise SystemExit(1) from e

    ensure_layouts_dir()
    init_display()
    print("坪效布局编辑器已启动。")
    print("提示: 可选择已有门店，或按 2 / Enter 新建中型店。")

    stores = list_store_layouts()
    if stores:
        try:
            switch_store_layout(stores[0]["path"])
            startup_active = False
            print(f"已自动打开最近门店: {stores[0]['name']}")
        except Exception as e:
            print(f"自动打开门店失败: {e}")
            startup_active = True
    else:
        startup_active = True

    startup_buttons = build_startup_ui() if startup_active else None
    store_picker_buttons = None
    editor_buttons = None
    input_box = None
    template_list_top = 0
    running = True

    while running:
        mouse_pos = to_surface_pos(pygame.mouse.get_pos())
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                continue

            if store_picker_active:
                if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP) and event.button == 1:
                    handle_store_picker_click(*event.pos, store_picker_buttons)
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    close_store_picker()
                continue

            if startup_active:
                if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP) and event.button == 1:
                    handle_startup_click(*event.pos, startup_buttons, allow_fallback=False)
                elif event.type == pygame.KEYDOWN:
                    handle_startup_key(event)
                continue

            if event.type == pygame.MOUSEWHEEL:
                mx, my = mouse_pos
                wx, wy = screen_to_world(mx, my)
                scale = max(MIN_SCALE, min(MAX_SCALE, scale * (ZOOM_IN if event.y > 0 else ZOOM_OUT)))
                offset_x = wx - (mx - SIDEBAR_WIDTH) / scale
                offset_y = wy - my / scale

            elif event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                if mx < SIDEBAR_WIDTH:
                    handle_sidebar_click(mx, my, editor_buttons, input_box, template_list_top)
                elif event.button == 1:
                    result = handle_canvas_click(mx, my, event.button)
                    if result == "pan":
                        dragging_view = True
                        last_mouse_pos = event.pos
                elif event.button == 3:
                    dragging_view = True
                    last_mouse_pos = event.pos

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button in (1, 3):
                    dragging_view = False
                if event.button == 1:
                    if dragging_furniture:
                        dragging_furniture.dragging = False
                        dragging_furniture = None
                    dragging_collision = False

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
                elif drawing_polygon and current_polygon:
                    last = current_polygon[-1]
                    keys = pygame.key.get_pressed()
                    if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
                        if abs(wx - last[0]) > abs(wy - last[1]):
                            wy = last[1]
                        else:
                            wx = last[0]
                    preview_point = (wx, wy)
                else:
                    preview_point = None

            elif event.type == pygame.KEYDOWN:
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
            poll_startup_input(startup_buttons)
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
            if store_picker_active:
                if store_picker_buttons is None:
                    store_picker_buttons = build_store_picker_ui()
                draw_store_picker(screen, store_picker_buttons)
            else:
                store_picker_buttons = None
        pygame.display.flip()
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
