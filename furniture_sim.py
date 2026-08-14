import json
import math
import os
import sys
import traceback
import copy

# IME / 中文输入：须在 import pygame 之前设置
os.environ.setdefault("SDL_IME_SHOW_UI", "1")
os.environ.setdefault("SDL_IME_SUPPORT_EXTENDED_TEXT", "1")

try:
    import pygame
except ModuleNotFoundError:
    print("未找到 pygame。Python 3.14 请安装: python -m pip install pygame-ce")
    if __name__ == "__main__":
        input("\n按 Enter 退出...")
    raise SystemExit(1) from None

from roi_lookup import lookup_roi, reload_roi_map
from display_lookup import (
    SHOPS,
    filter_items,
    group_by_family,
    last_load_error,
    last_load_source,
    last_family_column,
    load_display_items,
    match_template_index,
    reload_display_items,
    shop_stats,
    shops_for_display_tabs,
)
from product_images import is_image_failed, prefetch_urls, request_thumbnail

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
C_SIDEBAR_TEXT = ui.C_SIDEBAR_TEXT
C_SIDEBAR_MUTED = ui.C_SIDEBAR_MUTED
C_SIDEBAR_ACTIVE = ui.C_SIDEBAR_ACTIVE
C_SIDEBAR_HOVER = ui.C_SIDEBAR_HOVER
C_SIDEBAR = ui.C_SIDEBAR
C_SIDEBAR_DARK = ui.C_SIDEBAR_DARK
C_SUCCESS = ui.C_SUCCESS
INPUT_TEXT = ui.INPUT_TEXT
FONT_TITLE = ui.FONT_TITLE
FONT_BODY = ui.FONT_BODY
FONT_SMALL = ui.FONT_SMALL
FONT_LABEL = ui.FONT_LABEL
FONT_MARK = ui.FONT_MARK
Button = ui.Button
draw_sidebar_bg = ui.draw_sidebar_bg
draw_sidebar_header = ui.draw_sidebar_header

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
dragging_shape = False
drag_shape_last_world = None

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
editing_mode = "new"  # "new" = 新绘制/副本, "edit" = 修改列表中已有项
_template_clipboard = None  # 内存中的模板剪贴板（Ctrl+C/V 整模板复制）

input_name = ui.InputBox((0, 0, 0, 0), placeholder="例如 corner_sofa")
input_family = ui.InputBox((0, 0, 0, 0), placeholder="例如 corner_sofa")
input_search = ui.InputBox((0, 0, 0, 0), placeholder="搜索名称或 Product Family…")
_last_input_click = {"box": None, "time": 0}

FOCUS_ZONES = ("name", "family")
focus_zone = "canvas"
app_screen = "gallery"  # editor | gallery
gallery_mode = "display"  # display | templates
display_shop = "all"
selected_display_key = None
display_items = []
_pending_input_focus = None
_pending_focus_frames = 0
_sidebar_click_start = None  # (x, y) mouse-down position for click-vs-drag
_last_list_pick = {"index": -1, "time": 0}
_last_gallery_pick = {"index": -1, "time": 0}
CLICK_MOVE_TOLERANCE = 10
return_to_gallery_after_edit = False
_gallery_snapshot: dict | None = None


class GalleryView:
    """全屏总览：Display 大库（按门店）+ 已测绘模板库。"""

    TOP_H = 96
    SHOP_H = 36
    FAMILY_H = 40
    SUB_FAMILY_H = 34
    CARD_W = 140
    CARD_H = 120
    CARD_GAP = 14
    PAD = 28
    FAMILY_GAP = 24
    SCROLLBAR_W = 12
    SCROLLBAR_MARGIN = 6

    def __init__(self):
        self.scroll_y = 0
        self.back_btn = Button((0, 0, 0, 0), "← 返回绘制", "gallery_back")
        self.refresh_btn = Button((0, 0, 0, 0), "刷新", "display_refresh")
        self._layout = []
        self._cards = []  # (rect, kind, data) kind: template|display
        self._shop_tabs: list[tuple[pygame.Rect, str]] = []
        self._mode_tabs: list[tuple[pygame.Rect, str]] = []
        self._layout_key: tuple | None = None
        self._content_h = 0
        self._scroll_drag = False
        self._scroll_drag_offset = 0
        self._last_sw = 0

    def _filtered_displays(self):
        return filter_items(display_items, display_shop, input_search.get_text())

    def group_templates(self, templates):
        query = input_search.get_text().lower().strip()
        groups = {}
        for i, tpl in enumerate(templates):
            family = tpl.get("product_family") or tpl.get("id", "未分类")
            tid = tpl.get("id", "")
            if query and query not in family.lower() and query not in tid.lower():
                continue
            groups.setdefault(family, []).append((i, tpl))
        return sorted(groups.items(), key=lambda item: item[0].lower())

    def invalidate_layout(self) -> None:
        self._layout_key = None

    def _layout_cache_key(self, templates, screen_w: int) -> tuple:
        return (
            screen_w,
            gallery_mode,
            display_shop,
            input_search.get_text(),
            len(display_items),
            len(templates),
            id(display_items),
        )

    def _ensure_layout(self, templates, screen_w: int) -> int:
        key = self._layout_cache_key(templates, screen_w)
        if key != self._layout_key or screen_w != self._last_sw:
            self._content_h = self.build_layout(templates, screen_w)
            self._layout_key = key
            self._last_sw = screen_w
        return self._content_h

    def _view_height(self, screen_h: int) -> int:
        return screen_h - self.TOP_H

    def scrollbar_geometry(
        self, screen_w: int, screen_h: int, content_h: int
    ) -> tuple[pygame.Rect | None, pygame.Rect | None, int]:
        view_h = self._view_height(screen_h)
        if content_h <= view_h:
            return None, None, 0
        track = pygame.Rect(
            screen_w - self.SCROLLBAR_W - self.SCROLLBAR_MARGIN,
            self.TOP_H + self.SCROLLBAR_MARGIN,
            self.SCROLLBAR_W,
            view_h - self.SCROLLBAR_MARGIN * 2,
        )
        thumb_h = max(40, int(track.height * view_h / content_h))
        max_scroll = max(0, content_h - view_h)
        ratio = self.scroll_y / max_scroll if max_scroll else 0
        thumb_y = track.y + int((track.height - thumb_h) * ratio)
        thumb = pygame.Rect(track.x, thumb_y, track.width, thumb_h)
        return track, thumb, max_scroll

    def scroll_to_thumb_center(self, my: int, screen_h: int, content_h: int) -> None:
        track, thumb, max_scroll = self.scrollbar_geometry(self._last_sw, screen_h, content_h)
        if not track or not thumb or max_scroll <= 0:
            return
        rel = (my - self._scroll_drag_offset - track.y) / max(1, track.height - thumb.height)
        rel = max(0.0, min(1.0, rel))
        self.scroll_y = int(rel * max_scroll)

    def begin_scroll_drag(self, mx: int, my: int, screen_h: int) -> bool:
        track, thumb, max_scroll = self.scrollbar_geometry(self._last_sw, screen_h, self._content_h)
        if not track or not thumb:
            return False
        if thumb.collidepoint(mx, my):
            self._scroll_drag = True
            self._scroll_drag_offset = my - thumb.centery
            return True
        if track.collidepoint(mx, my):
            self._scroll_drag = True
            self._scroll_drag_offset = thumb.height // 2
            self.scroll_to_thumb_center(my, screen_h, self._content_h)
            return True
        return False

    def update_scroll_drag(self, my: int, screen_h: int) -> None:
        if self._scroll_drag:
            self.scroll_to_thumb_center(my, screen_h, self._content_h)

    def end_scroll_drag(self) -> None:
        self._scroll_drag = False

    def draw_scrollbar(self, surface, screen_w: int, screen_h: int, content_h: int) -> None:
        track, thumb, _ = self.scrollbar_geometry(screen_w, screen_h, content_h)
        if not track or not thumb:
            return
        pygame.draw.rect(surface, (220, 224, 230), track, border_radius=6)
        pygame.draw.rect(surface, (140, 148, 160), thumb, border_radius=6)

    def _prefetch_visible_images(self, screen_h: int) -> None:
        if gallery_mode != "display":
            return
        urls: list[str] = []
        for item in self._layout:
            if item[0] != "card_disp":
                continue
            _, rect, disp_item, _ = item
            sy = self.TOP_H + rect.y - self.scroll_y
            if sy > screen_h or sy + self.CARD_H < self.TOP_H:
                continue
            if getattr(disp_item, "image_url", ""):
                urls.append(disp_item.image_url)
        prefetch_urls(urls, limit=32)

    def build_layout_templates(self, templates, screen_w: int):
        self._layout = []
        self._cards = []
        y = self.PAD
        for family, tpls in self.group_templates(templates):
            rois = [t.get("roi", 0) or 0 for _, t in tpls]
            avg_roi = sum(rois) / max(len(rois), 1)
            self._layout.append(("family", family, len(tpls), avg_roi, y))
            y += self.FAMILY_H
            x = self.PAD
            row_y = y
            for idx, tpl in sorted(tpls, key=lambda x: x[1].get("id", "").lower()):
                if x + self.CARD_W > screen_w - self.PAD:
                    x = self.PAD
                    row_y += self.CARD_H + self.CARD_GAP
                rect = pygame.Rect(x, row_y, self.CARD_W, self.CARD_H)
                self._layout.append(("card_tpl", rect, idx, tpl))
                self._cards.append((rect, "template", idx))
                x += self.CARD_W + self.CARD_GAP
            y = row_y + self.CARD_H + self.FAMILY_GAP
        return y + self.PAD

    def build_layout_display(self, templates, screen_w: int):
        self._layout = []
        self._cards = []
        y = self.PAD
        filtered = self._filtered_displays()
        for family, items in group_by_family(filtered):
            modeled = sum(1 for it in items if match_template_index(it, templates) >= 0)
            self._layout.append(("family", family, len(items), modeled, y))
            y += self.FAMILY_H
            x = self.PAD
            row_y = y
            for item in sorted(items, key=lambda it: it.product_name.lower()):
                if x + self.CARD_W > screen_w - self.PAD:
                    x = self.PAD
                    row_y += self.CARD_H + self.CARD_GAP
                rect = pygame.Rect(x, row_y, self.CARD_W, self.CARD_H)
                tpl_idx = match_template_index(item, templates)
                self._layout.append(("card_disp", rect, item, tpl_idx))
                self._cards.append((rect, "display", item.key))
                x += self.CARD_W + self.CARD_GAP
            y = row_y + self.CARD_H + self.FAMILY_GAP
        return y + self.PAD

    def build_layout(self, templates, screen_w: int):
        if gallery_mode == "display":
            return self.build_layout_display(templates, screen_w)
        return self.build_layout_templates(templates, screen_w)

    def scroll(self, delta: int):
        self.scroll_y = max(0, self.scroll_y + delta)

    def clamp_scroll(self, content_h: int, screen_h: int):
        view_h = screen_h - self.TOP_H
        self.scroll_y = min(self.scroll_y, max(0, content_h - view_h))

    def content_y(self, my: int) -> int:
        return my - self.TOP_H + self.scroll_y

    def handle_click(self, mx: int, my: int):
        if self.back_btn.contains((mx, my)):
            return "back"
        if self.refresh_btn.contains((mx, my)):
            return "refresh"
        for rect, mode in self._mode_tabs:
            if rect.collidepoint(mx, my):
                return f"mode:{mode}"
        for rect, shop_id in self._shop_tabs:
            if rect.collidepoint(mx, my):
                return f"shop:{shop_id}"
        if input_search.contains((mx, my)):
            return None
        if my < self.TOP_H:
            return None
        cy = self.content_y(my)
        for rect, kind, data in self._cards:
            if rect.collidepoint(mx, cy):
                if kind == "template":
                    return data
                return ("display", data)
        return None

    def _draw_header_tabs(self, surface, sw: int, templates):
        self._mode_tabs = []
        self._shop_tabs = []
        x = 20
        y = 10
        for mode, label in (("display", "Display 库"), ("templates", "已测绘")):
            w = 108
            rect = pygame.Rect(x, y, w, 28)
            active = gallery_mode == mode
            bg = C_SIDEBAR_ACTIVE if active else C_SIDEBAR_HOVER
            pygame.draw.rect(surface, bg, rect, border_radius=6)
            surface.blit(FONT_SMALL.render(label, True, (255, 255, 255)), (rect.x + 12, rect.y + 7))
            self._mode_tabs.append((rect, mode))
            x += w + 8

        input_search.rect = pygame.Rect(250, 10, min(360, sw - 560), 28)
        input_search.draw(surface, None, on_dark=True)

        stats = shop_stats(display_items, templates) if display_items else {}
        if gallery_mode == "display" and stats.get("all"):
            s = stats["all"]
            label = f"已测绘 {s['modeled']}/{s['total']}"
        else:
            label = f"共 {len(templates)} 个"
        surface.blit(FONT_SMALL.render(label, True, C_SIDEBAR_MUTED), (input_search.rect.right + 10, 16))

        self.refresh_btn.rect = pygame.Rect(sw - 248, 10, 72, 28)
        self.refresh_btn.draw(surface, mouse_pos, on_dark=True)
        self.back_btn.rect = pygame.Rect(sw - 148, 10, 128, 28)
        self.back_btn.draw(surface, mouse_pos, on_dark=True)

        if gallery_mode == "display":
            x = 20
            y = 52
            for shop, st in shops_for_display_tabs(display_items, templates):
                sid = shop["id"]
                if sid == "all":
                    text = f"全部 {st['total']}"
                else:
                    fam_n = st.get("families", 0)
                    text = f"{shop['label']} {fam_n}族 {st['modeled']}/{st['total']}"
                w = max(88, FONT_SMALL.size(text)[0] + 20)
                rect = pygame.Rect(x, y, w, self.SHOP_H - 4)
                active = display_shop == sid
                bg = C_ACCENT if active else C_SIDEBAR
                pygame.draw.rect(surface, bg, rect, border_radius=6)
                surface.blit(FONT_SMALL.render(text, True, (255, 255, 255)), (rect.x + 10, rect.y + 8))
                self._shop_tabs.append((rect, sid))
                x += w + 8
                if x > sw - 40:
                    break

    def draw(self, surface, templates, selected_index: int):
        sw, sh = surface.get_width(), surface.get_height()
        surface.fill((245, 247, 250))
        pygame.draw.rect(surface, C_SIDEBAR_DARK, (0, 0, sw, self.TOP_H))

        title = "Display 大库" if gallery_mode == "display" else "已测绘模板"
        if gallery_mode == "display":
            surface.blit(FONT_TITLE.render(title, True, C_SIDEBAR_TEXT), (20, 58))
            surface.blit(FONT_MARK.render("按 Product Family 分组 · 双击测绘/编辑 · 右侧滑块滚动", True, C_SIDEBAR_MUTED), (168, 62))

        self._draw_header_tabs(surface, sw, templates)

        content_h = self._ensure_layout(templates, sw)
        self.clamp_scroll(content_h, sh)
        self._prefetch_visible_images(sh)

        viewport = pygame.Rect(0, self.TOP_H, sw - self.SCROLLBAR_W - 4, sh - self.TOP_H)
        clip = surface.get_clip()
        surface.set_clip(viewport)

        for item in self._layout:
            if item[0] == "family":
                _, family, count, extra, y = item
                sy = self.TOP_H + y - self.scroll_y
                if sy > sh or sy + self.FAMILY_H < self.TOP_H:
                    continue
                bar = pygame.Rect(self.PAD, sy, sw - self.PAD * 2, self.FAMILY_H - 4)
                pygame.draw.rect(surface, C_SIDEBAR, bar, border_radius=6)
                surface.blit(FONT_LABEL.render(family, True, (255, 255, 255)), (bar.x + 14, bar.y + 6))
                if gallery_mode == "display":
                    meta = f"{count} 款 Display  ·  已测绘 {extra}/{count}"
                else:
                    meta = f"{count} 款  ·  ROI {extra:.1f}"
                meta_surf = FONT_SMALL.render(meta, True, C_SIDEBAR_MUTED)
                surface.blit(meta_surf, (bar.right - meta_surf.get_width() - 14, bar.y + 12))
            elif item[0] == "card_tpl":
                _, rect, idx, tpl = item
                screen_rect = rect.move(0, self.TOP_H - self.scroll_y)
                if screen_rect.bottom < self.TOP_H or screen_rect.top > sh:
                    continue
                selected = idx == selected_index
                draw_template_card(surface, tpl, screen_rect, selected)
                name = tpl.get("id", "")
                name_surf = FONT_SMALL.render(name, True, INPUT_TEXT if not selected else (255, 255, 255))
                surface.blit(name_surf, (screen_rect.x + 8, screen_rect.bottom - 20))
            elif item[0] == "card_disp":
                _, rect, disp_item, tpl_idx = item
                screen_rect = rect.move(0, self.TOP_H - self.scroll_y)
                if screen_rect.bottom < self.TOP_H or screen_rect.top > sh:
                    continue
                tpl = templates[tpl_idx] if tpl_idx >= 0 else None
                selected = disp_item.key == selected_display_key
                draw_display_card(surface, disp_item, tpl, screen_rect, selected, display_shop)

        surface.set_clip(clip)

        self.draw_scrollbar(surface, sw, sh, content_h)

        err = last_load_error()
        if gallery_mode == "display" and err and not display_items:
            banner = FONT_SMALL.render(f"⚠ {err[:90]}", True, (200, 80, 60))
            surface.blit(banner, (self.PAD, sh - 28))
        elif gallery_mode == "display" and display_items and last_load_source():
            src = last_load_source()
            fam_col = last_family_column()
            hint = f"数据源: {src}"
            if fam_col:
                hint += f" · Family列: {fam_col}"
            with_img = sum(1 for it in display_items if getattr(it, "image_url", ""))
            if with_img:
                hint += f" · 有图链接 {with_img}/{len(display_items)}"
            else:
                hint += " · 无 ImageUrl，请重新 grab_display"
            err = last_load_error()
            if err and display_items and "未读到有效" in (err or ""):
                hint += f" · {err[:70]}"
            surface.blit(FONT_MARK.render(hint, True, C_SIDEBAR_MUTED), (self.PAD, sh - 22))


gallery_view = GalleryView()


def draw_display_card(surface, item, tpl, rect, selected=False, shop_id="all"):
    has_model = tpl is not None
    inner = rect.inflate(-10, -36)
    inner.height = max(48, inner.height)
    thumb_surf = None
    if not has_model and getattr(item, "image_url", ""):
        thumb_surf = request_thumbnail(item.image_url)

    if has_model:
        draw_template_card(surface, tpl, rect, selected)
        pygame.draw.circle(surface, C_SUCCESS, (rect.right - 14, rect.top + 14), 7)
        pygame.draw.circle(surface, (255, 255, 255), (rect.right - 14, rect.top + 14), 7, 2)
    else:
        bg = (235, 238, 242) if not selected else (220, 228, 238)
        border = (190, 198, 208) if not selected else C_ACCENT
        pygame.draw.rect(surface, bg, rect, border_radius=8)
        pygame.draw.rect(surface, border, rect, 2 if selected else 1, border_radius=8)
        if thumb_surf is not None:
            scaled = pygame.transform.smoothscale(thumb_surf, (inner.width, inner.height))
            surface.blit(scaled, inner.topleft)
        else:
            pygame.draw.rect(surface, (210, 218, 226), inner, 2, border_radius=4)
            if not getattr(item, "image_url", ""):
                label = "待测绘"
            elif is_image_failed(item.image_url):
                label = "无图"
            else:
                label = "加载中…"
            wait = FONT_MARK.render(label, True, C_MUTED)
            surface.blit(wait, wait.get_rect(center=inner.center))

    name = item.product_name
    if len(name) > 16:
        name = name[:15] + "…"
    name_surf = FONT_SMALL.render(name, True, INPUT_TEXT if not selected else (255, 255, 255))
    surface.blit(name_surf, (rect.x + 8, rect.bottom - 34))
    qty = item.display_qty_for_shop(shop_id)
    qty_surf = FONT_MARK.render(f"Display ×{qty}", True, C_SUCCESS if has_model else C_MUTED)
    surface.blit(qty_surf, (rect.x + 8, rect.bottom - 18))


def draw_template_card(surface, tpl, rect, selected=False):
    bg = C_SIDEBAR_ACTIVE if selected else (255, 255, 255)
    border = C_ACCENT if selected else (210, 218, 226)
    pygame.draw.rect(surface, bg, rect, border_radius=8)
    pygame.draw.rect(surface, border, rect, 2 if selected else 1, border_radius=8)
    preview = rect.inflate(-12, -28)
    preview.height = max(40, preview.height)
    points = normalize_template_dict(tpl)
    if len(points) < 2:
        return
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    bw, bh = max(max_x - min_x, 1), max(max_y - min_y, 1)
    pad = 6
    sc = min((preview.width - pad * 2) / bw, (preview.height - pad * 2) / bh)
    cx, cy = preview.centerx, preview.centery
    mid_x, mid_y = (min_x + max_x) / 2, (min_y + max_y) / 2
    screen_pts = [
        (cx + (x - mid_x) * sc, cy + (y - mid_y) * sc) for x, y in points
    ]
    fill = (214, 234, 248) if not selected else (255, 255, 255)
    line = C_ACCENT if not selected else (255, 255, 255)
    if len(screen_pts) >= 3:
        pygame.draw.polygon(surface, fill, screen_pts)
    pygame.draw.lines(surface, line, True, screen_pts, 2)




def focus_input(box):
    global focus_zone, _pending_input_focus, _pending_focus_frames
    input_name.deactivate()
    input_family.deactivate()
    input_search.deactivate()
    if box is input_name:
        input_name.activate()
        focus_zone = "name"
    elif box is input_family:
        input_family.activate()
        focus_zone = "family"
    elif box is input_search:
        input_search.activate()
        focus_zone = "search"
    _pending_input_focus = box
    _pending_focus_frames = 10


def tick_input_focus():
    """Re-attach text input after programmatic focus (copy / Tab) on Windows."""
    global _pending_focus_frames
    if _pending_input_focus and _pending_focus_frames > 0:
        _pending_input_focus.refresh_text_input()
        _pending_focus_frames -= 1
    for box in (input_name, input_family, input_search):
        if box.active:
            box.refresh_text_input()


def handle_input_click(box):
    global _last_input_click
    now = pygame.time.get_ticks()
    is_double = _last_input_click["box"] is box and now - _last_input_click["time"] < 400
    if is_double:
        focus_input(box)
        box.select_all_text()
    elif box.active and box.select_all:
        box.select_all = False
        focus_input(box)
    else:
        focus_input(box)
    _last_input_click = {"box": box, "time": now}


def blur_inputs():
    global focus_zone
    input_name.deactivate()
    input_family.deactivate()
    input_search.deactivate()
    if focus_zone in FOCUS_ZONES:
        focus_zone = "canvas"


def apply_focus_zone():
    input_name.deactivate()
    input_family.deactivate()
    input_search.deactivate()
    if focus_zone == "name":
        input_name.activate()
    elif focus_zone == "family":
        input_family.activate()
    elif focus_zone == "search":
        input_search.activate()


def advance_focus(reverse: bool = False):
    global focus_zone, selected_index
    if focus_zone not in FOCUS_ZONES:
        focus_zone = FOCUS_ZONES[-1] if reverse else FOCUS_ZONES[0]
    else:
        idx = FOCUS_ZONES.index(focus_zone)
        idx = (idx - 1) if reverse else (idx + 1)
        focus_zone = FOCUS_ZONES[idx % len(FOCUS_ZONES)]
    apply_focus_zone()


def handle_enter_action():
    if input_name.active:
        focus_zone = "family"
        apply_focus_zone()
        return True
    if input_family.active:
        if _is_new_entry_mode():
            save_to_list()
        else:
            rename_template()
        return True
    return False


def open_gallery(reset_scroll: bool = True):
    global app_screen, display_items, return_to_gallery_after_edit, _gallery_snapshot
    blur_inputs()
    app_screen = "gallery"
    if reset_scroll:
        gallery_view.scroll_y = 0
    gallery_view.invalidate_layout()
    return_to_gallery_after_edit = False
    _gallery_snapshot = None
    display_items = load_display_items()


def open_editor_from_gallery():
    """从 Display 大库打开测绘/编辑，保留大库滚动与门店筛选。"""
    global app_screen, return_to_gallery_after_edit, _gallery_snapshot
    _gallery_snapshot = {
        "scroll_y": gallery_view.scroll_y,
        "display_shop": display_shop,
        "gallery_mode": gallery_mode,
    }
    return_to_gallery_after_edit = True
    app_screen = "editor"
    input_search.deactivate()


def return_to_gallery_view():
    global app_screen, display_shop, gallery_mode, display_items
    global return_to_gallery_after_edit, _gallery_snapshot
    snap = _gallery_snapshot or {}
    gallery_view.scroll_y = snap.get("scroll_y", 0)
    display_shop = snap.get("display_shop", display_shop)
    gallery_mode = snap.get("gallery_mode", gallery_mode)
    return_to_gallery_after_edit = False
    _gallery_snapshot = None
    app_screen = "gallery"
    display_items = reload_display_items(prefer_db=False)
    gallery_view.invalidate_layout()
    toast.show("已返回 Display 大库")


def close_gallery():
    global app_screen
    app_screen = "editor"
    input_search.deactivate()


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
    sw, sh = surface.get_width(), surface.get_height()
    spacing = 100
    start_x = int(offset_x // spacing * spacing)
    end_x = int((offset_x + (sw - SIDEBAR_WIDTH) / scale) // spacing * spacing + spacing)
    start_y = int(offset_y // spacing * spacing)
    end_y = int((offset_y + sh / scale) // spacing * spacing + spacing)
    for x in range(start_x, end_x, spacing):
        sx = world_to_screen(x, 0)[0]
        pygame.draw.line(surface, C_GRID, (sx, 0), (sx, sh))
    for y in range(start_y, end_y, spacing):
        sy = world_to_screen(0, y)[1]
        pygame.draw.line(surface, C_GRID, (SIDEBAR_WIDTH, sy), (sw, sy))


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


def point_in_polygon(x, y, poly) -> bool:
    if len(poly) < 3:
        return False
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-9) + xi):
            inside = not inside
        j = i
    return inside


def hit_template_body(mx, my) -> bool:
    if not editing_template or draw_phase != "idle":
        return False
    wx, wy = screen_to_world(mx, my)
    return point_in_polygon(wx, wy, normalize_template_dict(editing_template))


def _template_from_points(base: dict, points) -> dict:
    return {
        "id": base.get("id", ""),
        "product_family": base.get("product_family", ""),
        "type": "polygon",
        "points": [[int(round(x)), int(round(y))] for x, y in points],
        "roi": base.get("roi", 0),
    }


def translate_editing_template(dx, dy):
    global editing_template
    if not editing_template or (dx == 0 and dy == 0):
        return
    dx, dy = int(round(dx)), int(round(dy))
    pts = normalize_template_dict(editing_template)
    new_pts = [(x + dx, y + dy) for x, y in pts]
    if editing_template.get("type") in ("rectangle", "circle"):
        editing_template = _template_from_points(editing_template, new_pts)
    elif editing_template.get("type") == "polygon":
        for i, (x, y) in enumerate(new_pts):
            editing_template["points"][i] = [int(round(x)), int(round(y))]
    else:
        editing_template = _template_from_points(editing_template, new_pts)


def snap_template_to_grid():
    if not editing_template:
        return
    pts = normalize_template_dict(editing_template)
    min_x = min(p[0] for p in pts)
    min_y = min(p[1] for p in pts)
    snap_x = round(min_x / GRID_SNAP) * GRID_SNAP
    snap_y = round(min_y / GRID_SNAP) * GRID_SNAP
    translate_editing_template(snap_x - min_x, snap_y - min_y)


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
    sw, sh = surface.get_width(), surface.get_height()
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
    pygame.draw.line(surface, (148, 163, 184), (SIDEBAR_WIDTH, cy), (sw, cy), 1)
    pygame.draw.line(surface, (148, 163, 184), (cx, 0), (cx, sh), 1)

    if current_tool == "polygon" and draw_phase != "idle":
        banner = pygame.Rect(SIDEBAR_WIDTH + 16, 12, sw - SIDEBAR_WIDTH - 32, 34)
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
        tip = "左键拖动形状移动 | 橙色角点调整大小 | Shift 自由定位"
        surface.blit(FONT_SMALL.render(tip, True, C_MUTED), (SIDEBAR_WIDTH + 16, 12))
    elif draw_phase == "idle":
        tip = "自动对齐 10cm 网格 | 按住 Shift 自由绘制"
        surface.blit(FONT_SMALL.render(tip, True, C_MUTED), (SIDEBAR_WIDTH + 16, 12))


def build_sidebar():
    pad = 16
    w = SIDEBAR_WIDTH - pad * 2
    y = 72
    tool_buttons = {}
    bw = (w - 8) // 2
    for i, (tool_id, label) in enumerate(TOOLS):
        col, row = i % 2, i // 2
        rect = (pad + col * (bw + 8), y + row * 38, bw, 32)
        tool_buttons[tool_id] = Button(rect, label, f"tool:{tool_id}", toggle=True)
    y += 38 * 2 + 10

    input_name.rect = pygame.Rect(pad, y + 18, w, 32)
    input_family.rect = pygame.Rect(pad, y + 66, w, 32)
    y += 118

    half = (w - 8) // 2
    buttons = {
        "gallery": Button((pad, y, w, 40), "Display 总览 →", "gallery"),
        "apply": Button((pad, y + 48, w, 38), "保存", "apply", primary=True),
        "rename": Button((pad, y + 94, half, 34), "重命名", "rename"),
        "copy": Button((pad + half + 8, y + 94, half, 34), "复制", "copy"),
        "write": Button((pad, y + 136, w, 34), "写入 JSON", "write"),
        "export": Button((pad, y + 178, half, 34), "导出", "export"),
        "import": Button((pad + half + 8, y + 178, half, 34), "导入", "import"),
        "delete": Button((pad, y + 220, w, 34), "删除", "delete", danger=True),
        "clear": Button((pad, y + 260, w, 34), "清空画布", "clear"),
    }
    return tool_buttons, buttons


def draw_sidebar(tool_buttons, buttons):
    draw_sidebar_bg(screen)
    draw_sidebar_header(screen, "家具模板编辑器", "Furniture Template")

    pad = 16
    screen.blit(FONT_SMALL.render("绘制工具", True, C_SIDEBAR_MUTED), (pad, 64))

    for btn in tool_buttons.values():
        btn.active = btn.action == f"tool:{current_tool}"
        btn.draw(screen, mouse_pos, on_dark=True)
    if return_to_gallery_after_edit:
        buttons["gallery"].label = "← 返回 Display 大库"
        buttons["gallery"].action = "gallery_return"
    else:
        buttons["gallery"].label = "Display 总览 →"
        buttons["gallery"].action = "gallery"
    for btn in buttons.values():
        btn.draw(screen, mouse_pos, on_dark=True)

    input_name.draw(screen, "模板名称", on_dark=True)
    input_family.draw(screen, "Product Family", on_dark=True)
    family = input_family.get_text()
    roi_val = lookup_roi(family)
    roi_hint = f"ROI: {roi_val:.1f}"
    if family and roi_val == 0:
        roi_hint = f"ROI: 未找到「{family}」"
    screen.blit(FONT_MARK.render(roi_hint, True, C_SIDEBAR_MUTED), (pad, input_family.rect.bottom + 4))
    mode_label = _editing_mode_label()
    if mode_label:
        screen.blit(FONT_MARK.render(mode_label, True, C_SUCCESS), (pad, input_family.rect.bottom + 18))

    footer_y = screen.get_height() - 44
    pygame.draw.line(screen, C_SIDEBAR_HOVER, (pad, footer_y - 8), (SIDEBAR_WIDTH - pad, footer_y - 8), 1)
    if selected_index >= 0 and selected_index < len(furniture_templates):
        tpl = furniture_templates[selected_index]
        status = f"当前: {tpl.get('id', '')}"
        sub = tpl.get("product_family", "")
    else:
        status = "未选中模板"
        sub = "从产品总览打开或新建"
    screen.blit(FONT_SMALL.render(status, True, C_SIDEBAR_TEXT), (pad, footer_y))
    screen.blit(FONT_MARK.render(sub, True, C_SIDEBAR_MUTED), (pad, footer_y + 18))


def _is_new_entry_mode() -> bool:
    return editing_mode in ("new", "copy")


def _editing_mode_label() -> str:
    if editing_mode == "copy":
        return "【新副本 · 保存后添加，不覆盖原模板】"
    if editing_mode == "new":
        return "【新模板 · 保存后添加】"
    return ""


def reset_draw_state():
    global draw_phase, drag_start, drag_current, polygon_points, preview_point, editing_template
    global l_outer_corners, l_cut_preview, resizing_handle, editing_mode
    draw_phase = "idle"
    drag_start = None
    drag_current = None
    l_outer_corners = None
    l_cut_preview = None
    resizing_handle = None
    polygon_points = []
    preview_point = None
    editing_template = None
    editing_mode = "new"


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


def _duplicate_id(name: str, ignore_index: int = -1) -> bool:
    for i, tpl in enumerate(furniture_templates):
        if i != ignore_index and tpl.get("id", "").lower() == name.lower():
            return True
    return False


def rename_template():
    """只更新名称和 Product Family，复制后也可用此保存新名称。"""
    global selected_index, editing_template, editing_mode
    name = input_name.get_text().strip()
    family = input_family.get_text().strip() or name
    if not name:
        toast.show("请填写模板名称")
        return
    roi = lookup_roi(family)
    if roi == 0:
        toast.show(f"警告: roi.xlsx 中未找到 {family}，ROI 将为 0")

    if not _is_new_entry_mode() and selected_index >= 0:
        if _duplicate_id(name, ignore_index=selected_index):
            toast.show(f"名称「{name}」已存在，请换一个")
            return
        tpl = furniture_templates[selected_index]
        old_name = tpl["id"]
        tpl["id"] = name
        tpl["product_family"] = family
        tpl["roi"] = roi
        editing_template = copy.deepcopy(tpl)
        toast.show(f"已重命名: {old_name} → {name}，ROI={roi:.1f}")
        return

    if not editing_template:
        toast.show("请先选中模板，或先复制再重命名")
        return
    if _duplicate_id(name):
        toast.show(f"名称「{name}」已存在，请换一个")
        return
    editing_template = copy.deepcopy(editing_template)
    editing_template["id"] = name
    editing_template["product_family"] = family
    editing_template["roi"] = roi
    furniture_templates.append(editing_template)
    selected_index = len(furniture_templates) - 1
    editing_mode = "edit"
    toast.show(f"新模板已添加: {name}，ROI={roi:.1f}")


def save_to_list():
    global selected_index, editing_mode, editing_template
    if not editing_template:
        apply_current_shape()
    if not editing_template:
        return
    family = input_family.get_text() or editing_template.get("id", "")
    editing_template["id"] = input_name.get_text() or editing_template["id"]
    editing_template["product_family"] = family
    editing_template["roi"] = lookup_roi(family)
    name = editing_template["id"]
    saved = copy.deepcopy(editing_template)

    if _is_new_entry_mode():
        if _duplicate_id(name):
            toast.show(f"名称「{name}」已存在，请换一个名称")
            return
        furniture_templates.append(saved)
        selected_index = len(furniture_templates) - 1
        editing_mode = "edit"
        editing_template = saved
        toast.show(f"已添加新模板: {name}")
        return

    if selected_index >= 0:
        if _duplicate_id(name, ignore_index=selected_index):
            toast.show(f"名称「{name}」已存在")
            return
        furniture_templates[selected_index] = saved
        editing_template = saved
        toast.show(f"已更新: {name}")
    else:
        if _duplicate_id(name):
            toast.show(f"名称「{name}」已存在")
            return
        furniture_templates.append(saved)
        selected_index = len(furniture_templates) - 1
        editing_mode = "edit"
        editing_template = saved
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
    selected_index = -1
    toast.show(f"已加载 {len(furniture_templates)} 个模板")


def load_template_into_editor(index, quiet=False):
    global selected_index, editing_template, current_tool, editing_mode
    global draw_phase, drag_start, drag_current, polygon_points, preview_point
    global l_outer_corners, l_cut_preview, resizing_handle, _last_list_pick

    now = pygame.time.get_ticks()
    if index == _last_list_pick["index"] and now - _last_list_pick["time"] < WHEEL_CLICK_COOLDOWN_MS:
        return
    _last_list_pick = {"index": index, "time": now}

    if index == selected_index and editing_mode == "edit" and editing_template and quiet:
        return

    if _is_new_entry_mode() and editing_template and not quiet:
        toast.show("未保存的新副本已丢弃，已加载列表中的模板")

    selected_index = index
    editing_mode = "edit"
    tpl = copy.deepcopy(furniture_templates[index])
    editing_template = tpl
    input_name.set_text(tpl["id"])
    input_family.set_text(tpl.get("product_family", tpl["id"]))
    if tpl["type"] == "rectangle":
        current_tool = "rect"
    elif tpl["type"] == "circle":
        current_tool = "circle"
    else:
        current_tool = "polygon"
    draw_phase = "idle"
    drag_start = drag_current = None
    l_outer_corners = l_cut_preview = resizing_handle = None
    polygon_points = []
    preview_point = None
    if not quiet:
        toast.show(f"已选中: {tpl['id']}（修改后保存会更新此项）")


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


def _suggest_copy_name(base: str) -> str:
    candidate = f"{base}_copy"
    n = 2
    while _duplicate_id(candidate):
        candidate = f"{base}_copy{n}"
        n += 1
    return candidate


def _store_template_clipboard(tpl: dict) -> None:
    global _template_clipboard
    _template_clipboard = copy.deepcopy(tpl)


def _template_source() -> dict | None:
    if selected_index >= 0 and selected_index < len(furniture_templates):
        return furniture_templates[selected_index]
    if editing_template:
        return editing_template
    return None


def copy_template_to_clipboard(src: dict | None = None) -> bool:
    tpl = src or _template_source()
    if not tpl:
        toast.show("请先选中要复制的模板")
        return False
    _store_template_clipboard(tpl)
    toast.show(f"已复制: {tpl.get('id', 'template')}")
    return True


def paste_template_from_clipboard() -> bool:
    """Ctrl+V：从剪贴板粘贴出新形状，进入绘制界面并重命名。"""
    global editing_template, selected_index, draw_phase, editing_mode, app_screen
    if not _template_clipboard:
        toast.show("剪贴板为空，请先 Ctrl+C 复制")
        return False

    src = _template_clipboard
    new_tpl = copy.deepcopy(src)
    new_name = _suggest_copy_name(src.get("id", "template"))
    new_family = src.get("product_family", src.get("id", new_name))
    new_tpl["id"] = new_name
    new_tpl["product_family"] = new_family
    new_tpl["roi"] = lookup_roi(new_family)

    editing_template = new_tpl
    editing_mode = "copy"
    selected_index = -1
    draw_phase = "idle"
    input_name.set_text(new_name)
    input_family.set_text(new_family)

    if app_screen == "gallery":
        close_gallery()
    focus_input(input_name)
    input_name.select_all_text()
    toast.show(f"已粘贴新形状，请修改名称后保存")
    return True


def copy_selected_template():
    if not copy_template_to_clipboard():
        return
    paste_template_from_clipboard()


def handle_toolbar(action):
    global current_tool, selected_index
    if action.startswith("tool:"):
        current_tool = action.split(":", 1)[1]
        reset_draw_state()
        toast.show(f"工具: {dict(TOOLS)[current_tool]}")
    elif action == "apply":
        save_to_list()
    elif action == "rename":
        rename_template()
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
    elif action == "gallery":
        open_gallery()
    elif action == "gallery_return":
        return_to_gallery_view()
    elif action == "gallery_back":
        close_gallery()


def handle_canvas_mousedown(mx, my, button):
    global draw_phase, drag_start, drag_current, polygon_points, preview_point, editing_template, selected_index
    global l_outer_corners, l_cut_preview, resizing_handle, editing_mode
    global dragging_shape, drag_shape_last_world
    wx, wy = screen_to_world(mx, my)
    wx, wy = snap_grid(wx, wy)

    if button == 3:
        return "pan"

    if draw_phase == "idle" and editing_template:
        handle = hit_resize_handle(mx, my)
        if handle is not None:
            resizing_handle = handle
            return
        if hit_template_body(mx, my):
            dragging_shape = True
            drag_shape_last_world = screen_to_world(mx, my)
            return
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
        editing_mode = "new"
        selected_index = -1
        draw_phase = "idle"
        l_outer_corners = None
        l_cut_preview = None
        toast.show("L 形已生成，可调整名称和 ROI 后保存")
        return

    draw_phase = "drawing"
    drag_start = (wx, wy)
    drag_current = (wx, wy)


def handle_canvas_mouseup(mx, my, button):
    global draw_phase, drag_current, editing_template, selected_index, l_outer_corners, editing_mode
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
        editing_mode = "new"
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
        editing_mode = "new"
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


def handle_global_clipboard_shortcuts(event):
    """Template-level Ctrl+C/V when input fields are not focused."""
    if event.type != pygame.KEYDOWN:
        return False
    if input_name.active or input_family.active or input_search.active:
        return False

    if ui.is_ctrl_key(event, "c"):
        copy_template_to_clipboard()
        return True

    if ui.is_ctrl_key(event, "v"):
        paste_template_from_clipboard()
        return True

    return False


def try_sidebar_click(pos, tool_buttons, buttons):
    mx, my = pos
    return handle_sidebar_click(mx, my, tool_buttons, buttons)


def handle_sidebar_click(mx, my, tool_buttons, buttons):
    for tool_id, btn in tool_buttons.items():
        if btn.contains((mx, my)):
            handle_toolbar(btn.action)
            return True
    for btn in buttons.values():
        if btn.contains((mx, my)):
            handle_toolbar(btn.action)
            return True
    if input_name.contains((mx, my)):
        handle_input_click(input_name)
        return True
    if input_family.contains((mx, my)):
        handle_input_click(input_family)
        return True
    blur_inputs()
    return False


_last_gallery_display_pick = {"key": None, "time": 0}


def _find_display_item(key: str):
    for it in display_items:
        if it.key == key:
            return it
    return None


def begin_survey_display(item) -> None:
    """无模型时进入绘制界面开始测绘（保留 Display 大库状态，可一键返回）。"""
    global editing_template, editing_mode, selected_index, selected_display_key
    reset_draw_state()
    selected_display_key = item.key
    input_name.set_text(item.product_name)
    input_family.set_text(item.product_family if item.product_family != "未分类" else "")
    editing_mode = "new"
    selected_index = -1
    open_editor_from_gallery()
    focus_input(input_name)
    toast.show(f"开始测绘: {item.product_name}（保存后点「返回 Display 大库」）")


def refresh_display_data(prefer_db: bool = True) -> None:
    global display_items
    try:
        if prefer_db:
            from display_lookup import grab_and_save
            from product_images import clear_image_cache

            display_items, excel_path = grab_and_save()
            clear_image_cache()
            gallery_view.invalidate_layout()
            toast.show(f"已抓取 {len(display_items)} 款 → {os.path.basename(excel_path)}")
            return
    except Exception:
        pass
    display_items = reload_display_items(prefer_db=False)
    gallery_view.invalidate_layout()
    src = last_load_source() or "display.xlsx"
    if display_items:
        toast.show(f"已刷新 {len(display_items)} 款（来自 {src}）")
    else:
        toast.show(last_load_error() or "请先运行 grab_display.bat")


def handle_gallery_click(mx, my):
    global selected_index, selected_display_key, gallery_mode, display_shop, _last_gallery_pick, _last_gallery_display_pick
    hit = gallery_view.handle_click(mx, my)
    if hit == "back":
        close_gallery()
        return True
    if hit == "refresh":
        refresh_display_data(prefer_db=True)
        return True
    if isinstance(hit, str) and hit.startswith("mode:"):
        gallery_mode = hit.split(":", 1)[1]
        gallery_view.scroll_y = 0
        gallery_view.invalidate_layout()
        return True
    if isinstance(hit, str) and hit.startswith("shop:"):
        display_shop = hit.split(":", 1)[1]
        gallery_view.scroll_y = 0
        gallery_view.invalidate_layout()
        return True
    if isinstance(hit, tuple) and hit[0] == "display":
        key = hit[1]
        item = _find_display_item(key)
        if not item:
            return True
        now = pygame.time.get_ticks()
        is_double = key == _last_gallery_display_pick["key"] and now - _last_gallery_display_pick["time"] < 400
        _last_gallery_display_pick = {"key": key, "time": now}
        tpl_idx = match_template_index(item, furniture_templates)
        if is_double:
            if tpl_idx >= 0:
                open_editor_from_gallery()
                load_template_into_editor(tpl_idx)
            else:
                begin_survey_display(item)
        else:
            selected_display_key = key
            if tpl_idx >= 0:
                toast.show(f"已选中: {item.product_name}（已有模型 · 双击编辑）")
            else:
                toast.show(f"已选中: {item.product_name}（待测绘 · 双击开始）")
        return True
    if hit is not None and isinstance(hit, int):
        now = pygame.time.get_ticks()
        is_double = hit == _last_gallery_pick["index"] and now - _last_gallery_pick["time"] < 400
        _last_gallery_pick = {"index": hit, "time": now}
        if is_double:
            open_editor_from_gallery()
            load_template_into_editor(hit)
        else:
            selected_index = hit
            toast.show(f"已选中: {furniture_templates[hit]['id']}")
        return True
    if input_search.contains((mx, my)):
        handle_input_click(input_search)
        return True
    blur_inputs()
    return False


def main():
    global screen, clock
    global offset_x, offset_y, scale, dragging_view, last_mouse_pos, mouse_pos
    global draw_phase, drag_current, preview_point, polygon_points, l_cut_preview, resizing_handle, editing_template
    global dragging_shape, drag_shape_last_world
    global editing_template, selected_index, editing_mode, app_screen, display_items

    reload_roi_map()
    display_items = load_display_items()

    if os.path.isfile(TEMPLATES_FILE):
        try:
            load_templates_file()
        except Exception as exc:
            show_error("加载模板失败", str(exc))

    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.RESIZABLE)
    pygame.display.set_caption(f"家具模板编辑器 v{ui.__version__}")
    clock = pygame.time.Clock()

    tool_buttons, buttons = build_sidebar()
    running = True
    global _sidebar_click_start
    _gallery_click_start = None
    is_fullscreen = False
    open_gallery()

    while running:
        mouse_pos = pygame.mouse.get_pos()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.VIDEORESIZE and not is_fullscreen:
                screen = pygame.display.set_mode(event.size, pygame.RESIZABLE)
                gallery_view.invalidate_layout()

            elif app_screen == "gallery":
                sh = screen.get_height()
                if event.type == pygame.MOUSEWHEEL:
                    gallery_view.scroll(-event.y * 48)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mx, my = event.pos
                    if gallery_view.begin_scroll_drag(mx, my, sh):
                        _gallery_click_start = None
                    else:
                        _gallery_click_start = event.pos
                elif event.type == pygame.MOUSEMOTION:
                    if gallery_view._scroll_drag:
                        gallery_view.update_scroll_drag(event.pos[1], sh)
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    gallery_view.end_scroll_drag()
                    if _gallery_click_start is not None:
                        gx, gy = _gallery_click_start
                        mx, my = event.pos
                        if abs(mx - gx) <= CLICK_MOVE_TOLERANCE and abs(my - gy) <= CLICK_MOVE_TOLERANCE:
                            handle_gallery_click(mx, my)
                    _gallery_click_start = None
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        close_gallery()
                    elif event.key == pygame.K_F11:
                        is_fullscreen = not is_fullscreen
                        screen = pygame.display.set_mode(
                            (0, 0) if is_fullscreen else (SCREEN_WIDTH, SCREEN_HEIGHT),
                            pygame.FULLSCREEN if is_fullscreen else pygame.RESIZABLE,
                        )
                    elif handle_global_clipboard_shortcuts(event):
                        pass
                    else:
                        handled = input_search.handle_event(event)
                        if handled and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                            pass
                elif event.type in (pygame.TEXTEDITING, pygame.TEXTINPUT):
                    if input_search.active:
                        input_search.handle_event(event)
                        if event.type == pygame.TEXTINPUT:
                            gallery_view.scroll_y = 0
                            gallery_view.invalidate_layout()

            else:
                if event.type == pygame.MOUSEWHEEL:
                    mx, my = mouse_pos
                    if mx < SIDEBAR_WIDTH:
                        pass
                    else:
                        wx, wy = screen_to_world(mx, my)
                        scale = max(0.01, min(2.0, scale * (1.15 if event.y > 0 else 1 / 1.15)))
                        offset_x = wx - (mx - SIDEBAR_WIDTH) / scale
                        offset_y = wy - my / scale

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    mx, my = event.pos
                    if mx < SIDEBAR_WIDTH:
                        if event.button == 1:
                            _sidebar_click_start = event.pos
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
                        mx, my = event.pos
                        if mx < SIDEBAR_WIDTH:
                            if _sidebar_click_start is not None:
                                sx, sy = _sidebar_click_start
                                if abs(mx - sx) <= CLICK_MOVE_TOLERANCE and abs(my - sy) <= CLICK_MOVE_TOLERANCE:
                                    try_sidebar_click(event.pos, tool_buttons, buttons)
                            _sidebar_click_start = None
                        else:
                            if resizing_handle is not None:
                                resizing_handle = None
                                toast.show("尺寸已更新")
                            elif dragging_shape:
                                dragging_shape = False
                                drag_shape_last_world = None
                                keys = pygame.key.get_pressed()
                                if not (keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]):
                                    snap_template_to_grid()
                                toast.show("位置已更新")
                            else:
                                handle_canvas_mouseup(*event.pos, 1)

                elif event.type == pygame.MOUSEMOTION:
                    mx, my = event.pos
                    if _sidebar_click_start is not None and mx < SIDEBAR_WIDTH:
                        sx, sy = _sidebar_click_start
                        if abs(mx - sx) > CLICK_MOVE_TOLERANCE or abs(my - sy) > CLICK_MOVE_TOLERANCE:
                            _sidebar_click_start = None
                    if resizing_handle is not None:
                        wx, wy = screen_to_world(mx, my)
                        apply_resize(resizing_handle, wx, wy)
                    elif dragging_shape and drag_shape_last_world is not None:
                        wx, wy = screen_to_world(mx, my)
                        dx = wx - drag_shape_last_world[0]
                        dy = wy - drag_shape_last_world[1]
                        if abs(dx) >= 1 or abs(dy) >= 1:
                            keys = pygame.key.get_pressed()
                            if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
                                translate_editing_template(dx, dy)
                            else:
                                translate_editing_template(
                                    round(dx / GRID_SNAP) * GRID_SNAP,
                                    round(dy / GRID_SNAP) * GRID_SNAP,
                                )
                            drag_shape_last_world = screen_to_world(mx, my)
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
                    if event.key == pygame.K_F11:
                        is_fullscreen = not is_fullscreen
                        screen = pygame.display.set_mode(
                            (0, 0) if is_fullscreen else (SCREEN_WIDTH, SCREEN_HEIGHT),
                            pygame.FULLSCREEN if is_fullscreen else pygame.RESIZABLE,
                        )
                    elif event.key == pygame.K_TAB:
                        advance_focus(bool(event.mod & pygame.KMOD_SHIFT))
                        continue

                    handled = (
                        input_name.handle_event(event)
                        or input_family.handle_event(event)
                    )
                    if handled:
                        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                            handle_enter_action()
                    elif handle_global_clipboard_shortcuts(event):
                        pass
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        handle_enter_action()
                    elif current_tool == "polygon":
                        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and len(polygon_points) >= 3:
                            editing_template = template_to_dict(
                                input_name.get_text() or "polygon",
                                input_family.get_text() or input_name.get_text() or "polygon",
                                "polygon",
                                polygon_points,
                            )
                            editing_mode = "new"
                            polygon_points = []
                            draw_phase = "idle"
                            preview_point = None
                            selected_index = -1
                            toast.show("多边形完成，可保存到列表")
                        elif event.key == pygame.K_ESCAPE:
                            polygon_points = []
                            draw_phase = "idle"
                            preview_point = None
                    elif event.key == pygame.K_ESCAPE:
                        if return_to_gallery_after_edit and draw_phase == "idle":
                            if input_name.active or input_family.active:
                                blur_inputs()
                            else:
                                return_to_gallery_view()
                    elif event.key == pygame.K_s and event.mod & pygame.KMOD_CTRL:
                        if not (input_name.active or input_family.active):
                            save_to_list()
                            write_templates_file()

                elif event.type == pygame.TEXTEDITING:
                    if input_name.active:
                        input_name.handle_event(event)
                    elif input_family.active:
                        input_family.handle_event(event)

                elif event.type == pygame.TEXTINPUT:
                    if input_name.active:
                        input_name.handle_event(event)
                    elif input_family.active:
                        input_family.handle_event(event)

        if app_screen == "gallery":
            gallery_view.draw(screen, furniture_templates, selected_index)
            tick_input_focus()
            toast.draw(screen, screen.get_width() // 2)
        else:
            draw_canvas(screen)
            draw_sidebar(tool_buttons, buttons)
            tick_input_focus()
            sw = screen.get_width()
            toast.draw(screen, SIDEBAR_WIDTH + (sw - SIDEBAR_WIDTH) // 2)
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
