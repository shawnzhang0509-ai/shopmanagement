try:
    import pygame
except ModuleNotFoundError:
    print("未找到 pygame。Python 3.14 请安装: python -m pip install pygame-ce")
    if __name__ == "__main__":
        input("\n按 Enter 退出...")
    raise SystemExit(1) from None

import json
import math
import os
import sys
import traceback
import copy

from roi_lookup import lookup_roi, reload_roi_map

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)
TEMPLATES_FILE = "furniture_templates.json"

pygame.init()

try:
    import ui_common as ui
except ImportError as exc:
    print("无法加载 ui_common.py，请确认该文件与 furniture_sim.py 在同一目录。")
    print(f"当前目录: {os.getcwd()}")
    print(f"错误: {exc}")
    if __name__ == "__main__":
        input("\n按 Enter 退出...")
    raise SystemExit(1) from exc

ui.init_fonts()

# 必须在 init_fonts() 之后绑定，否则字体为 None
SIDEBAR_WIDTH = ui.SIDEBAR_WIDTH
SCREEN_WIDTH = ui.SCREEN_WIDTH
SCREEN_HEIGHT = ui.SCREEN_HEIGHT
C_ACCENT = ui.C_ACCENT
C_BORDER = ui.C_BORDER
C_CANVAS = ui.C_CANVAS
C_GRID = ui.C_GRID
C_MUTED = ui.C_MUTED
C_PREVIEW = ui.C_PREVIEW
C_PREVIEW_FILL = ui.C_PREVIEW_FILL
C_TEXT = ui.C_TEXT
FONT_TITLE = ui.FONT_TITLE
FONT_BODY = ui.FONT_BODY
FONT_SMALL = ui.FONT_SMALL
FONT_LABEL = ui.FONT_LABEL
FONT_MARK = ui.FONT_MARK
Button = ui.Button
draw_sidebar_bg = ui.draw_sidebar_bg

_tk_root = None


def get_tk_root():
    global _tk_root
    if _tk_root is None:
        import tkinter as tk
        _tk_root = tk.Tk()
        _tk_root.withdraw()
    return _tk_root


def filedialog_save(**kwargs):
    from tkinter import filedialog
    return filedialog.asksaveasfilename(parent=get_tk_root(), **kwargs)


def filedialog_open(**kwargs):
    from tkinter import filedialog
    return filedialog.askopenfilename(parent=get_tk_root(), **kwargs)


def show_error(title, message):
    try:
        from tkinter import messagebox
        messagebox.showerror(title, message, parent=get_tk_root())
    except Exception:
        print(f"{title}: {message}")


screen = None
clock = None

# ── 画布状态 ────────────────────────────────────────────────
offset_x, offset_y = 0.0, 0.0
scale = 0.08
dragging_view = False
last_mouse_pos = (0, 0)
mouse_pos = (0, 0)
toast = ui.Toast()
GRID_SNAP = 100  # 100mm = 10cm
resizing_handle = None

# ── 工具与绘制 ──────────────────────────────────────────────
TOOLS = [
    ("rect", "矩形"),
    ("circle", "圆形"),
    ("l_shape", "L 形"),
    ("polygon", "多边形"),
]
current_tool = "rect"
draw_phase = "idle"  # idle | drawing | l_cut
drag_start = None
drag_current = None
l_outer_corners = None  # L形外框 (x0, y0, x1, y1)
l_cut_preview = None
polygon_points = []
preview_point = None

# ── 表单 ────────────────────────────────────────────────────
furniture_templates = []
selected_index = -1
editing_template = None  # dict preview before save

input_name = ui.InputBox((0, 0, 0, 0), placeholder="例如 corner_sofa")
input_family = ui.InputBox((0, 0, 0, 0), placeholder="例如 corner_sofa")


def screen_to_world(sx, sy):
    return offset_x + (sx - SIDEBAR_WIDTH) / scale, offset_y + sy / scale


def world_to_screen(wx, wy):
    return (wx - offset_x) * scale + SIDEBAR_WIDTH, (wy - offset_y) * scale


def snap_grid(wx, wy):
    """默认吸附 10cm 网格，按住 Shift 可自由定位。"""
    keys = pygame.key.get_pressed()
    if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
        return wx, wy
    return round(wx / GRID_SNAP) * GRID_SNAP, round(wy / GRID_SNAP) * GRID_SNAP


def snap_point(wx, wy, ref=None):
    wx, wy = snap_grid(wx, wy)
    keys = pygame.key.get_pressed()
    if ref and (keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]):
        rx, ry = ref
        if abs(wx - rx) > abs(wy - ry):
            wy = ry
        else:
            wx = rx
    return wx, wy


def draw_grid(surface):
    spacing = 100
    start_x = int(offset_x // spacing * spacing)
    end_x = int((offset_x + (SCREEN_WIDTH - SIDEBAR_WIDTH) / scale) // spacing * spacing + spacing)
    start_y = int(offset_y // spacing * spacing)
    end_y = int((offset_y + SCREEN_HEIGHT / scale) // spacing * spacing + spacing)
    for x in range(start_x, end_x, spacing):
        sx = world_to_screen(x, 0)[0]
        pygame.draw.line(surface, C_GRID, (sx, 0), (sx, SCREEN_HEIGHT))
    for y in range(start_y, end_y, spacing):
        sy = world_to_screen(0, y)[1]
        pygame.draw.line(surface, C_GRID, (SIDEBAR_WIDTH, sy), (SCREEN_WIDTH, sy))


def polygon_from_rect(x0, y0, x1, y1):
    left, right = sorted([x0, x1])
    top, bottom = sorted([y0, y1])
    return [(left, top), (right, top), (right, bottom), (left, bottom)]


def polygon_from_circle(cx, cy, r):
    return [(cx + r * math.cos(2 * math.pi * i / 32), cy + r * math.sin(2 * math.pi * i / 32)) for i in range(32)]


def polygon_from_l_shape(x0, y0, x1, y1, cut_x, cut_y):
    left, right = sorted([x0, x1])
    top, bottom = sorted([y0, y1])
    cut_x = max(left + 1, min(right - 1, cut_x))
    cut_y = max(top + 1, min(bottom - 1, cut_y))
    return [(left, top), (right, top), (right, cut_y), (cut_x, cut_y), (cut_x, bottom), (left, bottom)]


def normalize_template_dict(data):
    shape_type = data.get("type", "")
    if shape_type == "rectangle":
        w, h = data.get("width", 0), data.get("height", 0)
        points = [(0, 0), (w, 0), (w, h), (0, h)]
    elif shape_type == "circle":
        r = data.get("radius", 0)
        points = polygon_from_circle(0, 0, r)
    else:
        points = [tuple(p) for p in data.get("points", [])]
    return points


def template_to_dict(name, product_family, tool, points):
    roi = lookup_roi(product_family)
    if tool == "rect":
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        return {
            "id": name,
            "product_family": product_family,
            "type": "rectangle",
            "width": int(round(w)),
            "height": int(round(h)),
            "roi": roi,
        }
    if tool == "circle":
        cx = sum(p[0] for p in points) / len(points)
        cy = sum(p[1] for p in points) / len(points)
        r = math.hypot(points[0][0] - cx, points[0][1] - cy)
        return {
            "id": name,
            "product_family": product_family,
            "type": "circle",
            "radius": int(round(r)),
            "roi": roi,
        }
    return {
        "id": name,
        "product_family": product_family,
        "type": "polygon",
        "points": [[int(round(x)), int(round(y))] for x, y in points],
        "roi": roi,
    }


def draw_shape(surface, points, fill=C_PREVIEW_FILL, border=C_PREVIEW, width=2, closed=True):
    if len(points) < 2:
        return
    screen_pts = [world_to_screen(x, y) for x, y in points]
    if closed and len(screen_pts) >= 3:
        pygame.draw.polygon(surface, fill, screen_pts)
    if len(screen_pts) >= 2:
        pygame.draw.lines(surface, border, closed, screen_pts, width)
    for pt in screen_pts:
        pygame.draw.circle(surface, border, (int(pt[0]), int(pt[1])), 4)


def draw_dimension_label(surface, p1, p2, text):
    mid = world_to_screen((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
    label = FONT_MARK.render(text, True, C_ACCENT)
    bg = label.get_rect(center=(mid[0], mid[1] - 12))
    bg.inflate_ip(8, 4)
    pygame.draw.rect(surface, (255, 255, 255), bg, border_radius=4)
    surface.blit(label, label.get_rect(center=(mid[0], mid[1] - 12)))


def get_resize_handles():
    if not editing_template:
        return []
    t = editing_template
    if t["type"] == "rectangle":
        w, h = t.get("width", 0), t.get("height", 0)
        return [
            ("br", (w, h)),
            ("tr", (w, 0)),
            ("bl", (0, h)),
        ]
    if t["type"] == "circle":
        r = t.get("radius", 0)
        return [("r", (r, 0))]
    return [(i, tuple(p)) for i, p in enumerate(t.get("points", []))]


def hit_resize_handle(mx, my):
    for handle_id, (wx, wy) in get_resize_handles():
        sx, sy = world_to_screen(wx, wy)
        if math.hypot(mx - sx, my - sy) <= 12:
            return handle_id
    return None


def apply_resize(handle_id, wx, wy):
    global editing_template
    if not editing_template:
        return
    wx, wy = snap_grid(wx, wy)
    t = editing_template
    if t["type"] == "rectangle":
        w, h = t.get("width", 0), t.get("height", 0)
        if handle_id == "br":
            t["width"] = int(max(GRID_SNAP, wx))
            t["height"] = int(max(GRID_SNAP, wy))
        elif handle_id == "tr":
            t["width"] = int(max(GRID_SNAP, wx))
            t["height"] = int(max(GRID_SNAP, h))
        elif handle_id == "bl":
            t["width"] = int(max(GRID_SNAP, w))
            t["height"] = int(max(GRID_SNAP, wy))
    elif t["type"] == "circle":
        r = int(max(GRID_SNAP, math.hypot(wx, wy)))
        t["radius"] = r
    elif isinstance(handle_id, int):
        pts = t.get("points", [])
        if 0 <= handle_id < len(pts):
            pts[handle_id] = [int(wx), int(wy)]


def draw_resize_handles(surface):
    if not editing_template or draw_phase != "idle":
        return
    for handle_id, (wx, wy) in get_resize_handles():
        sx, sy = world_to_screen(wx, wy)
        color = (234, 88, 12) if resizing_handle == handle_id else (251, 146, 60)
        pygame.draw.circle(surface, color, (int(sx), int(sy)), 8)
        pygame.draw.circle(surface, (255, 255, 255), (int(sx), int(sy)), 8, 2)
    pts = normalize_template_dict(editing_template)
    if editing_template["type"] == "rectangle" and len(pts) >= 4:
        w = abs(pts[1][0] - pts[0][0]) / 1000
        h = abs(pts[2][1] - pts[1][1]) / 1000
        draw_dimension_label(surface, pts[0], pts[1], f"{w:.1f} m")
        draw_dimension_label(surface, pts[1], pts[2], f"{h:.1f} m")
    elif editing_template["type"] == "circle":
        r = editing_template.get("radius", 0) / 1000
        draw_dimension_label(surface, (0, 0), (editing_template.get("radius", 0), 0), f"R {r:.1f} m")


def draw_canvas(surface):
    surface.fill(C_CANVAS)
    draw_grid(surface)

    if editing_template:
        pts = normalize_template_dict(editing_template)
        draw_shape(surface, pts, fill=(254, 243, 199), border=(217, 119, 6))
        draw_resize_handles(surface)

    if current_tool == "polygon" and polygon_points:
        pts = polygon_points + ([preview_point] if preview_point else [])
        draw_shape(surface, pts, closed=False)
        if len(polygon_points) >= 2:
            p1, p2 = polygon_points[-2], polygon_points[-1]
            draw_dimension_label(surface, p1, p2, f"{math.hypot(p2[0]-p1[0], p2[1]-p1[1])/1000:.2f} m")

    if draw_phase == "drawing" and drag_start and drag_current:
        if current_tool == "rect":
            pts = polygon_from_rect(*drag_start, *drag_current)
            draw_shape(surface, pts)
            w = abs(drag_current[0] - drag_start[0]) / 1000
            h = abs(drag_current[1] - drag_start[1]) / 1000
            draw_dimension_label(surface, pts[0], pts[1], f"{w:.2f} m")
            draw_dimension_label(surface, pts[1], pts[2], f"{h:.2f} m")
        elif current_tool == "circle":
            cx, cy = drag_start
            r = math.hypot(drag_current[0] - cx, drag_current[1] - cy)
            pts = polygon_from_circle(cx, cy, r)
            draw_shape(surface, pts)
            draw_dimension_label(surface, (cx, cy), drag_current, f"R {r/1000:.2f} m")

    if draw_phase == "l_cut" and l_outer_corners and l_cut_preview:
        x0, y0, x1, y1 = l_outer_corners
        cx, cy = l_cut_preview
        pts = polygon_from_l_shape(x0, y0, x1, y1, cx, cy)
        draw_shape(surface, pts)

    # 十字中心线
    cx, cy = world_to_screen(0, 0)
    pygame.draw.line(surface, (148, 163, 184), (SIDEBAR_WIDTH, cy), (SCREEN_WIDTH, cy), 1)
    pygame.draw.line(surface, (148, 163, 184), (cx, 0), (cx, SCREEN_HEIGHT), 1)

    if current_tool == "polygon" and draw_phase != "idle":
        banner = pygame.Rect(SIDEBAR_WIDTH + 16, 12, SCREEN_WIDTH - SIDEBAR_WIDTH - 32, 34)
        pygame.draw.rect(surface, (219, 234, 254), banner, border_radius=8)
        tip = "多边形模式: 左键加点 | Shift 正交 | Enter 完成 | Esc 取消 | 右键拖动画布"
        surface.blit(FONT_SMALL.render(tip, True, C_ACCENT), (banner.x + 12, banner.y + 9))
    elif draw_phase == "drawing":
        tip = "拖拽绘制形状，松开鼠标完成"
        surface.blit(FONT_SMALL.render(tip, True, C_MUTED), (SIDEBAR_WIDTH + 16, 12))
    elif draw_phase == "l_cut":
        tip = "第二步: 点击 L 形内角位置"
        surface.blit(FONT_SMALL.render(tip, True, C_MUTED), (SIDEBAR_WIDTH + 16, 12))
    elif editing_template and draw_phase == "idle":
        tip = "拖动橙色角点调整大小 | 自动对齐 10cm | Shift 自由定位"
        surface.blit(FONT_SMALL.render(tip, True, C_MUTED), (SIDEBAR_WIDTH + 16, 12))
    elif draw_phase == "idle":
        tip = "自动对齐 10cm 网格 | 按住 Shift 自由绘制"
        surface.blit(FONT_SMALL.render(tip, True, C_MUTED), (SIDEBAR_WIDTH + 16, 12))


def build_sidebar():
    pad = 16
    w = SIDEBAR_WIDTH - pad * 2
    y = 16
    tool_buttons = {}
    bw = (w - 8) // 2
    for i, (tool_id, label) in enumerate(TOOLS):
        col, row = i % 2, i // 2
        rect = (pad + col * (bw + 8), y + 52 + row * 38, bw, 32)
        tool_buttons[tool_id] = Button(rect, label, f"tool:{tool_id}", toggle=True)
    y += 52 + 38 * 2 + 8

    input_name.rect = pygame.Rect(pad, y + 18, w, 34)
    input_family.rect = pygame.Rect(pad, y + 72, w, 34)
    y += 132

    buttons = {
        "apply": Button((pad, y, w, 38), "保存到列表", "apply", primary=True),
        "copy": Button((pad, y + 46, w, 34), "复制选中模板", "copy"),
        "write": Button((pad, y + 86, w, 34), "写入 furniture_templates.json", "write"),
        "export": Button((pad, y + 126, bw, 34), "导出", "export"),
        "import": Button((pad + bw + 8, y + 126, bw, 34), "导入", "import"),
        "delete": Button((pad, y + 166, w, 34), "删除选中", "delete", danger=True),
        "clear": Button((pad, y + 206, w, 34), "清空画布", "clear"),
    }
    list_top = y + 250
    return tool_buttons, buttons, list_top


def draw_sidebar(tool_buttons, buttons, list_top):
    draw_sidebar_bg(screen)
    screen.blit(FONT_TITLE.render("家具模板编辑器", True, C_TEXT), (16, 16))
    screen.blit(FONT_SMALL.render("在右侧画布拖拽或点击绘制", True, C_MUTED), (16, 42))

    for btn in tool_buttons.values():
        btn.active = btn.action == f"tool:{current_tool}"
        btn.draw(screen, mouse_pos)
    for btn in buttons.values():
        btn.draw(screen, mouse_pos)

    input_name.draw(screen, "模板名称")
    input_family.draw(screen, "Product Family")
    family = input_family.get_text()
    roi_val = lookup_roi(family)
    roi_hint = f"ROI: {roi_val:.1f}（按 Product Family 自动匹配）"
    if family and roi_val == 0:
        roi_hint = f"ROI: 未找到「{family}」，请检查 roi.xlsx"
    screen.blit(FONT_SMALL.render(roi_hint, True, C_MUTED), (16, input_family.rect.bottom + 6))

    screen.blit(FONT_LABEL.render("已保存模板", True, C_TEXT), (16, list_top))
    y = list_top + 28
    for i, tpl in enumerate(furniture_templates):
        row = pygame.Rect(12, y + i * 46, SIDEBAR_WIDTH - 24, 40)
        selected = i == selected_index
        bg = (219, 234, 254) if selected else (248, 250, 252)
        pygame.draw.rect(screen, bg, row, border_radius=8)
        if selected:
            pygame.draw.rect(screen, C_ACCENT, row, 2, border_radius=8)
        family_label = tpl.get("product_family", tpl.get("id", ""))
        screen.blit(FONT_SMALL.render(tpl["id"], True, C_TEXT), (row.x + 10, row.y + 6))
        screen.blit(
            FONT_SMALL.render(f"{family_label}  |  ROI {tpl.get('roi', '-')}", True, C_MUTED),
            (row.x + 10, row.y + 22),
        )

    screen.blit(
        FONT_SMALL.render(f"共 {len(furniture_templates)} 个模板", True, C_MUTED),
        (16, SCREEN_HEIGHT - 24),
    )


def reset_draw_state():
    global draw_phase, drag_start, drag_current, polygon_points, preview_point, editing_template
    global l_outer_corners, l_cut_preview, resizing_handle
    draw_phase = "idle"
    drag_start = None
    drag_current = None
    l_outer_corners = None
    l_cut_preview = None
    resizing_handle = None
    polygon_points = []
    preview_point = None
    editing_template = None


def apply_current_shape():
    global editing_template
    name = input_name.get_text() or f"template_{len(furniture_templates) + 1}"
    family = input_family.get_text() or name

    points = None
    if current_tool == "polygon" and len(polygon_points) >= 3:
        points = polygon_points[:]
    elif editing_template:
        points = normalize_template_dict(editing_template)
    else:
        toast.show("请先在画布上绘制形状")
        return

    if not points:
        toast.show("形状无效，请重新绘制")
        return

    editing_template = template_to_dict(name, family, current_tool if current_tool != "l_shape" else "polygon", points)
    if current_tool == "l_shape":
        editing_template["type"] = "polygon"
    roi = editing_template["roi"]
    if roi == 0:
        toast.show(f"已生成: {name}，但 roi.xlsx 中未找到 {family}")
    else:
        toast.show(f"已生成: {name}，ROI={roi:.1f}")


def save_to_list():
    global selected_index
    if not editing_template:
        apply_current_shape()
    if not editing_template:
        return
    family = input_family.get_text() or editing_template.get("id", "")
    editing_template["id"] = input_name.get_text() or editing_template["id"]
    editing_template["product_family"] = family
    editing_template["roi"] = lookup_roi(family)
    name = editing_template["id"]
    if selected_index >= 0:
        furniture_templates[selected_index] = editing_template.copy()
        toast.show(f"已更新: {name}")
    else:
        furniture_templates.append(editing_template.copy())
        selected_index = len(furniture_templates) - 1
        toast.show(f"已添加: {name}")


def write_templates_file():
    if not furniture_templates:
        toast.show("列表为空，请先保存模板")
        return
    with open(TEMPLATES_FILE, "w", encoding="utf-8") as f:
        json.dump(furniture_templates, f, ensure_ascii=False, indent=2)
    toast.show(f"已写入 {TEMPLATES_FILE}")


def load_templates_file(path=TEMPLATES_FILE):
    global furniture_templates, selected_index
    if not os.path.isfile(path):
        return
    reload_roi_map()
    with open(path, "r", encoding="utf-8") as f:
        furniture_templates = json.load(f)
    for tpl in furniture_templates:
        family = tpl.get("product_family") or tpl.get("id", "")
        tpl["product_family"] = family
        tpl["roi"] = lookup_roi(family)
    selected_index = 0 if furniture_templates else -1
    if furniture_templates:
        load_template_into_editor(0)
    toast.show(f"已加载 {len(furniture_templates)} 个模板")


def load_template_into_editor(index):
    global selected_index, editing_template, current_tool
    selected_index = index
    tpl = furniture_templates[index]
    editing_template = tpl.copy()
    input_name.set_text(tpl["id"])
    input_family.set_text(tpl.get("product_family", tpl["id"]))
    if tpl["type"] == "rectangle":
        current_tool = "rect"
    elif tpl["type"] == "circle":
        current_tool = "circle"
    else:
        current_tool = "polygon"
    reset_draw_state()
    editing_template = tpl.copy()
    toast.show(f"编辑: {tpl['id']}")


def delete_selected():
    global selected_index
    if selected_index < 0:
        toast.show("请先选中模板")
        return
    name = furniture_templates[selected_index]["id"]
    furniture_templates.pop(selected_index)
    selected_index = min(selected_index, len(furniture_templates) - 1)
    reset_draw_state()
    input_name.set_text("")
    input_family.set_text("")
    if selected_index >= 0:
        load_template_into_editor(selected_index)
    toast.show(f"已删除: {name}")


def copy_selected_template():
    global editing_template, selected_index, draw_phase
    if selected_index < 0:
        toast.show("请先选中要复制的模板")
        return
    src = furniture_templates[selected_index]
    new_tpl = copy.deepcopy(src)
    new_name = f"{src['id']}_copy"
    new_family = src.get("product_family", src["id"])
    new_tpl["id"] = new_name
    new_tpl["product_family"] = new_family
    new_tpl["roi"] = lookup_roi(new_family)
    editing_template = new_tpl
    selected_index = -1
    draw_phase = "idle"
    input_name.set_text(new_name)
    input_family.set_text(new_family)
    toast.show(f"已复制 {src['id']}，请修改名称和 Product Family 后保存")


def handle_toolbar(action):
    global current_tool, selected_index
    if action.startswith("tool:"):
        current_tool = action.split(":", 1)[1]
        reset_draw_state()
        toast.show(f"工具: {dict(TOOLS)[current_tool]}")
    elif action == "apply":
        save_to_list()
    elif action == "copy":
        copy_selected_template()
    elif action == "write":
        save_to_list()
        write_templates_file()
    elif action == "export":
        path = filedialog_save(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(furniture_templates, f, ensure_ascii=False, indent=2)
            toast.show(f"已导出: {os.path.basename(path)}")
    elif action == "import":
        path = filedialog_open(filetypes=[("JSON", "*.json")])
        if path:
            load_templates_file(path)
    elif action == "delete":
        delete_selected()
    elif action == "clear":
        reset_draw_state()
        input_name.set_text("")
        input_family.set_text("")
        selected_index = -1
        toast.show("画布已清空")


def handle_canvas_mousedown(mx, my, button):
    global draw_phase, drag_start, drag_current, polygon_points, preview_point, editing_template, selected_index
    global l_outer_corners, l_cut_preview, resizing_handle
    wx, wy = screen_to_world(mx, my)
    wx, wy = snap_grid(wx, wy)

    if button == 3:
        return "pan"

    if draw_phase == "idle" and editing_template:
        handle = hit_resize_handle(mx, my)
        if handle is not None:
            resizing_handle = handle
            return

    if current_tool == "polygon":
        if draw_phase == "idle":
            draw_phase = "drawing"
        ref = polygon_points[-1] if polygon_points else None
        wx, wy = snap_point(wx, wy, ref)
        polygon_points.append((wx, wy))
        return

    if draw_phase == "l_cut":
        if not l_outer_corners:
            toast.show("L 形外框丢失，请重新绘制")
            draw_phase = "idle"
            return
        x0, y0, x1, y1 = l_outer_corners
        pts = polygon_from_l_shape(x0, y0, x1, y1, wx, wy)
        editing_template = template_to_dict(
            input_name.get_text() or "l_shape",
            input_family.get_text() or input_name.get_text() or "l_shape",
            "polygon",
            pts,
        )
        draw_phase = "idle"
        l_outer_corners = None
        l_cut_preview = None
        toast.show("L 形已生成，可调整名称和 ROI 后保存")
        return

    draw_phase = "drawing"
    drag_start = (wx, wy)
    drag_current = (wx, wy)


def handle_canvas_mouseup(mx, my, button):
    global draw_phase, drag_current, editing_template, selected_index, l_outer_corners
    if button != 1 or draw_phase != "drawing" or not drag_start:
        return
    wx, wy = screen_to_world(mx, my)
    drag_current = snap_point(wx, wy, drag_start)

    if current_tool == "rect":
        pts = polygon_from_rect(*drag_start, *drag_current)
        if abs(pts[1][0] - pts[0][0]) < 10 or abs(pts[2][1] - pts[1][1]) < 10:
            toast.show("矩形太小，请重新拖拽")
            draw_phase = "idle"
            return
        editing_template = template_to_dict(
            input_name.get_text() or "rectangle",
            input_family.get_text() or input_name.get_text() or "rectangle",
            "rect",
            pts,
        )
        draw_phase = "idle"
        selected_index = -1
        toast.show("矩形已生成，填写名称后点保存")
    elif current_tool == "circle":
        pts = polygon_from_circle(drag_start[0], drag_start[1], math.hypot(drag_current[0] - drag_start[0], drag_current[1] - drag_start[1]))
        if math.hypot(drag_current[0] - drag_start[0], drag_current[1] - drag_start[1]) < 10:
            toast.show("圆形太小，请重新拖拽")
            draw_phase = "idle"
            return
        editing_template = template_to_dict(
            input_name.get_text() or "circle",
            input_family.get_text() or input_name.get_text() or "circle",
            "circle",
            pts,
        )
        draw_phase = "idle"
        selected_index = -1
        toast.show("圆形已生成，填写名称后点保存")
    elif current_tool == "l_shape":
        if abs(drag_current[0] - drag_start[0]) < 10 or abs(drag_current[1] - drag_start[1]) < 10:
            toast.show("外框太小，请重新拖拽")
            draw_phase = "idle"
            return
        l_outer_corners = (drag_start[0], drag_start[1], drag_current[0], drag_current[1])
        draw_phase = "l_cut"
        toast.show("外框完成，再点击内角位置")


def handle_sidebar_click(mx, my, tool_buttons, buttons, list_top):
    for tool_id, btn in tool_buttons.items():
        if btn.contains((mx, my)):
            handle_toolbar(btn.action)
            return True
    for btn in buttons.values():
        if btn.contains((mx, my)):
            handle_toolbar(btn.action)
            return True
    if input_name.contains((mx, my)):
        input_name.active = True
        input_family.active = False
        return True
    if input_family.contains((mx, my)):
        input_family.active = True
        input_name.active = False
        return True
    input_name.active = input_family.active = False

    y = list_top + 28
    for i in range(len(furniture_templates)):
        row = pygame.Rect(12, y + i * 46, SIDEBAR_WIDTH - 24, 40)
        if row.collidepoint(mx, my):
            load_template_into_editor(i)
            return True
    return False


def main():
    global screen, clock
    global offset_x, offset_y, scale, dragging_view, last_mouse_pos, mouse_pos
    global draw_phase, drag_current, preview_point, polygon_points, l_cut_preview, resizing_handle, editing_template
    global editing_template, selected_index

    reload_roi_map()

    if os.path.isfile(TEMPLATES_FILE):
        try:
            load_templates_file()
        except Exception as exc:
            show_error("加载模板失败", str(exc))

    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("家具模板编辑器")
    clock = pygame.time.Clock()

    tool_buttons, buttons, list_top = build_sidebar()
    running = True

    while running:
        mouse_pos = pygame.mouse.get_pos()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.MOUSEWHEEL:
                mx, my = mouse_pos
                wx, wy = screen_to_world(mx, my)
                scale = max(0.01, min(2.0, scale * (1.15 if event.y > 0 else 1 / 1.15)))
                offset_x = wx - (mx - SIDEBAR_WIDTH) / scale
                offset_y = wy - my / scale

            elif event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                if mx < SIDEBAR_WIDTH:
                    handle_sidebar_click(mx, my, tool_buttons, buttons, list_top)
                elif event.button == 1:
                    result = handle_canvas_mousedown(mx, my, 1)
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
                    if resizing_handle is not None:
                        resizing_handle = None
                        toast.show("尺寸已更新")
                    elif event.pos[0] >= SIDEBAR_WIDTH:
                        handle_canvas_mouseup(*event.pos, 1)

            elif event.type == pygame.MOUSEMOTION:
                mx, my = event.pos
                if resizing_handle is not None:
                    wx, wy = screen_to_world(mx, my)
                    apply_resize(resizing_handle, wx, wy)
                elif dragging_view:
                    offset_x += (last_mouse_pos[0] - mx) / scale
                    offset_y += (last_mouse_pos[1] - my) / scale
                    last_mouse_pos = (mx, my)
                elif draw_phase == "drawing" and drag_start and current_tool != "polygon":
                    wx, wy = screen_to_world(mx, my)
                    drag_current = snap_point(wx, wy, drag_start)
                elif current_tool == "polygon" and polygon_points:
                    wx, wy = screen_to_world(mx, my)
                    preview_point = snap_point(wx, wy, polygon_points[-1])
                elif draw_phase == "l_cut" and l_outer_corners:
                    wx, wy = screen_to_world(mx, my)
                    l_cut_preview = (wx, wy)
                else:
                    preview_point = None
                    l_cut_preview = None

            elif event.type == pygame.KEYDOWN:
                active = input_name.active or input_family.active
                box = input_name if input_name.active else input_family
                if active:
                    if event.key == pygame.K_BACKSPACE:
                        box.text = box.text[:-1]
                    elif event.key == pygame.K_ESCAPE:
                        box.active = False
                    elif event.unicode and event.unicode.isprintable():
                            box.text += event.unicode
                elif current_tool == "polygon":
                    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and len(polygon_points) >= 3:
                        editing_template = template_to_dict(
                            input_name.get_text() or "polygon",
                            input_family.get_text() or input_name.get_text() or "polygon",
                            "polygon",
                            polygon_points,
                        )
                        polygon_points = []
                        draw_phase = "idle"
                        preview_point = None
                        selected_index = -1
                        toast.show("多边形完成，可保存到列表")
                    elif event.key == pygame.K_ESCAPE:
                        polygon_points = []
                        draw_phase = "idle"
                        preview_point = None
                elif event.key == pygame.K_s and event.mod & pygame.KMOD_CTRL:
                    save_to_list()
                    write_templates_file()

        draw_canvas(screen)
        draw_sidebar(tool_buttons, buttons, list_top)
        toast.draw(screen, SIDEBAR_WIDTH + (SCREEN_WIDTH - SIDEBAR_WIDTH) // 2)
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        traceback.print_exc()
        show_error("启动失败", f"{exc}\n\n请运行: python check_env.py")
        if sys.platform == "win32":
            input("\n按 Enter 退出...")
        raise SystemExit(1) from exc
