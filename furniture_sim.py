import pygame
import json
import sys
import tkinter as tk
from tkinter import filedialog

pygame.init()

# ----- Global Constants -----
SCREEN_WIDTH, SCREEN_HEIGHT = 700, 600
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Furniture Template Manager")
FONT = pygame.font.SysFont(None, 18)
clock = pygame.time.Clock()

# 初始化 Tkinter
root = tk.Tk()
root.withdraw()

# ----- InputBox Class -----
class InputBox:
    def __init__(self, x, y, w, h, label, text='', is_name=False):
        self.rect = pygame.Rect(x, y, w, h)
        self.color_inactive = pygame.Color('lightskyblue3')
        self.color_active = pygame.Color('dodgerblue2')
        self.color = self.color_inactive
        self.text = text
        self.label = label
        self.is_name = is_name
        self.txt_surface = FONT.render(text, True, (0, 0, 0))
        self.active = False
        self.cleared = False

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                self.active = True
                if not self.cleared:
                    self.text = ''
                    self.cleared = True
            else:
                self.active = False
            self.color = self.color_active if self.active else self.color_inactive

        elif event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.key == pygame.K_RETURN:
                self.active = False
                self.color = self.color_inactive
            else:
                if self.is_name:
                    if event.unicode.isprintable():
                        self.text += event.unicode
                else:
                    if event.unicode.isdigit():
                        self.text += event.unicode
            self.txt_surface = FONT.render(self.text, True, (0, 0, 0))

    def draw(self, screen):
        label_surf = FONT.render(self.label, True, (0, 0, 0))
        screen.blit(label_surf, (self.rect.x, self.rect.y - 18))
        screen.blit(self.txt_surface, (self.rect.x + 5, self.rect.y + 5))
        pygame.draw.rect(screen, self.color, self.rect, 2)

    def get_text(self):
        return self.text.strip()
    
    def set_text(self, text):
        self.text = text
        self.txt_surface = FONT.render(self.text, True, (0, 0, 0))
        self.cleared = True

    def get_value(self):
        try:
            return int(self.text)
        except ValueError:
            return 0
    def set_value(self, value):
        self.text = str(value)
        self.txt_surface = FONT.render(self.text, True, (0, 0, 0))
        self.cleared = True  # 避免再次点击时清空

# ----- Input Boxes and Controls -----
input_name = InputBox(140, 70, 120, 20, "Template Name", is_name=True)
input_w = InputBox(140, 110, 80, 20, "Width")
input_h = InputBox(240, 110, 80, 20, "Height")
input_radius = InputBox(140, 140, 80, 20, "Radius")
input_cut_w = InputBox(140, 170, 80, 20, "Cut Width")
input_cut_h = InputBox(240, 170, 80, 20, "Cut Height")

btn_save_rect = pygame.Rect(140, 155, 180, 35)
btn_export_rect = pygame.Rect(140, 200, 180, 35)
btn_import_rect = pygame.Rect(140, 245, 180, 35)
preview_rect = pygame.Rect(400, 60, 260, 260)

shape_types = ["rectangle", "circle", "l_shape"]
selected_shape_index = 0
furniture_templates = []

# ----- UI Drawing -----
def draw_ui():
    screen.fill((240, 240, 240))
    screen.blit(FONT.render("Furniture Shape:", True, (0, 0, 0)), (20, 20))

    for i, stype in enumerate(shape_types):
        color = (100, 200, 100) if i == selected_shape_index else (180, 180, 180)
        rect = pygame.Rect(140 + i * 90, 20, 80, 25)
        pygame.draw.rect(screen, color, rect)
        screen.blit(FONT.render(stype, True, (0, 0, 0)), (rect.x + 8, rect.y + 5))

    input_name.draw(screen)
    shape = shape_types[selected_shape_index]
    if shape == "rectangle":
        input_w.draw(screen)
        input_h.draw(screen)
    elif shape == "circle":
        input_radius.draw(screen)
    elif shape == "l_shape":
        input_w.draw(screen)
        input_h.draw(screen)
        input_cut_w.draw(screen)
        input_cut_h.draw(screen)

    pygame.draw.rect(screen, (100, 200, 100), btn_save_rect)
    screen.blit(FONT.render("Save Template", True, (0, 0, 0)), (btn_save_rect.x + 30, btn_save_rect.y + 10))

    pygame.draw.rect(screen, (100, 100, 250), btn_export_rect)
    screen.blit(FONT.render("Export JSON", True, (255, 255, 255)), (btn_export_rect.x + 30, btn_export_rect.y + 10))

    pygame.draw.rect(screen, (100, 100, 250), btn_import_rect)
    screen.blit(FONT.render("Import JSON", True, (255, 255, 255)), (btn_import_rect.x + 30, btn_import_rect.y + 10))

    screen.blit(FONT.render("Templates:", True, (0, 0, 0)), (20, 300))
    for i, tpl in enumerate(furniture_templates):
        label = f"{tpl['id']} ({tpl['type']})"
        screen.blit(FONT.render(label, True, (0, 0, 0)), (40, 330 + i * 20))

    pygame.draw.rect(screen, (230, 230, 230), preview_rect)
    pygame.draw.rect(screen, (0, 0, 0), preview_rect, 1)
    draw_preview(preview_rect)

# ----- Shape Preview -----

import math
def draw_preview(area):
    shape = shape_types[selected_shape_index]
    ox, oy = area.x + 10, area.y + 10
    maxw, maxh = area.width - 20, area.height - 20

    if shape == "rectangle":
        w = input_w.get_value()
        h = input_h.get_value()
        if w > 0 and h > 0:
            scale = min(maxw / w, maxh / h, 2)
            points = [(0, 0), (w, 0), (w, h), (0, h)]
            scaled_points = [(ox + x * scale, oy + y * scale) for x, y in points]
            pygame.draw.polygon(screen, (200, 150, 100), scaled_points)
            pygame.draw.polygon(screen, (0, 0, 0), scaled_points, 2)

    elif shape == "circle":
        r = input_radius.get_value()
        if r > 0:
            scale = min(maxw / (2 * r), maxh / (2 * r), 2)
            cx, cy = ox + r * scale, oy + r * scale
            points = []
            num_points = 20  # 多边形顶点数，越大越圆
            for i in range(num_points):
                angle = 2 * math.pi * i / num_points
                x = cx + r * scale * math.cos(angle)
                y = cy + r * scale * math.sin(angle)
                points.append((x, y))
            pygame.draw.polygon(screen, (100, 200, 200), points)
            pygame.draw.polygon(screen, (0, 0, 0), points, 2)


    elif shape == "l_shape":
        w = input_w.get_value()
        h = input_h.get_value()
        cw = input_cut_w.get_value()
        ch = input_cut_h.get_value()
        if w > 0 and h > 0 and cw < w and ch < h:
            points = [(0, 0), (w, 0), (w, ch), (cw, ch), (cw, h), (0, h)]
            scale = min(maxw / w, maxh / h, 2)
            scaled = [(ox + x * scale, oy + y * scale) for x, y in points]
            pygame.draw.polygon(screen, (180, 150, 220), scaled)
            pygame.draw.polygon(screen, (0, 0, 0), scaled, 2)

# ----- Polygon Generator -----
def generate_lshape_polygon(w, h, cw, ch):
    return [[0, 0], [w, 0], [w, ch], [cw, ch], [cw, h], [0, h]]

def popup_save_dialog():
    global save_template_file

    save_template_file = filedialog.asksaveasfilename(
        defaultextension=".json",
        filetypes=[("JSON files", "*.json")],
        title="Save template",
    )

    if save_template_file:
        try:
            with open(save_template_file, "w") as f:
                json.dump(furniture_templates, f, indent=2)
            print(f"Exported to {save_template_file}")
        except Exception as e:
            print("Export failed:", e)

def popup_load_dialog():
    global load_template_file
    load_template_file = filedialog.askopenfilename(
        defaultextension=".json",
        filetypes=[("JSON files", "*.json")],
        title="Load template",
    )
    if load_template_file:
        try:
            load_template(load_template_file)
        except Exception as e:
            print(f"load template file failed: {e}")
            
def load_template(file_path):
    global furniture_templates
    with open(file_path, 'r', encoding='utf-8') as f:
        furniture_templates = json.load(f)
    if furniture_templates:
        first_item = furniture_templates[0]
        shape_type = first_item['type']
        print(f"显示第一个家具模板: ID={first_item['id']}, 类型={shape_type}")

        if shape_type == "rectangle":
            input_name.set_text(first_item['id'])
            input_w.set_value(first_item['width'])
            input_h.set_value(first_item['height'])
            selected_shape_index = shape_types.index("rectangle")

        elif shape_type == "circle":
            input_name.set_text(first_item['id'])
            input_radius.set_value(first_item['radius'])
            selected_shape_index = shape_types.index("circle")

        elif shape_type == "polygon":
            input_name.set_text(first_item['id'])
            selected_shape_index = shape_types.index("l_shape")

            # ⚠️ 尝试从 polygon 的点反推出 w, h, cut_w, cut_h（仅适用于标准 L 型）
            try:
                points = first_item['points']
                # 假设点顺序为：
                # [(0,0), (w,0), (w,h), (cw,h), (cw,ch), (0,ch)]
                w = points[1][0]
                h = points[2][1]
                cw = points[3][0]
                ch = points[4][1]

                input_w.set_value(w)
                input_h.set_value(h)
                input_cut_w.set_value(cw)
                input_cut_h.set_value(ch)
            except Exception as e:
                print("无法从 polygon 点自动还原 l_shape 参数:", e)

        else:
            print("JSON 数据为空，未加载任何模板")
            print(f"Loaded template from {file_path}")


# ----- Main Loop -----
running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        if event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos
            for i in range(len(shape_types)):
                if pygame.Rect(140 + i * 90, 20, 80, 25).collidepoint(mx, my):
                    selected_shape_index = i

            if btn_save_rect.collidepoint(mx, my):
                name = input_name.get_text() or f"{shape_types[selected_shape_index]}_{len(furniture_templates)+1}"
                shape = shape_types[selected_shape_index]

                if shape == "rectangle":
                    w, h = input_w.get_value(), input_h.get_value()
                    if w > 0 and h > 0:
                        furniture_templates.append({"id": name, "type": "rectangle", "width": w, "height": h})

                elif shape == "circle":
                    r = input_radius.get_value()
                    if r > 0:
                        furniture_templates.append({"id": name, "type": "circle", "radius": r})

                elif shape == "l_shape":
                    w, h = input_w.get_value(), input_h.get_value()
                    cw, ch = input_cut_w.get_value(), input_cut_h.get_value()
                    if w > 0 and h > 0 and cw < w and ch < h:
                        furniture_templates.append({"id": name, "type": "polygon", "points": generate_lshape_polygon(w, h, cw, ch)})

            if btn_export_rect.collidepoint(mx, my):
                popup_save_dialog()
            if btn_import_rect.collidepoint(mx, my):
                popup_load_dialog()

        for box in [input_name, input_w, input_h, input_radius, input_cut_w, input_cut_h]:
            box.handle_event(event)

    draw_ui()
    pygame.display.flip()
    clock.tick(30)

pygame.quit()
sys.exit()
