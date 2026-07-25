try:
    import pygame
except ModuleNotFoundError:
    print("未找到 pygame。Python 3.14 请安装: python -m pip install pygame-ce")
    raise SystemExit(1) from None

import json
import math
import os
import sys
import tkinter as tk
from tkinter import filedialog

pygame.init()

root = tk.Tk()
root.withdraw()

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

screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("坪效布局编辑器")
clock = pygame.time.Clock()

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
        return self.enabled and self.rect.collidepoint(pos)

    def draw(self, surface):
        hover = self.enabled and self.rect.collidepoint(mouse_pos)
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
        prefix = "🔍 " if not self.text else ""
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
    for col in obstacles:
        for px, py in furniture.get_rotated_points():
            if point_in_poly(px, py, col["points"]):
                return True
    return False


def load_furniture_templates(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    templates = []
    for item in data:
        points = shape_to_points(item)
        if points:
            templates.append(Furniture(item.get("id", "unnamed"), item.get("roi", 0), points))
    return templates


furniture_templates = load_furniture_templates("furniture_templates.json")


# ── 数据持久化 ──────────────────────────────────────────────
def save_layout(filepath="saved_layout.json"):
    data = {
        "furnitures": [
            {"name": f.name, "roi": f.roi, "x": f.x, "y": f.y, "rotation": f.rotation, "points": f.points}
            for f in placed_furnitures
        ],
        "obstacles": collision_polygons,
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    show_toast(f"已保存: {os.path.basename(filepath)}")


def load_layout(filepath="saved_layout.json"):
    global placed_furnitures, collision_polygons
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    placed_furnitures = []
    for f in data.get("furnitures", []):
        furniture = Furniture(f["name"], f["roi"], f["points"])
        furniture.x = f.get("x", 0)
        furniture.y = f.get("y", 0)
        furniture.rotation = f.get("rotation", 0)
        placed_furnitures.append(furniture)
    collision_polygons = data.get("obstacles", [])
    show_toast(f"已加载 {len(placed_furnitures)} 件家具, {len(collision_polygons)} 个障碍物")


def popup_save_dialog():
    path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")], title="保存布局")
    if path:
        save_layout(path)


def popup_load_dialog():
    path = filedialog.askopenfilename(defaultextension=".json", filetypes=[("JSON", "*.json")], title="加载布局")
    if path:
        try:
            load_layout(path)
        except Exception as e:
            show_toast(f"加载失败: {e}")


# ── 操作 ────────────────────────────────────────────────────
def add_furniture_to_canvas():
    global selected_furniture, selected_feature, selected_collision
    tpl = furniture_templates[selected_template_index]
    new_furn = Furniture(tpl.name, tpl.roi, [tuple(p) for p in tpl.points])
    new_furn.x = offset_x + (SCREEN_WIDTH - SIDEBAR_WIDTH) / 2 / scale
    new_furn.y = offset_y + SCREEN_HEIGHT / 2 / scale
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
        show_toast("绘制障碍物: 左键加点, Enter 完成, Esc 取消")
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
        show_toast(f"障碍物已创建 ({len(current_polygon)} 个顶点)")
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
    global renaming_obstacle, input_text
    if selected_collision is not None:
        renaming_obstacle = True
        input_text = collision_polygons[selected_collision]["name"]
        show_toast("输入新名称后按 Enter")


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


def draw_obstacles(surface):
    for idx, col in enumerate(collision_polygons):
        pts = [world_to_screen(x, y) for x, y in col["points"]]
        selected = idx == selected_collision
        fill = C_OBSTACLE_SEL if selected else (254, 202, 202)
        border = C_DANGER if selected else (185, 28, 28)
        pygame.draw.polygon(surface, fill, pts)
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
        text = FONT_SMALL.render("绘制障碍物中 — 左键添加顶点 | Shift 水平/垂直 | Enter 完成 | Esc 取消", True, C_ACCENT)
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
    if not renaming_obstacle:
        return
    box = pygame.Rect(SIDEBAR_WIDTH + 80, 120, 420, 110)
    pygame.draw.rect(surface, (255, 255, 255), box, border_radius=12)
    pygame.draw.rect(surface, C_BORDER, box, 1, border_radius=12)
    surface.blit(FONT_LABEL.render("重命名障碍物", True, C_TEXT), (box.x + 16, box.y + 14))
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
    buttons["load"] = Button((pad + bw + 8, y, bw, 34), "加载", "load")
    y += 42
    buttons["obstacle"] = Button((pad, y, w, 34), "绘制障碍物", "obstacle", toggle=True)
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

    input_box.rect.y = 52
    input_box.draw(surface)

    for key in ("save", "load", "obstacle", "add", "rotate_l", "rotate_r", "rename", "delete"):
        buttons[key].draw(surface)
    buttons["obstacle"].active = drawing_polygon

    y = template_list_top
    surface.blit(FONT_LABEL.render("家具模板", True, C_TEXT), (16, y))
    y += 28

    filtered = filtered_templates()
    row_h = 44
    for i, (idx, tpl) in enumerate(filtered[:8]):
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
    hints = "右键拖动画布 | 滚轮缩放 | Del 删除"
    surface.blit(FONT_SMALL.render(hints, True, C_MUTED), (16, y))
    surface.blit(
        FONT_SMALL.render(f"家具 {len(placed_furnitures)}  |  障碍 {len(collision_polygons)}", True, C_MUTED),
        (16, SCREEN_HEIGHT - 24),
    )


def handle_toolbar_click(action, buttons):
    if action == "save":
        popup_save_dialog()
    elif action == "load":
        popup_load_dialog()
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
    for i, (idx, tpl) in enumerate(filtered[:8]):
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
    global placed_furnitures, selected_template_index, dragging_collision, collision_drag_offset
    global renaming_obstacle, input_text, search_text, search_box_active, mouse_pos

    offset_x = -((SCREEN_WIDTH - SIDEBAR_WIDTH) / 2) / scale
    offset_y = -SCREEN_HEIGHT / 2 / scale

    if os.path.exists("saved_layout.json"):
        try:
            load_layout("saved_layout.json")
        except Exception:
            pass

    buttons, input_box, template_list_top = build_sidebar_ui()
    running = True

    while running:
        mouse_pos = pygame.mouse.get_pos()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.MOUSEWHEEL:
                mx, my = mouse_pos
                wx, wy = screen_to_world(mx, my)
                scale = max(MIN_SCALE, min(MAX_SCALE, scale * (ZOOM_IN if event.y > 0 else ZOOM_OUT)))
                offset_x = wx - (mx - SIDEBAR_WIDTH) / scale
                offset_y = wy - my / scale

            elif event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                if mx < SIDEBAR_WIDTH:
                    handle_sidebar_click(mx, my, buttons, input_box, template_list_top)
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
                if renaming_obstacle:
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
                        buttons["obstacle"].active = False
                    elif event.key == pygame.K_ESCAPE:
                        toggle_draw_obstacle(False)
                        buttons["obstacle"].active = False
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
                        buttons["obstacle"].active = drawing_polygon

        screen.fill(C_CANVAS)
        pygame.draw.rect(screen, C_CANVAS, CANVAS_RECT)
        draw_grid(screen)
        for f in placed_furnitures:
            f.draw(screen, selected=(f is selected_furniture))
        draw_obstacles(screen)
        draw_polygon_preview(screen)
        draw_scale_bar(screen)
        draw_banner(screen)
        draw_rename_dialog(screen)
        draw_sidebar(buttons, input_box, template_list_top)
        draw_toast(screen)
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
