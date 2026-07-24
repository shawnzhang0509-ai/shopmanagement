try:
    import pygame
except ModuleNotFoundError:
    print("未找到 pygame。Python 3.14 请安装: python -m pip install pygame-ce")
    raise SystemExit(1) from None

import sys
import math
import json
import tkinter as tk
from tkinter import filedialog

pygame.init()

# 初始化 Tkinter
root = tk.Tk()
root.withdraw()

SCREEN_WIDTH, SCREEN_HEIGHT = 1200, 700
LEFT_PANEL_WIDTH = 250
RIGHT_PANEL_RECT = pygame.Rect(LEFT_PANEL_WIDTH, 0, SCREEN_WIDTH - LEFT_PANEL_WIDTH, SCREEN_HEIGHT)

screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Furniture & Obstacles Layout Editor")

FONT = pygame.font.SysFont("Microsoft YaHei", 24)
font = pygame.font.SysFont(None, 20)
MARK_FONT = pygame.font.SysFont("Microsoft YaHei", 12)
SMALL_FONT = pygame.font.SysFont("Microsoft YaHei", 16)

clock = pygame.time.Clock()

GRID_SPACING = 100  # 100mm = 10cm网格大小

offset_x, offset_y = 0.0, 0.0
scale = 0.011875  # 初始缩放比例

dragging_view = False
last_mouse_pos = (0, 0)

drawing_polygon = False
current_polygon = []

selected_collision = None
collision_polygons = []

selected_furniture = None
dragging_furniture = None
selected_feature = None
placed_furnitures = []

renaming_obstacle = False
input_text = ""
preview_point = None
zoom_in_factor = 1.25
zoom_out_factor = 0.8
max_scale = 5.0
min_scale = 0.002

dragging_view = False
last_mouse_pos = (0, 0)

selected_template_index = 0

selected_vertex = None  # (障碍物索引, 顶点索引)
dragging_vertex = False

search_text = ""
search_result = ""
search_box_active = False

is_in_command_model = False  # 是否处于命令模型模式
ctrl_press_time = 0
ctrl_pressed_once = False

save_layout_file = "saved_layout.json"
load_layout_file = "saved_layout.json"

# 在主循环 while running: 之前（例如函数顶部）加这几行：
dragging_furniture = None

def point_in_polygon(x, y, poly):
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside



def start_drag_view(pos):
    global dragging_view, last_mouse_pos
    dragging_view = True
    last_mouse_pos = pos

def add_obstacle_point(mx, my):
    global current_polygon
    wx = offset_x + (mx - LEFT_PANEL_WIDTH) / scale
    wy = offset_y + my / scale
    if current_polygon:
        last_px, last_py = current_polygon[-1]
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
            dx = abs(wx - last_px)
            dy = abs(wy - last_py)
            if dx > dy:
                wy = last_py
            else:
                wx = last_px
    current_polygon.append((wx, wy))
    print(f"添加障碍物点: ({wx:.1f}, {wy:.1f})")
        
def draw_current_polygon(screen, current_polygon, preview_point, offset_x, offset_y, scale):
    draw_points = [((x - offset_x) * scale + LEFT_PANEL_WIDTH, (y - offset_y) * scale)
                   for x, y in current_polygon]

    if preview_point:
        px = (preview_point[0] - offset_x) * scale + LEFT_PANEL_WIDTH
        py = (preview_point[1] - offset_y) * scale
        draw_points.append((px, py))

    # 绘制线条
    if len(draw_points) >= 2:
        pygame.draw.lines(screen, (0, 0, 255), False, draw_points, 2)

    # 绘制点
    for pt in draw_points:
        pygame.draw.circle(screen, (0, 255, 255), (int(pt[0]), int(pt[1])), 5)

def roi_to_color(roi):
    # 限定roi范围，假设roi是0-10区间
    roi = max(0, min(10, roi))
    
    # 起点颜色 - 淡蓝 light blue
    start_color = (173, 216, 230)  # R, G, B
    
    # 终点颜色 - 深红 firebrick
    end_color = (178, 34, 34)
    
    # 计算比例（0~1）
    t = roi / 10
    
    # 线性插值计算每个颜色通道
    r = int(start_color[0] + t * (end_color[0] - start_color[0]))
    g = int(start_color[1] + t * (end_color[1] - start_color[1]))
    b = int(start_color[2] + t * (end_color[2] - start_color[2]))
    
    return (r, g, b)

def check_collision(furniture, collision_polygons):
    pts = furniture.get_rotated_points()
    for col in collision_polygons:
        poly = col["points"]
        for px, py in pts:
            if point_in_poly(px, py, poly):
                return True
    return False

def point_in_poly(x, y, poly):
    inside = False
    n = len(poly)
    p1x, p1y = poly[0]
    for i in range(n+1):
        p2x, p2y = poly[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y-p1y)*(p2x-p1x)/(p2y-p1y)+p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside

def screen_to_world(sx, sy, offset_x, offset_y, scale):
    wx = offset_x + (sx - LEFT_PANEL_WIDTH) / scale
    wy = offset_y + sy / scale
    return wx, wy

class Furniture:
    def __init__(self, name, roi, points, x=0, y=0, rotation=0):
        self.name = name
        self.roi = roi
        self.points = points
        self.x = x
        self.y = y
        self.rotation = rotation

    def rotate_by(self, angle):
        self.rotation = (self.rotation + angle) % 360

    def get_rotated_points(self):
        cx = sum(p[0] for p in self.points) / len(self.points)
        cy = sum(p[1] for p in self.points) / len(self.points)
        rad = math.radians(self.rotation)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        rotated = []
        for px, py in self.points:
            rx, ry = px - cx, py - cy
            rrx = rx * cos_a - ry * sin_a
            rry = rx * sin_a + ry * cos_a
            rotated.append((rrx + cx + self.x, rry + cy + self.y))
        return rotated

    def draw(self, surface, offset_x, offset_y, scale):
        pts = self.get_rotated_points()
        screen_pts = [((x - offset_x) * scale + LEFT_PANEL_WIDTH, (y - offset_y) * scale) for x, y in pts]
        fill_color = roi_to_color(self.roi)
        pygame.draw.polygon(surface, fill_color, screen_pts)
        pygame.draw.polygon(surface, (0, 0, 0), screen_pts, 2)
        cx = sum(x for x, _ in screen_pts) / len(screen_pts)
        cy = sum(y for _, y in screen_pts) / len(screen_pts)
        text_surf = MARK_FONT.render(self.name, True, (0, 0, 0))
        
        text_rect = text_surf.get_rect(midtop=(cx, cy + 10))
        surface.blit(text_surf, text_rect)

    def is_clicked(self, mx, my, offset_x, offset_y, scale):
        wx = offset_x + (mx - LEFT_PANEL_WIDTH) / scale
        wy = offset_y + my / scale
        pts = self.get_rotated_points()
        return point_in_poly(wx, wy, self.get_rotated_points())


def shape_to_points(item):
    shape_type = item.get("type", "")
    if shape_type == "polygon":
        return item.get("points", [])
    elif shape_type == "rectangle":
        w, h = item.get("width", 0), item.get("height", 0)
        return [(0, 0), (w, 0), (w, h), (0, h)]
    elif shape_type == "circle":
        r = item.get("radius", 0)
        num_points = 20
        points = []
        for i in range(num_points):
            angle = 2 * math.pi * i / num_points
            x = r * math.cos(angle)
            y = r * math.sin(angle)
            points.append((x, y))
        return points
    elif shape_type == "l_shape":
        w, h = item.get("width", 0), item.get("height", 0)
        cw, ch = item.get("cut_width", 0), item.get("cut_height", 0)
        return [(0, 0), (w, 0), (w, ch), (cw, ch), (cw, h), (0, h)]
    else:
        return []


def load_furniture_templates(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    templates = []
    for item in data:
        roi = item.get("roi", 0)
        points = shape_to_points(item)
        if points:
            templates.append(Furniture(item.get("id", "unnamed"), roi, points))
    return templates


furniture_templates = load_furniture_templates("furniture_templates.json")

def draw_instructions(surface):
    instructions = [
         "[鼠标操作]",
         "<- 左转   -> 右转",
        "左键：选中 / 添加点 / 拖动物体",
        "右键拖动：移动视图",
        "滚轮：缩放视图",
        "",
        "[快捷键]",
        "P：绘制障碍物",
        "Shift：水平/垂直线段",
        "Enter：完成障碍物",
        "R：重命名障碍物",
        "Backspace/Delete：删除选中项",
        "S：保存布局",
        "L：加载布局",
        "Esc：取消重命名",
        # 可以根据需要补充更多说明
    ]
    y = 280  # 说明文字起始y坐标，调整合适位置
    for line in instructions:
        txt = SMALL_FONT.render(line, True, (50, 50, 50))
        surface.blit(txt, (10, y))
        y += 25

def redraw_state_label(surface):
    global is_in_command_model
    mode_text = "Mode: COMMAND" if is_in_command_model else "Mode: NORMAL"
    mode_surf = SMALL_FONT.render(mode_text, True, (0, 0, 0))
    mode_x = 10  # 离左边10像素
    mode_y = SCREEN_HEIGHT - 30  # 离底部30像素
    surface.blit(mode_surf, (mode_x, mode_y))

def draw_sidebar(surface):
    global search_text
    global is_in_command_model, selected_feature
    pygame.draw.rect(surface, (230, 230, 230), (0, 0, LEFT_PANEL_WIDTH, SCREEN_HEIGHT))
    title = FONT.render("家具模板", True, (0, 0, 0))
    surface.blit(title, (10, 10))
    y = 40
    for i, tpl in enumerate(furniture_templates):
        color = (255, 0, 0) if i == selected_template_index else (0, 0, 0)
        txt = FONT.render(tpl.name, True, color)
        surface.blit(txt, (10, y))
        y += 30

    draw_instructions(surface)

    SMALL_FONT = pygame.font.SysFont(None, 16)

    LABEL_FONT = pygame.font.SysFont(None, 20)
    btn_rect = pygame.Rect(10, y + 10, 110, 20)
    pygame.draw.rect(surface, (100, 200, 100), btn_rect)
    btn_text = SMALL_FONT.render("ADD FURNITURE", True, (0, 0, 0))
    surface.blit(btn_text, (btn_rect.x + 10, btn_rect.y + 5))

    input_box_rect = pygame.Rect(10, btn_rect.bottom + 10, LEFT_PANEL_WIDTH - 20, 20)
    pygame.draw.rect(surface, (255, 255, 255), input_box_rect, 0)
    pygame.draw.rect(surface, (0, 0, 0), input_box_rect, 1)
    input_surf = SMALL_FONT.render(search_text, True, (0, 0, 0))
    surface.blit(input_surf, (input_box_rect.x + 5, input_box_rect.y + 5))

    search_btn_rect = pygame.Rect(130, y + 10, 70, 20)
    pygame.draw.rect(surface, (100, 150, 250), search_btn_rect)
    search_surf = SMALL_FONT.render("SEARCH", True, (0, 0, 0))
    surface.blit(search_surf, (search_btn_rect.x + 10, search_btn_rect.y + 5))

    if selected_feature is not None:
        label_text = f"selected: {selected_feature.name}"
        label_surf = LABEL_FONT.render(label_text, True, (255, 0, 0))
        label_y = input_box_rect.bottom + 15
        surface.blit(label_surf, (input_box_rect.x, label_y))

    mode_text = "Mode: EDIT" if is_in_command_model else "Mode: NORMAL"
    mode_surf = SMALL_FONT.render(mode_text, True, (0, 0, 0))
    mode_x = 10  # 离左边10像素
    mode_y = SCREEN_HEIGHT - 30  # 离底部30像素
    surface.blit(mode_surf, (mode_x, mode_y))

    return [btn_rect, input_box_rect, search_btn_rect]


def draw_grid(surface, offset_x, offset_y, scale):
    grid_color = (200, 200, 200)
    start_x = int(offset_x // GRID_SPACING * GRID_SPACING)
    end_x = int((offset_x + (SCREEN_WIDTH - LEFT_PANEL_WIDTH) / scale) // GRID_SPACING * GRID_SPACING + GRID_SPACING)
    start_y = int(offset_y // GRID_SPACING * GRID_SPACING)
    end_y = int((offset_y + SCREEN_HEIGHT / scale) // GRID_SPACING * GRID_SPACING + GRID_SPACING)

    for x in range(start_x, end_x, GRID_SPACING):
        sx = LEFT_PANEL_WIDTH + (x - offset_x) * scale
        pygame.draw.line(surface, grid_color, (sx, 0), (sx, SCREEN_HEIGHT))
    for y in range(start_y, end_y, GRID_SPACING):
        sy = (y - offset_y) * scale
        pygame.draw.line(surface, grid_color, (LEFT_PANEL_WIDTH, sy), (SCREEN_WIDTH, sy))


def draw_collision_polygons(surface, offset_x, offset_y, scale):
    for idx, col in enumerate(collision_polygons):
        poly = col["points"]
        screen_pts = [((x - offset_x) * scale + LEFT_PANEL_WIDTH, (y - offset_y) * scale) for x, y in poly]
        fill_color = (200, 100, 100)
        border_color = (150, 0, 0)
        if idx == selected_collision:
            fill_color = (255, 180, 180)
            border_color = (255, 0, 0)
        pygame.draw.polygon(surface, fill_color, screen_pts)
        pygame.draw.polygon(surface, border_color, screen_pts, 2)
        cx = sum(p[0] for p in screen_pts) / len(screen_pts)
        cy = sum(p[1] for p in screen_pts) / len(screen_pts)
        name_surf = FONT.render(col["name"], True, (100, 0, 0))
        name_rect = name_surf.get_rect(center=(cx, cy))
        surface.blit(name_surf, name_rect)
   
    if drawing_polygon and len(current_polygon) >= 1:
        # 先绘制已确定的边
        screen_points = []
        for px, py in current_polygon:
            sx = LEFT_PANEL_WIDTH + (px - offset_x) * scale
            sy = (py - offset_y) * scale
            screen_points.append((sx, sy))

        if len(screen_points) >= 2:
            pygame.draw.lines(screen, (255, 0, 0), False, screen_points, 2)
        elif len(screen_points) == 1:
            pygame.draw.circle(screen, (255, 0, 0), screen_points[0], 4)

        # 显示已画边的最后一条边长度（单位米）
        if len(current_polygon) >= 2:
            (x1, y1), (x2, y2) = current_polygon[-2], current_polygon[-1]
            length_m = math.hypot(x2 - x1, y2 - y1) / 1000  # 单位转换

            sx1, sy1 = screen_points[-2]
            sx2, sy2 = screen_points[-1]
            mid_x = (sx1 + sx2) / 2
            mid_y = (sy1 + sy2) / 2

            label = font.render(f"{length_m:.2f} m", True, (0, 0, 0))
            screen.blit(label, (mid_x + 5, mid_y - 15))

        # 动态绘制当前鼠标点与最后点的连线和距离
        mx, my = pygame.mouse.get_pos()
        world_mx = offset_x + (mx - LEFT_PANEL_WIDTH) / scale
        world_my = offset_y + my / scale

        last_x, last_y = current_polygon[-1]

        # 计算距离，单位米
        dist_m = math.hypot(world_mx - last_x, world_my - last_y) / 1000  # 根据你数据单位调整

        # 画辅助线
        sx_last = LEFT_PANEL_WIDTH + (last_x - offset_x) * scale
        sy_last = (last_y - offset_y) * scale
        pygame.draw.line(screen, (0, 255, 0), (sx_last, sy_last), (mx, my), 2)

        # 显示动态距离文字
        mid_x_dyn = (sx_last + mx) / 2
        mid_y_dyn = (sy_last + my) / 2
        label_dyn = font.render(f"{dist_m:.2f} m", True, (0, 128, 0))
        screen.blit(label_dyn, (mid_x_dyn + 5, mid_y_dyn - 15))



        # 3. 鼠标位置 → 世界坐标
        mx, my = pygame.mouse.get_pos()
        wx = offset_x + (mx - LEFT_PANEL_WIDTH) / scale
        wy = offset_y + my / scale

        # 4. Shift 对齐处理（在世界坐标中操作）
        last_px, last_py = current_polygon[-1]
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
            dx = abs(wx - last_px)
            dy = abs(wy - last_py)
            if dx > dy:
                wy = last_py
            else:
                wx = last_px

        # 5. 转为屏幕坐标
        current_sx = LEFT_PANEL_WIDTH + (wx - offset_x) * scale
        current_sy = (wy - offset_y) * scale
        last_sx = LEFT_PANEL_WIDTH + (last_px - offset_x) * scale
        last_sy = (last_py - offset_y) * scale

        # 6. 绘制绿色临时线段
        pygame.draw.line(screen, (0, 255, 0), (last_sx, last_sy), (current_sx, current_sy), 2)

        # 7. 显示距离
        dx = wx - last_px
        dy = wy - last_py
        length = math.hypot(dx, dy)
        mid_sx = (last_sx + current_sx) / 2
        mid_sy = (last_sy + current_sy) / 2

        text = font.render(f"{length:.1f} m", True, (0, 128, 0))
        pygame.draw.rect(screen, (255, 230, 230), (mid_sx + 5, mid_sy - 5, 60, 20))
        screen.blit(text, (mid_sx + 5, mid_sy - 5))
    
        # 计算线段长度，单位像素
        length = math.hypot(current_sx - last_sx, current_sy - last_sy)
        
        # 文字显示长度
        text_surface = font.render(f"{length:.1f} px", True, (0, 128, 0))
        
        mid_x = (last_sx + current_sx) / 2
        mid_y = (last_sy + current_sy) / 2
        
        # 画背景框让文字更清晰
        text_bg_rect = pygame.Rect(mid_x + 5, mid_y - 5, text_surface.get_width() + 10, text_surface.get_height() + 4)
        pygame.draw.rect(screen, (255, 200, 200), text_bg_rect)
        
        # 画文字
        screen.blit(text_surface, (mid_x + 10, mid_y - 3))

def point_in_polygon(x, y, polygon):
    num = len(polygon)
    j = num - 1
    c = False
    for i in range(num):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and \
           (x < (xj - xi) * (y - yi) / (yj - yi + 1e-6) + xi):
            c = not c
        j = i
    return c

def screen_to_world(mx, my, offset_x, offset_y, scale):
    wx = offset_x + (mx - LEFT_PANEL_WIDTH) / scale
    wy = offset_y + my / scale
    return wx, wy

def popup_save_dialog():
    global save_layout_file

    save_layout_file = filedialog.asksaveasfilename(
        defaultextension=".json",
        filetypes=[("JSON files", "*.json")],
        title="Save Layout",
    )

    if save_layout_file:
        save_layout(save_layout_file)

def save_layout(filepath="saved_layout.json"):
    data = {
        "furnitures": [
            {
                "name": f.name,
                "roi": f.roi,
                "x": f.x,
                "y": f.y,
                "rotation": f.rotation,
                "points": f.points
            } for f in placed_furnitures
        ],
        "obstacles": collision_polygons
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"布局已保存至 {filepath}")

def popup_load_dialog():
    global load_layout_file
    load_layout_file = filedialog.askopenfilename(
        defaultextension=".json",
        filetypes=[("JSON files", "*.json")],
        title="Load layout",
    )
    if load_layout_file:
        try:
            with open(load_layout_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                load_layout(load_layout_file)
        except Exception as e:
            print(f"load layout file failed: {e}")

def load_layout(filepath="saved_layout.json"):
    global placed_furnitures, collision_polygons
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        placed_furnitures = []
        collision_polygons = []

        for f in data.get("furnitures", []):
            furniture = Furniture(
                name=f["name"],
                roi=f["roi"],
                points=f["points"]
            )
            furniture.x = f.get("x", 0)
            furniture.y = f.get("y", 0)
            furniture.rotation = f.get("rotation", 0)
            placed_furnitures.append(furniture)

        collision_polygons = data.get("obstacles", [])

        print(f"✅ 布局已从 {filepath} 成功加载！家具数：{len(placed_furnitures)}，障碍物数：{len(collision_polygons)}")

    except Exception as e:
        print(f"❌ 加载布局失败：{e}")

def draw_rename_input_box(surface):
    if renaming_obstacle:
        box_width, box_height = 400, 100
        box_x = LEFT_PANEL_WIDTH + 100
        box_y = 100

        # 背景框
        pygame.draw.rect(surface, (255, 255, 255), (box_x, box_y, box_width, box_height))
        pygame.draw.rect(surface, (0, 0, 0), (box_x, box_y, box_width, box_height), 2)

        # 提示文字
        title_text = f"Renaming: {collision_polygons[selected_collision]['name']}" if selected_collision is not None else "Renaming:"
        title_surf = FONT.render(title_text, True, (0, 0, 0))
        surface.blit(title_surf, (box_x + 10, box_y + 10))

        # 当前输入内容
        input_surf = FONT.render(input_text, True, (0, 0, 200))
        surface.blit(input_surf, (box_x + 10, box_y + 50))


def main():
    global offset_x, offset_y, scale, dragging_view, last_mouse_pos
    global drawing_polygon, current_polygon
    global selected_collision, selected_furniture, dragging_furniture
    global placed_furnitures, selected_template_index
    global dragging_collision, collision_drag_offset  # <== 新增这行
    global renaming_obstacle, input_text
    global selected_vertex, dragging_vertex
    # 你的其他 global 声明不变

    MAX_VERTEX_SELECT_DIST = 10  # 以屏幕像素为单位，选顶点的最大距离

    dragging_collision = False    # <== 初始化变量
    collision_drag_offset = (0, 0) # <== 初始化变量

    running = True
    add_furniture_btn_rect = None
    add_input_box_rect = None
    add_search_btn_rect = None

    offset_x = -((SCREEN_WIDTH - LEFT_PANEL_WIDTH) / 2) / scale
    offset_y = -SCREEN_HEIGHT / 2 / scale


    while running:
        mx, my = pygame.mouse.get_pos()
        for event in pygame.event.get():
            global search_text, search_result, search_box_active
            global ctrl_press_time, ctrl_pressed_once, is_in_command_model, selected_feature

            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.MOUSEWHEEL:
                 world_x = offset_x + (mx - LEFT_PANEL_WIDTH) / scale
                 world_y = offset_y + my / scale

                # 使用指数式缩放因子
                 zoom_in_factor = 1.25
                 zoom_out_factor = 0.8
                 max_scale = 0.5
                 min_scale = 0.002

                 if event.y > 0:  # 滚轮上（Zoom In）
                     scale *= zoom_in_factor
                 elif event.y < 0:  # 滚轮下（Zoom Out）
                     scale *= zoom_out_factor

                # 限制缩放范围
                 scale = max(min_scale, min(max_scale, scale))

                # 缩放后重新计算 offset，保持缩放中心在鼠标位置
                 offset_x = world_x - (mx - LEFT_PANEL_WIDTH) / scale
                 offset_y = world_y - my / scale

            elif event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                if event.button == 3:
                    dragging_view = True
                    last_mouse_pos = event.pos  # 这里要用 event.pos

                elif event.button == 1:
                    wx = offset_x + (mx - LEFT_PANEL_WIDTH) / scale
                    wy = offset_y + my / scale

                    # 输入框点击检测
                    if add_input_box_rect and add_input_box_rect.collidepoint(mx, my):
                        search_box_active = True
                    else:
                        search_box_active = False

                    # 搜索按钮点击检测
                    if add_search_btn_rect and add_search_btn_rect.collidepoint(mx, my):
                        global search_text, search_result
                        if len(search_text) > 0:
                            search_result = f"搜索结果：你输入的是：{search_text}"
                            print(search_result)
                        if len(search_text) > 0:
                            user_input = search_text.strip().lower()
                            matched = None

                            for i, tpl in enumerate(furniture_templates):
                                if user_input in tpl.name.lower():  # 模糊匹配：输入是 id 的子串
                                    matched = i
                                    break

                            if matched is not None:
                                selected_template_index = matched
                                tpl = furniture_templates[matched]
                                print(f"选中家具模板: {tpl.name} ROI: {tpl.roi}")
                            else:
                                print("没有找到匹配的家具模板。")

                    if drawing_polygon:
                        current_polygon.append((wx, wy))
                        print(f"添加障碍物点: ({wx:.1f}, {wy:.1f})")

                    else:
                        # 先尝试选中家具
                        selected_furniture = None
                        for f in reversed(placed_furnitures):
                            if f.is_clicked(mx, my, offset_x, offset_y, scale):
                                dragging_furniture = f
                                f.dragging = True
                                selected_furniture = f
                                selected_feature = f
                                selected_collision = None
                                break
                        if selected_furniture is None:
                            # 没点中家具，处理左面板点击或障碍物选中
                            if mx < LEFT_PANEL_WIDTH:
                                # 左侧面板逻辑
                                y_start = 40
                                for i, tpl in enumerate(furniture_templates):
                                    if y_start <= my <= y_start + 24:
                                        selected_template_index = i
                                        print(f"选中家具模板: {tpl.name} ROI: {tpl.roi}")
                                        break
                                    y_start += 30

                            # 添加按钮逻辑
                            if add_furniture_btn_rect and add_furniture_btn_rect.collidepoint(mx, my):
                                tpl = furniture_templates[selected_template_index]
                                new_furn = Furniture(tpl.name, tpl.roi, tpl.points)
                                new_furn.x = offset_x + (SCREEN_WIDTH - LEFT_PANEL_WIDTH) / 2 / scale
                                new_furn.y = offset_y + SCREEN_HEIGHT / 2 / scale
                                placed_furnitures.append(new_furn)
                                print(f"添加家具: {new_furn.name} ROI: {new_furn.roi}")
                            else:
                            
                             # 右侧地图区域逻辑，检测障碍物选中

                            # 先检测障碍物（你需要写这个函数或逻辑）
                                for i, poly in enumerate(collision_polygons):
                                    if point_in_polygon(wx, wy, poly["points"]):
                                        selected_collision = i
                                        dragging_collision = True
                                        # 计算多边形中心点
                                        poly_points = poly["points"]
                                        poly_center_x = sum(p[0] for p in poly_points) / len(poly_points)
                                        poly_center_y = sum(p[1] for p in poly_points) / len(poly_points)
                                        collision_drag_offset = (poly_center_x - wx, poly_center_y - wy)
                                        print(f"选中障碍物: {poly['name']}")
                                        break
            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 3:
                    dragging_view = False
                elif event.button == 1:
                    if dragging_furniture:
                        dragging_furniture.dragging = False
                        dragging_furniture = None
                        selected_furniture = None  # 可选：放开后取消选中
                    if dragging_collision:
                        dragging_collision = False

       
            elif event.type == pygame.MOUSEMOTION:
                mx, my = event.pos
                wx = offset_x + (mx - LEFT_PANEL_WIDTH) / scale
                wy = offset_y + my / scale

                if dragging_view:
                    dx = (last_mouse_pos[0] - mx) / scale
                    dy = (last_mouse_pos[1] - my) / scale
                    offset_x += dx
                    offset_y += dy
                    last_mouse_pos = (mx, my)

                elif dragging_vertex and selected_vertex is not None:
                    poly_index, vertex_index = selected_vertex
                    poly = collision_polygons[poly_index]
                    poly["points"][vertex_index] = (wx, wy)

                elif dragging_furniture and dragging_furniture.dragging:
                    new_x, new_y = wx, wy
                    old_x, old_y = dragging_furniture.x, dragging_furniture.y
                    dragging_furniture.x, dragging_furniture.y = new_x, new_y

                    if check_collision(dragging_furniture, collision_polygons):
                        dragging_furniture.x, dragging_furniture.y = old_x, old_y

                elif dragging_collision and selected_collision is not None:
                    new_cx = wx + collision_drag_offset[0]
                    new_cy = wy + collision_drag_offset[1]
                    poly = collision_polygons[selected_collision]
                    old_points = poly["points"]
                    cx = sum(p[0] for p in old_points) / len(old_points)
                    cy = sum(p[1] for p in old_points) / len(old_points)
                    dx = new_cx - cx
                    dy = new_cy - cy
                    poly["points"] = [(x + dx, y + dy) for x, y in old_points]

                else:
                    # 非拖动状态下的 hover 检查
                    if drawing_polygon:
                     if current_polygon:
                        last_px, last_py = current_polygon[-1]
                        keys = pygame.key.get_pressed()
                        if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
                            dx = abs(wx - last_px)
                            dy = abs(wy - last_py)
                            if dx > dy:
                                wy = last_py
                            else:
                                wx = last_px
                        preview_point = (wx, wy)  # 先保存预览点，不添加到current_polygon
                    else:
                        preview_point = None

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 3:
                    dragging_view = False
                elif event.button == 1:
                    if dragging_furniture:
                        dragging_furniture.dragging = False
                        dragging_furniture = None
                    if dragging_collision:
                        dragging_collision = False

            elif event.type == pygame.KEYDOWN:
                if search_box_active:
                    print(f"键值: {event.key}, unicode: {repr(event.unicode)}")
                    
                    if event.key == pygame.K_BACKSPACE:
                        search_text = search_text[:-1]
                    elif event.key == pygame.K_RETURN:
                        if len(search_text) > 0:
                            search_result = f"搜索结果：你输入的是：{search_text}"
                            print(search_result)
                    else:
                        if len(event.unicode) == 1 and event.unicode.isprintable():
                            search_text += event.unicode

                if renaming_obstacle:
                    if event.key == pygame.K_RETURN:
                        if selected_collision is not None and input_text.strip():
                            collision_polygons[selected_collision]["name"] = input_text.strip()
                            print(f"障碍物重命名为: {input_text.strip()}")
                        renaming_obstacle = False
                        input_text = ""
                    elif event.key == pygame.K_BACKSPACE:
                        input_text = input_text[:-1]
                    else:
                        input_text += event.unicode
                elif drawing_polygon:
                    if event.key == pygame.K_RETURN:
                        if len(current_polygon) >= 3:
                            collision_polygons.append({
                                "name": f"Obstacle{len(collision_polygons)+1}",
                                "points": current_polygon.copy()
                            })
                            print(f"[回车] 完成一个障碍物，共 {len(current_polygon)} 点")
                        else:
                            print("障碍物点数不足，未保存")
                        current_polygon.clear()
                        drawing_polygon = False
                        preview_point = None
                else:
                    if (event.key == pygame.K_BACKSPACE or event.key == pygame.K_DELETE) and is_in_command_model:
                        if selected_furniture is not None:
                            print(f"删除家具: {selected_furniture.name}")
                            placed_furnitures.remove(selected_furniture)
                            selected_furniture = None
                        elif selected_collision is not None:
                            print(f"删除障碍物: {collision_polygons[selected_collision]['name']}")
                            collision_polygons.pop(selected_collision)
                            selected_collision = None

                    elif event.key == pygame.K_p and is_in_command_model:
                        drawing_polygon = not drawing_polygon
                        if drawing_polygon:
                            current_polygon = []
                            print("进入障碍物绘制模式（点击右侧区域添加点）")
                        else:
                            print("取消绘制")
                    elif event.key == pygame.K_r and is_in_command_model:
                        if selected_collision is not None:
                            renaming_obstacle = True
                            input_text = collision_polygons[selected_collision]["name"]
                            print(f"开始重命名障碍物: 当前名称为 {input_text}")

                    elif event.key == pygame.K_BACKSPACE and is_in_command_model:
                        input_text = input_text[:-1]  # 删除最后一个字符

                    elif event.key == pygame.K_ESCAPE and is_in_command_model:
                        print("取消重命名")
                        renaming_obstacle = False

                    elif event.key == pygame.K_RETURN and drawing_polygon and len(current_polygon) >= 3:
                        name = f"Obstacle{len(collision_polygons)+1}"
                        collision_polygons.append({
                            "name": name,
                            "points": current_polygon[:]
                        })
                        print(f"完成障碍物: {name}")
                        current_polygon = []
                        drawing_polygon = False
                    elif event.key == pygame.K_LCTRL:
                        current_time = pygame.time.get_ticks()

                        if ctrl_pressed_once:
                            time_diff = current_time - ctrl_press_time
                            if time_diff <= 1000:
                                is_in_command_model = not is_in_command_model
                                redraw_state_label(screen)
                                ctrl_pressed_once = False
                            else:
                                # 超时，作为新的第一次按下
                                ctrl_press_time = current_time
                        else:
                            ctrl_pressed_once = True
                            ctrl_press_time = current_time
                    elif event.key == pygame.K_s and is_in_command_model:
                        popup_save_dialog()
                    elif event.key == pygame.K_l and is_in_command_model:
                        popup_load_dialog()
                    elif event.key == pygame.K_LEFT and is_in_command_model:
                         if selected_feature:
                            selected_feature.rotate_by(-15)
                    elif event.key == pygame.K_RIGHT and is_in_command_model:
                        if selected_feature:
                            selected_feature.rotate_by(15)
                    pass

        screen.fill((255, 255, 255))
        pygame.draw.rect(screen, (230, 230, 230), (0, 0, LEFT_PANEL_WIDTH, SCREEN_HEIGHT))
        pygame.draw.rect(screen, (245, 245, 245), RIGHT_PANEL_RECT)

        draw_grid(screen, offset_x, offset_y, scale)
        
        element_arr = draw_sidebar(screen)

        add_furniture_btn_rect = element_arr[0]
        add_input_box_rect = element_arr[1]
        add_search_btn_rect = element_arr[2]

        for f in placed_furnitures:
            f.draw(screen, offset_x, offset_y, scale)
                
        draw_collision_polygons(screen, offset_x, offset_y, scale)

        if drawing_polygon:
            draw_current_polygon(screen, current_polygon, preview_point, offset_x, offset_y, scale)
        if renaming_obstacle:
            draw_rename_input_box(screen)


        # 显示比例尺
        pixels_per_meter = scale * 1000  # 1m 对应的像素数

        # 设定比例尺长度，最大显示100px，按比例缩放
        if pixels_per_meter > 500:
            bar_length = 500
            label_text = "10 m"
            pixels_per_unit = pixels_per_meter / 10
        elif pixels_per_meter < 10:
            bar_length = int(pixels_per_meter * 100)  # 转换成厘米单位
            bar_length = min(bar_length, 100)
            label_text = "10 m"
            pixels_per_unit = pixels_per_meter / 0.1
        else:
            bar_length = int(pixels_per_meter)
            label_text = "1 m"
            pixels_per_unit = pixels_per_meter
            
        bar_length = max(10, min(bar_length, 500))

        pygame.draw.line(screen, (0, 0, 0),
                         (LEFT_PANEL_WIDTH + 20, SCREEN_HEIGHT - 30),
                         (LEFT_PANEL_WIDTH + 20 + bar_length, SCREEN_HEIGHT - 30), 3)

        label = font.render(label_text, True, (0, 0, 0))
        screen.blit(label, (LEFT_PANEL_WIDTH + 20, SCREEN_HEIGHT - 50))
        # 文字显示


        pygame.display.flip()
        clock.tick(60)
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
