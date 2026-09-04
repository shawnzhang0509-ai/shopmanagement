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
    TemplateIndexCache,
    blacklist_files_revision,
    blacklist_status,
    cached_shop_stats,
    display_items_including_blacklist,
    filter_gallery_items,
    filter_items,
    find_display_item_for_template,
    group_by_family,
    invalidate_shop_stats_cache,
    last_load_error,
    last_load_source,
    last_family_column,
    load_display_items,
    lookup_display_item,
    match_template_index,
    find_template_index_by_id,
    prune_orphan_templates,
    resolve_is_discontinued,
    reload_display_items,
    shop_stats,
    shops_for_display_tabs,
)
from product_images import is_image_failed, prefetch_urls, request_thumbnail, request_image

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
Dropdown = ui.Dropdown
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
display_shop = "all"
display_survey_filter = "all"  # all | modeled | unmodeled
display_blacklist_mode = "exclude"  # exclude | all | only
selected_display_key = None
display_items = []
_pending_input_focus = None
_pending_focus_frames = 0
_sidebar_click_start = None  # (x, y) mouse-down position for click-vs-drag
_last_list_pick = {"index": -1, "time": 0}
CLICK_MOVE_TOLERANCE = 10
WHEEL_CLICK_COOLDOWN_MS = 350
UNDO_LIMIT = 40
SIDEBAR_PRODUCT_CARD_H = 108
_undo_stack: list[dict] = []
_undo_drag_started = False
return_to_gallery_after_edit = False
_gallery_snapshot: dict | None = None


class GalleryView:
    """全屏总览：Display 大库（按门店 / 已测绘筛选）。"""

    TOP_H = 102
    SHOP_H = 36
    FILTER_H = 28
    FAMILY_H = 40
    SUB_FAMILY_H = 34
    CARD_W = 108
    CARD_H = 142
    IMG_SIZE = 88
    CARD_GAP = 14
    PAD = 28
    FAMILY_GAP = 24
    SCROLLBAR_W = 12
    SCROLLBAR_MARGIN = 6
    SEARCH_DEBOUNCE_MS = 180

    def __init__(self):
        self.scroll_y = 0
        self.back_btn = Button((0, 0, 0, 0), "← 返回绘制", "gallery_back")
        self.refresh_btn = Button((0, 0, 0, 0), "刷新", "display_refresh")
        self.copy_btn = Button((0, 0, 0, 0), "复制", "gallery_copy")
        self.paste_btn = Button((0, 0, 0, 0), "粘贴", "gallery_paste")
        self._layout = []
        self._cards = []  # (rect, kind, data) kind: template|display
        self._gallery_dropdowns: dict[str, Dropdown] = {}
        self._open_gallery_dd: str | None = None
        self._layout_key: tuple | None = None
        self._content_h = 0
        self._scroll_drag = False
        self._scroll_drag_offset = 0
        self._last_sw = 0
        self._search_query = ""
        self._search_dirty = False
        self._search_dirty_at = 0
        self._template_index = TemplateIndexCache()

    def _filtered_displays(self, templates):
        return filter_gallery_items(
            display_items_including_blacklist(),
            display_shop,
            self._search_query,
            templates,
            survey_filter=display_survey_filter,
            blacklist_mode=display_blacklist_mode,
            template_index=self._template_index,
        )

    def sync_search_query(self) -> None:
        """立即把搜索框文字同步到筛选条件（切换 Tab / 打开大库时用）。"""
        self._search_query = input_search.get_text()
        self._search_dirty = False

    def mark_search_dirty(self) -> None:
        self._search_dirty = True
        self._search_dirty_at = pygame.time.get_ticks()

    def tick_search_debounce(self) -> None:
        if not self._search_dirty:
            return
        if pygame.time.get_ticks() - self._search_dirty_at < self.SEARCH_DEBOUNCE_MS:
            return
        self._search_dirty = False
        query = input_search.get_text()
        if query == self._search_query:
            return
        self._search_query = query
        self.scroll_y = 0
        self.invalidate_layout()

    def invalidate_layout(self) -> None:
        self._layout_key = None

    def _layout_cache_key(self, templates, screen_w: int) -> tuple:
        return (
            screen_w,
            display_shop,
            display_survey_filter,
            display_blacklist_mode,
            blacklist_files_revision(),
            self._search_query,
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

    def build_layout(self, templates, screen_w: int):
        self._layout = []
        self._cards = []
        y = self.PAD
        idx_cache = self._template_index.for_templates(templates)
        filtered = self._filtered_displays(templates)
        for family, items in group_by_family(filtered):
            modeled = sum(1 for it in items if idx_cache.lookup(it) >= 0)
            self._layout.append(("family", family, len(items), modeled, y))
            y += self.FAMILY_H
            x = self.PAD
            row_y = y
            for item in sorted(items, key=lambda it: it.product_name.lower()):
                if x + self.CARD_W > screen_w - self.PAD:
                    x = self.PAD
                    row_y += self.CARD_H + self.CARD_GAP
                rect = pygame.Rect(x, row_y, self.CARD_W, self.CARD_H)
                tpl_idx = idx_cache.lookup(item)
                self._layout.append(("card_disp", rect, item, tpl_idx))
                self._cards.append((rect, "display", item.key))
                x += self.CARD_W + self.CARD_GAP
            y = row_y + self.CARD_H + self.FAMILY_GAP
        return y + self.PAD

    def scroll(self, delta: int):
        self.scroll_y = max(0, self.scroll_y + delta)

    def clamp_scroll(self, content_h: int, screen_h: int):
        view_h = screen_h - self.TOP_H
        self.scroll_y = min(self.scroll_y, max(0, content_h - view_h))

    def content_y(self, my: int) -> int:
        return my - self.TOP_H + self.scroll_y

    def _shop_dropdown_options(self, templates) -> list[tuple[str, str]]:
        opts: list[tuple[str, str]] = []
        for shop, st in shops_for_display_tabs(display_items, templates):
            sid = shop["id"]
            if sid == "all":
                text = f"全部 {st['total']}"
            else:
                text = f"{shop['label']} {st.get('families', 0)}族"
            opts.append((sid, text))
        return opts or [("all", "全部")]

    def _close_gallery_dropdowns(self) -> None:
        for dd in self._gallery_dropdowns.values():
            dd.open = False
        self._open_gallery_dd = None

    def _handle_gallery_dropdown_click(self, mx: int, my: int):
        pos = (mx, my)
        if self._open_gallery_dd and self._open_gallery_dd in self._gallery_dropdowns:
            dd = self._gallery_dropdowns[self._open_gallery_dd]
            hit = dd.hit_test(pos)
            if isinstance(hit, tuple) and hit[0] == "pick":
                dd.selected = hit[1]
                dd.open = False
                picked = self._open_gallery_dd
                value = hit[1]
                self._open_gallery_dd = None
                if picked == "shop":
                    return f"shop:{value}"
                if picked == "survey":
                    return f"survey:{value}"
                if picked == "bl":
                    return f"bl:{value}"
            if hit in ("trigger", "outside"):
                dd.open = False
                self._open_gallery_dd = None
                return "dd:closed"
        for dd_id, dd in self._gallery_dropdowns.items():
            if dd.hit_test(pos) == "trigger":
                self._close_gallery_dropdowns()
                dd.open = True
                self._open_gallery_dd = dd_id
                return "dd:opened"
        return None

    def handle_click(self, mx: int, my: int):
        if self.back_btn.contains((mx, my)):
            return "back"
        if self.refresh_btn.contains((mx, my)):
            return "refresh"
        if self.copy_btn.contains((mx, my)):
            return "gallery_copy"
        if self.paste_btn.contains((mx, my)):
            return "gallery_paste"
        dd_hit = self._handle_gallery_dropdown_click(mx, my)
        if isinstance(dd_hit, str) and dd_hit.startswith(("shop:", "survey:", "bl:")):
            return dd_hit
        if dd_hit in ("dd:opened", "dd:closed"):
            return True
        if input_search.contains((mx, my)):
            return None
        if my < self.TOP_H:
            return None
        cy = self.content_y(my)
        for rect, kind, data in self._cards:
            if rect.collidepoint(mx, cy):
                if kind == "display":
                    return ("display", data)
        return None

    def _draw_header_tabs(self, surface, sw: int, templates):
        input_search.rect = pygame.Rect(20, 10, min(360, sw - 560), 28)
        input_search.draw(surface, None, on_dark=True)

        stats = cached_shop_stats(display_items, templates) if display_items else {}
        if stats.get("all"):
            s = stats["all"]
            label = f"已测绘 {s['modeled']}/{s['total']}"
        else:
            label = f"共 {len(templates)} 个"
        surface.blit(FONT_SMALL.render(label, True, C_SIDEBAR_MUTED), (input_search.rect.right + 10, 16))

        self.refresh_btn.rect = pygame.Rect(sw - 248, 10, 72, 28)
        self.refresh_btn.draw(surface, mouse_pos, on_dark=True)
        self.paste_btn.rect = pygame.Rect(sw - 328, 10, 56, 28)
        self.copy_btn.rect = pygame.Rect(sw - 392, 10, 56, 28)
        self.paste_btn.draw(surface, mouse_pos, on_dark=True)
        self.copy_btn.draw(surface, mouse_pos, on_dark=True)
        self.back_btn.rect = pygame.Rect(sw - 148, 10, 128, 28)
        self.back_btn.draw(surface, mouse_pos, on_dark=True)

        fy = 42
        gap = 8
        shop_w = min(200, max(120, (sw - 40 - gap * 2) // 3))
        filt_w = min(160, max(100, (sw - 40 - gap * 2 - shop_w) // 2))
        self._gallery_dropdowns = {
            "shop": Dropdown(
                (20, fy, shop_w, 28),
                self._shop_dropdown_options(templates),
                display_shop,
                label="门店",
                dropdown_id="shop",
            ),
            "survey": Dropdown(
                (20 + shop_w + gap, fy, filt_w, 28),
                [("all", "全部"), ("modeled", "已测绘"), ("unmodeled", "未测绘")],
                display_survey_filter,
                label="测绘",
                dropdown_id="survey",
            ),
            "bl": Dropdown(
                (20 + shop_w + gap + filt_w + gap, fy, filt_w, 28),
                [("exclude", "剔除黑名单"), ("all", "含黑名单"), ("only", "仅黑名单")],
                display_blacklist_mode,
                label="黑名单",
                dropdown_id="bl",
            ),
        }
        if self._open_gallery_dd and self._open_gallery_dd in self._gallery_dropdowns:
            self._gallery_dropdowns[self._open_gallery_dd].open = True
        for dd in self._gallery_dropdowns.values():
            dd.draw(surface, mouse_pos, on_dark=True, draw_menu=False)

    def draw(self, surface, templates, selected_index: int):
        sw, sh = surface.get_width(), surface.get_height()
        surface.fill((245, 247, 250))
        pygame.draw.rect(surface, C_SIDEBAR_DARK, (0, 0, sw, self.TOP_H))

        title = "Display 大库"
        surface.blit(FONT_TITLE.render(title, True, C_SIDEBAR_TEXT), (20, 74))
        surface.blit(FONT_MARK.render("单击选中 · 复制/粘贴按钮或 Ctrl+C/V", True, C_SIDEBAR_MUTED), (168, 78))

        self._draw_header_tabs(surface, sw, templates)

        for dd in self._gallery_dropdowns.values():
            if dd.open:
                dd.draw_menu(surface, mouse_pos)

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
                meta = f"{count} 款 Display  ·  已测绘 {extra}/{count}"
                meta_surf = FONT_SMALL.render(meta, True, C_SIDEBAR_MUTED)
                surface.blit(meta_surf, (bar.right - meta_surf.get_width() - 14, bar.y + 12))
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
        if err and not display_items:
            banner = FONT_SMALL.render(f"⚠ {err[:90]}", True, (200, 80, 60))
            surface.blit(banner, (self.PAD, sh - 28))
        elif display_items and last_load_source():
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
            survey_labels = {"all": "全部", "modeled": "已测绘", "unmodeled": "未测绘"}
            bl_labels = {"exclude": "剔除黑", "all": "含黑名单", "only": "仅黑"}
            hint += f" · {survey_labels.get(display_survey_filter, '')} · {bl_labels.get(display_blacklist_mode, '')}"
            bl_n, bl_src, _ = blacklist_status()
            hint += f" · 黑名单 {bl_n} 个 ({bl_src})"
            err = last_load_error()
            if err and display_items and "未读到有效" in (err or ""):
                hint += f" · {err[:70]}"
            surface.blit(FONT_MARK.render(hint, True, C_SIDEBAR_MUTED), (self.PAD, sh - 22))


gallery_view = GalleryView()


def template_shape_badge(tpl: dict | None) -> str:
    """已测绘模板的形状角标：矩 / 圆 / L / 多边。"""
    if not tpl:
        return ""
    shape = tpl.get("type", "")
    if shape == "rectangle":
        return "矩"
    if shape == "circle":
        rx, ry = circle_radii(tpl)
        if abs(rx - ry) > 1:
            return "椭"
        return "圆"
    if shape == "polygon":
        pts = tpl.get("points", [])
        if len(pts) == 6:
            return "L"
        return "多边"
    return "?"


def _blit_thumb_fit(surface, thumb_surf, rect: pygame.Rect) -> None:
    tw, th = thumb_surf.get_size()
    if tw <= 0 or th <= 0:
        return
    scale = min(rect.width / tw, rect.height / th)
    nw = max(1, int(tw * scale))
    nh = max(1, int(th * scale))
    scaled = pygame.transform.smoothscale(thumb_surf, (nw, nh))
    dest = scaled.get_rect(center=rect.center)
    surface.blit(scaled, dest)


def draw_display_card(surface, item, tpl, rect, selected=False, shop_id="all"):
    has_model = tpl is not None
    discontinued = bool(getattr(item, "is_discontinued", False))
    sku_show = (item.product_code or "").strip()
    if len(sku_show) > 13:
        sku_show = sku_show[:12] + "…"

    img_size = min(GalleryView.IMG_SIZE, rect.width - 8)
    img_rect = pygame.Rect(0, 0, img_size, img_size)
    img_rect.centerx = rect.centerx
    img_rect.y = rect.y + 18

    if discontinued:
        border = ui.C_DISCONTINUED_BORDER
        border_w = 2
        bg = ui.C_DISCONTINUED_BG if not selected else (255, 228, 220)
    elif has_model:
        border = C_SUCCESS
        border_w = 3
        bg = (232, 245, 236) if not selected else (200, 225, 245)
    elif selected:
        border = C_ACCENT
        border_w = 3
        bg = (214, 228, 248)
    else:
        border = (190, 198, 208)
        border_w = 1
        bg = (235, 238, 242)

    pygame.draw.rect(surface, bg, rect, border_radius=8)
    pygame.draw.rect(surface, border, rect, border_w, border_radius=8)
    if discontinued:
        ui.draw_discontinued_card_stripe(surface, rect, radius=8)
    if selected:
        ring = rect.inflate(8, 8)
        pygame.draw.rect(surface, C_ACCENT, ring, 3, border_radius=11)
        for corner in (rect.topleft, rect.topright, rect.bottomleft, rect.bottomright):
            pygame.draw.circle(surface, C_ACCENT, corner, 5)
            pygame.draw.circle(surface, (255, 255, 255), corner, 5, 1)

    if sku_show:
        sku_surf = FONT_MARK.render(sku_show, True, (44, 62, 80))
        surface.blit(sku_surf, (rect.x + 6, rect.y + 4))

    pygame.draw.rect(surface, (248, 250, 252), img_rect, border_radius=4)

    thumb_surf = None
    if getattr(item, "image_url", ""):
        thumb_surf = request_thumbnail(item.image_url)

    if thumb_surf is not None:
        _blit_thumb_fit(surface, thumb_surf, img_rect)
    else:
        pygame.draw.rect(surface, (210, 218, 226), img_rect, 1, border_radius=4)
        if not getattr(item, "image_url", ""):
            label = "待测绘"
        elif is_image_failed(item.image_url):
            label = "无图"
        else:
            label = "加载中…"
        wait = FONT_MARK.render(label, True, C_MUTED)
        surface.blit(wait, wait.get_rect(center=img_rect.center))

    if has_model:
        badge = pygame.Rect(img_rect.right - 20, img_rect.bottom - 18, 16, 16)
        pygame.draw.circle(surface, C_SUCCESS, badge.center, 8)
        check = FONT_MARK.render("✓", True, (255, 255, 255))
        surface.blit(check, check.get_rect(center=badge.center))
        shape = template_shape_badge(tpl)
        if shape:
            tag = FONT_MARK.render(shape, True, (255, 255, 255))
            tag_bg = pygame.Rect(img_rect.x + 4, img_rect.y + 4, tag.get_width() + 8, tag.get_height() + 2)
            pygame.draw.rect(surface, C_SUCCESS, tag_bg, border_radius=4)
            surface.blit(tag, (tag_bg.x + 4, tag_bg.y + 1))

    name = item.product_name
    if len(name) > 14:
        name = name[:13] + "…"
    name_y = img_rect.bottom + 4
    name_surf = FONT_SMALL.render(name, True, INPUT_TEXT)
    surface.blit(name_surf, (rect.x + 6, name_y))
    qty = item.display_qty_for_shop(shop_id)
    qty_color = C_SUCCESS if has_model else C_MUTED
    qty_surf = FONT_MARK.render(f"Display ×{qty}", True, qty_color)
    surface.blit(qty_surf, (rect.x + 6, rect.bottom - 16))
    if discontinued:
        ui.draw_discontinued_badge(surface, rect, align="topright")


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


POLYGON_CLOSE_PX = 16


def finish_polygon():
    global editing_template, editing_mode, polygon_points, draw_phase, preview_point, selected_index
    if len(polygon_points) < 3:
        toast.show("至少需要 3 个顶点")
        return False
    push_undo()
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
    return True


def handle_editor_shortcuts(event):
    """Editor shortcuts that must run before text inputs (IME-safe Ctrl+Z)."""
    if event.type != pygame.KEYDOWN:
        return False
    if ui.is_ctrl_key(event, "z"):
        undo_editor()
        return True
    if ui.is_ctrl_key(event, "s"):
        if not (input_name.active or input_family.active):
            save_to_list()
            write_templates_file()
            return True
    return False


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
    gallery_view.sync_search_query()
    gallery_view.invalidate_layout()
    return_to_gallery_after_edit = False
    _gallery_snapshot = None
    if not display_items:
        display_items = reload_display_items(prefer_db=False)
        invalidate_shop_stats_cache()
    removed = prune_templates_against_display()
    bl_n, bl_src, _ = blacklist_status()
    if removed:
        toast.show(f"已移除游离模板: {', '.join(removed)}")
    elif bl_n:
        toast.show(f"黑名单已加载 {bl_n} 个 SKU（{bl_src}）")


def open_editor_from_gallery():
    """从 Display 大库打开测绘/编辑，保留大库滚动与门店筛选。"""
    global app_screen, return_to_gallery_after_edit, _gallery_snapshot
    _gallery_snapshot = {
        "scroll_y": gallery_view.scroll_y,
        "display_shop": display_shop,
        "display_survey_filter": display_survey_filter,
        "display_blacklist_mode": display_blacklist_mode,
    }
    return_to_gallery_after_edit = True
    app_screen = "editor"
    input_search.deactivate()


def return_to_gallery_view():
    global app_screen, display_shop, display_items
    global return_to_gallery_after_edit, _gallery_snapshot
    global display_survey_filter, display_blacklist_mode
    snap = _gallery_snapshot or {}
    gallery_view.scroll_y = snap.get("scroll_y", 0)
    display_shop = snap.get("display_shop", display_shop)
    display_survey_filter = snap.get("display_survey_filter", display_survey_filter)
    display_blacklist_mode = snap.get("display_blacklist_mode", display_blacklist_mode)
    return_to_gallery_after_edit = False
    _gallery_snapshot = None
    app_screen = "gallery"
    display_items = reload_display_items(prefer_db=False)
    invalidate_shop_stats_cache()
    gallery_view.sync_search_query()
    gallery_view.invalidate_layout()
    toast.show("已返回 Display 大库")


def close_gallery():
    global app_screen
    app_screen = "editor"
    input_search.deactivate()


def _display_items_for_validation():
    items = display_items_including_blacklist()
    if items:
        return items
    return display_items or []


def _bind_template_to_display(tpl: dict, item) -> dict:
    tpl_id = item.product_code or item.product_name
    family = item.product_family if item.product_family and item.product_family != "未分类" else tpl_id
    tpl["id"] = tpl_id
    tpl["product_family"] = family
    tpl["roi"] = lookup_roi(family)
    tpl["display_key"] = item.key
    tpl["source"] = "display"
    tpl["is_discontinued"] = bool(getattr(item, "is_discontinued", False))
    return tpl


def _template_display_item(tpl: dict | None):
    if not tpl:
        return None
    if selected_display_key:
        item = _find_display_item(selected_display_key)
        if item:
            return item
    return find_display_item_for_template(tpl, _display_items_for_validation())


def _require_display_source(tpl: dict) -> bool:
    if _template_display_item(tpl):
        return True
    toast.show("模板必须对应 Display 库产品，请从 Display 大库打开测绘")
    return False


def prune_templates_against_display(*, persist: bool = True) -> list[str]:
    """删除不在 Display 库中的游离模板。"""
    global furniture_templates, selected_index
    items = _display_items_for_validation()
    if not items:
        return []
    kept, removed = prune_orphan_templates(furniture_templates, items)
    if not removed:
        return []
    furniture_templates = kept
    if selected_index >= len(furniture_templates):
        selected_index = len(furniture_templates) - 1
    invalidate_shop_stats_cache()
    gallery_view.invalidate_layout()
    if persist and os.path.isfile(TEMPLATES_FILE):
        with open(TEMPLATES_FILE, "w", encoding="utf-8") as f:
            json.dump(furniture_templates, f, ensure_ascii=False, indent=2)
    return removed


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
    return polygon_from_ellipse(cx, cy, r, r)


def polygon_from_ellipse(cx, cy, rx, ry, segments=32):
    return [
        (cx + rx * math.cos(2 * math.pi * i / segments), cy + ry * math.sin(2 * math.pi * i / segments))
        for i in range(segments)
    ]


def circle_radii(t: dict) -> tuple[float, float]:
    legacy = float(t.get("radius", 0) or 0)
    rx = float(t.get("radius_x", legacy) or legacy)
    ry = float(t.get("radius_y", legacy if legacy else rx) or rx)
    return rx, ry


def circle_center(t: dict) -> tuple[float, float]:
    return float(t.get("center_x", 0) or 0), float(t.get("center_y", 0) or 0)


def rect_offset(t: dict) -> tuple[float, float]:
    return float(t.get("offset_x", 0) or 0), float(t.get("offset_y", 0) or 0)


def capture_editor_state() -> dict:
    return {
        "editing_template": copy.deepcopy(editing_template),
        "editing_mode": editing_mode,
        "selected_index": selected_index,
        "current_tool": current_tool,
        "polygon_points": copy.deepcopy(polygon_points),
        "draw_phase": draw_phase,
    }


def push_undo():
    global _undo_stack
    _undo_stack.append(capture_editor_state())
    if len(_undo_stack) > UNDO_LIMIT:
        _undo_stack.pop(0)


def clear_undo():
    global _undo_stack
    _undo_stack = []


def undo_editor():
    global editing_template, editing_mode, selected_index, current_tool, polygon_points, draw_phase
    if not _undo_stack:
        toast.show("无可撤销的操作")
        return
    state = _undo_stack.pop()
    editing_template = state["editing_template"]
    editing_mode = state["editing_mode"]
    selected_index = state["selected_index"]
    current_tool = state["current_tool"]
    polygon_points = state["polygon_points"]
    draw_phase = state["draw_phase"]
    toast.show("已撤销上一步")


def begin_editor_mutation():
    global _undo_drag_started
    if not _undo_drag_started:
        push_undo()
        _undo_drag_started = True


def end_editor_mutation():
    global _undo_drag_started
    _undo_drag_started = False


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
        ox, oy = rect_offset(data)
        points = [(ox, oy), (ox + w, oy), (ox + w, oy + h), (ox, oy + h)]
    elif shape_type == "circle":
        cx, cy = circle_center(data)
        rx, ry = circle_radii(data)
        points = polygon_from_ellipse(cx, cy, rx, ry)
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
    shape_type = editing_template.get("type")
    if shape_type == "circle":
        cx, cy = circle_center(editing_template)
        editing_template["center_x"] = int(round(cx + dx))
        editing_template["center_y"] = int(round(cy + dy))
        return
    if shape_type == "rectangle":
        ox, oy = rect_offset(editing_template)
        editing_template["offset_x"] = int(round(ox + dx))
        editing_template["offset_y"] = int(round(oy + dy))
        return
    pts = normalize_template_dict(editing_template)
    new_pts = [(x + dx, y + dy) for x, y in pts]
    if shape_type == "polygon":
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
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)
        rx = max(math.hypot(p[0] - cx, p[1] - cy) for p in points)
        ry = rx
        return {
            "id": name,
            "product_family": product_family,
            "type": "circle",
            "radius_x": int(round(rx)),
            "radius_y": int(round(ry)),
            "center_x": int(round(cx)),
            "center_y": int(round(cy)),
            "roi": roi,
        }
    return {
        "id": name,
        "product_family": product_family,
        "type": "polygon",
        "points": [[int(round(x)), int(round(y))] for x, y in points],
        "roi": roi,
    }


def draw_shape(surface, points, fill=C_PREVIEW_FILL, border=C_PREVIEW, width=2, closed=True, show_vertices=True):
    if len(points) < 2:
        return
    screen_pts = [world_to_screen(x, y) for x, y in points]
    if closed and len(screen_pts) >= 3:
        pygame.draw.polygon(surface, fill, screen_pts)
    if len(screen_pts) >= 2:
        pygame.draw.lines(surface, border, closed, screen_pts, width)
    if show_vertices:
        for pt in screen_pts:
            pygame.draw.circle(surface, border, (int(pt[0]), int(pt[1])), 4)


def _format_length_mm(dist_mm: float) -> str:
    if dist_mm >= 1000:
        return f"{dist_mm / 1000:.2f} m"
    return f"{dist_mm:.0f} mm"


def draw_edge_dimensions(surface, points, min_screen_px=36):
    if len(points) < 2:
        return
    n = len(points)
    for i in range(n):
        p1 = points[i]
        p2 = points[(i + 1) % n]
        s1 = world_to_screen(*p1)
        s2 = world_to_screen(*p2)
        if math.hypot(s2[0] - s1[0], s2[1] - s1[1]) < min_screen_px:
            continue
        dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        draw_dimension_label(surface, p1, p2, _format_length_mm(dist))


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
        ox, oy = rect_offset(t)
        w, h = t.get("width", 0), t.get("height", 0)
        return [
            ("br", (ox + w, oy + h)),
            ("tr", (ox + w, oy)),
            ("bl", (ox, oy + h)),
        ]
    if t["type"] == "circle":
        cx, cy = circle_center(t)
        rx, ry = circle_radii(t)
        return [
            ("rx", (cx + rx, cy)),
            ("-rx", (cx - rx, cy)),
            ("ry", (cx, cy + ry)),
            ("-ry", (cx, cy - ry)),
        ]
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
        ox, oy = rect_offset(t)
        w, h = t.get("width", 0), t.get("height", 0)
        if handle_id == "br":
            t["width"] = int(max(GRID_SNAP, wx - ox))
            t["height"] = int(max(GRID_SNAP, wy - oy))
        elif handle_id == "tr":
            t["width"] = int(max(GRID_SNAP, wx - ox))
        elif handle_id == "bl":
            t["height"] = int(max(GRID_SNAP, wy - oy))
    elif t["type"] == "circle":
        cx, cy = circle_center(t)
        if handle_id in ("rx", "-rx"):
            t["radius_x"] = int(max(GRID_SNAP, abs(wx - cx)))
            t.pop("radius", None)
        elif handle_id in ("ry", "-ry"):
            t["radius_y"] = int(max(GRID_SNAP, abs(wy - cy)))
            t.pop("radius", None)
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
    t = editing_template
    if t["type"] == "rectangle" and len(pts) >= 4:
        draw_edge_dimensions(surface, pts)
    elif t["type"] == "circle":
        cx, cy = circle_center(t)
        rx, ry = circle_radii(t)
        draw_dimension_label(surface, (cx, cy), (cx + rx, cy), f"Rx {_format_length_mm(rx)}")
        draw_dimension_label(surface, (cx, cy), (cx, cy + ry), f"Ry {_format_length_mm(ry)}")
    elif t["type"] == "polygon" and len(pts) >= 3:
        draw_edge_dimensions(surface, pts)


def draw_canvas(surface):
    sw, sh = surface.get_width(), surface.get_height()
    surface.fill(C_CANVAS)
    draw_grid(surface)

    if editing_template:
        pts = normalize_template_dict(editing_template)
        is_circle = editing_template.get("type") == "circle"
        draw_shape(surface, pts, fill=(254, 243, 199), border=(217, 119, 6), show_vertices=not is_circle)
        draw_resize_handles(surface)

    if current_tool == "polygon" and polygon_points:
        pts = polygon_points + ([preview_point] if preview_point else [])
        draw_shape(surface, pts, closed=False)
        if len(polygon_points) >= 2:
            p1, p2 = polygon_points[-2], polygon_points[-1]
            draw_dimension_label(surface, p1, p2, _format_length_mm(math.hypot(p2[0] - p1[0], p2[1] - p1[1])))
        if len(polygon_points) >= 3:
            fx, fy = world_to_screen(polygon_points[0][0], polygon_points[0][1])
            pygame.draw.circle(surface, C_ACCENT, (int(fx), int(fy)), 7, 2)
            if preview_point:
                near_close = math.hypot(mouse_pos[0] - fx, mouse_pos[1] - fy) <= POLYGON_CLOSE_PX
                if near_close:
                    pygame.draw.circle(surface, C_ACCENT, (int(fx), int(fy)), 11, 2)
                    close_line = [
                        world_to_screen(*polygon_points[-1]),
                        world_to_screen(*preview_point),
                        (fx, fy),
                    ]
                    pygame.draw.lines(surface, C_ACCENT, False, close_line, 2)

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
            draw_shape(surface, pts, show_vertices=False)
            draw_dimension_label(surface, (cx, cy), drag_current, f"R {_format_length_mm(r)}")
        elif current_tool == "l_shape":
            pts = polygon_from_rect(*drag_start, *drag_current)
            draw_shape(surface, pts)
            w = abs(drag_current[0] - drag_start[0])
            h = abs(drag_current[1] - drag_start[1])
            draw_dimension_label(surface, pts[0], pts[1], _format_length_mm(w))
            draw_dimension_label(surface, pts[1], pts[2], _format_length_mm(h))

    if draw_phase == "l_cut" and l_outer_corners and l_cut_preview:
        x0, y0, x1, y1 = l_outer_corners
        cx, cy = l_cut_preview
        pts = polygon_from_l_shape(x0, y0, x1, y1, cx, cy)
        draw_shape(surface, pts)
        draw_edge_dimensions(surface, pts)

    # 十字中心线
    cx, cy = world_to_screen(0, 0)
    pygame.draw.line(surface, (148, 163, 184), (SIDEBAR_WIDTH, cy), (sw, cy), 1)
    pygame.draw.line(surface, (148, 163, 184), (cx, 0), (cx, sh), 1)

    if current_tool == "polygon" and draw_phase != "idle":
        banner = pygame.Rect(SIDEBAR_WIDTH + 16, 12, sw - SIDEBAR_WIDTH - 32, 34)
        pygame.draw.rect(surface, (219, 234, 254), banner, border_radius=8)
        tip = "多边形: 左键加点 | 点击起点闭合 | Enter 完成 | Esc 取消"
        surface.blit(FONT_SMALL.render(tip, True, C_ACCENT), (banner.x + 12, banner.y + 9))
    elif draw_phase == "drawing" and current_tool == "l_shape":
        tip = "拖拽绘制 L 形外框（实时显示尺寸），松开后点击内角"
    elif draw_phase == "drawing":
        tip = "拖拽绘制形状，松开鼠标完成"
        surface.blit(FONT_SMALL.render(tip, True, C_MUTED), (SIDEBAR_WIDTH + 16, 12))
    elif draw_phase == "l_cut":
        tip = "第二步: 移动鼠标预览 L 形，点击确定内角位置"
        surface.blit(FONT_SMALL.render(tip, True, C_MUTED), (SIDEBAR_WIDTH + 16, 12))
    elif editing_template and draw_phase == "idle":
        tip = "左键拖动移动 | 橙色手柄调整大小 | 圆/椭圆拖四向轴点 | Ctrl+Z 撤销"
        surface.blit(FONT_SMALL.render(tip, True, C_MUTED), (SIDEBAR_WIDTH + 16, 12))
    elif draw_phase == "idle":
        tip = "自动对齐 10cm 网格 | 按住 Shift 自由绘制"
        surface.blit(FONT_SMALL.render(tip, True, C_MUTED), (SIDEBAR_WIDTH + 16, 12))


def draw_product_reference_card(surface):
    pad = 16
    w = SIDEBAR_WIDTH - pad * 2
    card = pygame.Rect(pad, 58, w, SIDEBAR_PRODUCT_CARD_H)
    pygame.draw.rect(surface, C_SIDEBAR_DARK, card, border_radius=8)
    pygame.draw.rect(surface, C_SIDEBAR_HOVER, card, 1, border_radius=8)

    item = _template_display_item(editing_template)
    if item is None and selected_display_key:
        item = _find_display_item(selected_display_key)

    img_rect = pygame.Rect(card.x + 8, card.y + 8, 72, 88)
    pygame.draw.rect(surface, (30, 41, 59), img_rect, border_radius=6)
    text_x = img_rect.right + 10
    text_w = card.right - text_x - 8

    if item:
        if getattr(item, "is_discontinued", False):
            pygame.draw.rect(surface, ui.C_DISCONTINUED_BORDER, card, 2, border_radius=8)
            ui.draw_discontinued_badge(surface, card, align="topright")
        if getattr(item, "image_url", ""):
            thumb = request_image(item.image_url, max_size=(120, 100))
            if thumb is not None:
                _blit_thumb_fit(surface, thumb, img_rect)
            elif not is_image_failed(item.image_url):
                wait = FONT_MARK.render("加载中…", True, C_SIDEBAR_MUTED)
                surface.blit(wait, wait.get_rect(center=img_rect.center))
            else:
                wait = FONT_MARK.render("无图", True, C_SIDEBAR_MUTED)
                surface.blit(wait, wait.get_rect(center=img_rect.center))
        else:
            wait = FONT_MARK.render("无图", True, C_SIDEBAR_MUTED)
            surface.blit(wait, wait.get_rect(center=img_rect.center))
        sku = (item.product_code or item.product_name or "").strip()
        name = item.product_name or sku
    else:
        sku = input_name.get_text().strip()
        name = sku or "未关联 Display 产品"
        hint = FONT_MARK.render("从大库打开测绘", True, C_SIDEBAR_MUTED)
        surface.blit(hint, hint.get_rect(center=img_rect.center))

    if sku:
        sku_surf = FONT_MARK.render(sku[:18], True, C_SIDEBAR_MUTED)
        surface.blit(sku_surf, (text_x, card.y + 10))
    name_lines = _wrap_text_lines(name, FONT_SMALL, text_w, max_lines=3)
    y = card.y + 30
    for line in name_lines:
        surface.blit(FONT_SMALL.render(line, True, C_SIDEBAR_TEXT), (text_x, y))
        y += 16


def _wrap_text_lines(text: str, font, max_width: int, max_lines: int = 3) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    if font.size(text)[0] <= max_width:
        return [text]
    lines = []
    chunk = ""
    for ch in text:
        trial = chunk + ch
        if font.size(trial)[0] <= max_width:
            chunk = trial
        else:
            if chunk:
                lines.append(chunk)
            chunk = ch
        if len(lines) >= max_lines:
            break
    if chunk and len(lines) < max_lines:
        lines.append(chunk)
    if len(lines) == max_lines and font.size(lines[-1])[0] > max_width - 8:
        lines[-1] = lines[-1][:-1] + "…"
    return lines or [text[:12] + "…"]


def build_sidebar():
    pad = 16
    w = SIDEBAR_WIDTH - pad * 2
    y = 58 + SIDEBAR_PRODUCT_CARD_H + 16
    tool_dropdown = Dropdown(
        (pad, y, w, 32),
        [(tool_id, label) for tool_id, label in TOOLS],
        current_tool,
        label="绘制工具",
        dropdown_id="tool",
    )
    y += 38

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
    return tool_dropdown, buttons


def draw_sidebar(tool_dropdown, buttons):
    draw_sidebar_bg(screen)
    draw_sidebar_header(screen, "家具模板编辑器", "Furniture Template")
    draw_product_reference_card(screen)

    pad = 16
    tools_y = 58 + SIDEBAR_PRODUCT_CARD_H + 8
    screen.blit(FONT_SMALL.render("绘制工具", True, C_SIDEBAR_MUTED), (pad, tools_y))

    tool_dropdown.selected = current_tool
    tool_dropdown.draw(screen, mouse_pos, on_dark=True, draw_menu=False)
    if tool_dropdown.open:
        tool_dropdown.draw_menu(screen, mouse_pos)
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
        if tpl.get("is_discontinued"):
            sub = (sub + " · 停产").strip(" ·")
    else:
        status = "未选中模板"
        sub = "从产品总览打开或新建"
    screen.blit(FONT_SMALL.render(status, True, C_SIDEBAR_TEXT), (pad, footer_y))
    screen.blit(FONT_MARK.render(sub, True, C_SIDEBAR_MUTED), (pad, footer_y + 18))
    hint = "Ctrl+Z 撤销  |  Ctrl+S 保存"
    screen.blit(FONT_MARK.render(hint, True, C_SIDEBAR_MUTED), (pad, footer_y - 14))


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
    clear_undo()
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
    """只更新 Product Family（名称锁定为 Display SKU）。"""
    global selected_index, editing_template, editing_mode
    if not editing_template and selected_index >= 0:
        editing_template = copy.deepcopy(furniture_templates[selected_index])
    if not editing_template:
        toast.show("请先选中模板，或从 Display 大库打开测绘")
        return
    display_item = _template_display_item(editing_template)
    if not display_item:
        toast.show("模板必须对应 Display 库产品，无法重命名游离项")
        return
    family = input_family.get_text().strip() or display_item.product_family or display_item.key
    roi = lookup_roi(family)
    if roi == 0:
        toast.show(f"警告: roi.xlsx 中未找到 {family}，ROI 将为 0")
    _bind_template_to_display(editing_template, display_item)
    editing_template["product_family"] = family
    editing_template["roi"] = roi
    input_name.set_text(editing_template["id"])
    input_family.set_text(family)

    if not _is_new_entry_mode() and selected_index >= 0:
        tpl = furniture_templates[selected_index]
        tpl.update({
            "id": editing_template["id"],
            "product_family": family,
            "roi": roi,
            "display_key": editing_template.get("display_key"),
            "source": "display",
        })
        editing_template = copy.deepcopy(tpl)
        toast.show(f"已更新 Family: {family}，ROI={roi:.1f}")
        write_templates_file(quiet=True)
        return

    if _duplicate_id(editing_template["id"]):
        toast.show(f"模板「{editing_template['id']}」已存在")
        return
    furniture_templates.append(copy.deepcopy(editing_template))
    selected_index = len(furniture_templates) - 1
    editing_mode = "edit"
    toast.show(f"新模板已添加: {editing_template['id']}，ROI={roi:.1f}")


def save_to_list():
    global selected_index, editing_mode, editing_template
    if not editing_template:
        apply_current_shape()
    if not editing_template:
        return
    display_item = _template_display_item(editing_template)
    if not display_item:
        toast.show("模板必须对应 Display 库产品，请从 Display 大库打开测绘")
        return
    _bind_template_to_display(editing_template, display_item)
    input_name.set_text(editing_template["id"])
    input_family.set_text(editing_template.get("product_family", ""))
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
    write_templates_file(quiet=True)


def write_templates_file(*, quiet: bool = False):
    if not furniture_templates:
        if not quiet:
            toast.show("列表为空，请先保存模板")
        return
    with open(TEMPLATES_FILE, "w", encoding="utf-8") as f:
        json.dump(furniture_templates, f, ensure_ascii=False, indent=2)
    if not quiet:
        toast.show(f"已写入 {TEMPLATES_FILE}")


def load_templates_file(path=TEMPLATES_FILE):
    global furniture_templates, selected_index
    if not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        furniture_templates = json.load(f)
    for tpl in furniture_templates:
        family = tpl.get("product_family") or tpl.get("id", "")
        tpl["product_family"] = family
        if "roi" in tpl:
            tpl["roi"] = float(tpl.get("roi") or 0)
        else:
            tpl["roi"] = lookup_roi(family)
        tpl["is_discontinued"] = resolve_is_discontinued(
            tpl.get("id", ""),
            tpl.get("is_discontinued"),
        )
    selected_index = -1
    removed = prune_templates_against_display(persist=path == TEMPLATES_FILE)
    if removed:
        toast.show(f"已加载 {len(furniture_templates)} 个模板，移除游离项: {', '.join(removed)}")
    else:
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
    clear_undo()
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
    if not selected_display_key:
        toast.show("请从 Display 大库选中目标产品后再粘贴")
        return False
    item = _find_display_item(selected_display_key)
    if not item:
        toast.show("未找到选中的 Display 产品")
        return False

    src = _template_clipboard
    new_tpl = copy.deepcopy(src)
    _bind_template_to_display(new_tpl, item)

    editing_template = new_tpl
    editing_mode = "copy"
    selected_index = -1
    draw_phase = "idle"
    input_name.set_text(new_tpl["id"])
    input_family.set_text(new_tpl.get("product_family", ""))

    if app_screen == "gallery":
        close_gallery()
    focus_input(input_family)
    toast.show(f"已粘贴到 {item.product_name}，调整后保存")
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
            begin_editor_mutation()
            resizing_handle = handle
            return
        if hit_template_body(mx, my):
            begin_editor_mutation()
            dragging_shape = True
            drag_shape_last_world = screen_to_world(mx, my)
            return
        return

    if current_tool == "polygon":
        if draw_phase == "idle":
            draw_phase = "drawing"
        if len(polygon_points) >= 3:
            fx, fy = world_to_screen(polygon_points[0][0], polygon_points[0][1])
            if math.hypot(mx - fx, my - fy) <= POLYGON_CLOSE_PX:
                finish_polygon()
                return
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
        push_undo()
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
    push_undo()

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

    # 大库里优先处理模型复制粘贴（即使搜索框曾获得焦点）
    if app_screen == "gallery":
        if ui.is_ctrl_key(event, "c"):
            if input_search.active:
                input_search.deactivate()
            return gallery_copy_model()
        if ui.is_ctrl_key(event, "v"):
            if input_search.active:
                input_search.deactivate()
            return gallery_paste_model()

    if input_name.active or input_family.active or input_search.active:
        return False

    if ui.is_ctrl_key(event, "c"):
        copy_template_to_clipboard()
        return True

    if ui.is_ctrl_key(event, "v"):
        paste_template_from_clipboard()
        return True

    return False


editor_tool_dropdown_open = False


def try_sidebar_click(pos, tool_dropdown, buttons):
    mx, my = pos
    return handle_sidebar_click(mx, my, tool_dropdown, buttons)


def handle_sidebar_click(mx, my, tool_dropdown, buttons):
    global editor_tool_dropdown_open
    hit = tool_dropdown.hit_test((mx, my))
    if isinstance(hit, tuple) and hit[0] == "pick":
        tool_dropdown.selected = hit[1]
        tool_dropdown.open = False
        editor_tool_dropdown_open = False
        handle_toolbar(f"tool:{hit[1]}")
        return True
    if hit == "trigger":
        tool_dropdown.open = not tool_dropdown.open
        editor_tool_dropdown_open = tool_dropdown.open
        return True
    if tool_dropdown.open and hit == "outside":
        tool_dropdown.open = False
        editor_tool_dropdown_open = False
        return True
    if tool_dropdown.open:
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
    input_name.set_text(item.product_code or item.product_name)
    input_family.set_text(item.product_family if item.product_family != "未分类" else "")
    editing_mode = "new"
    selected_index = -1
    open_editor_from_gallery()
    focus_input(input_name)
    toast.show(f"开始测绘: {item.product_name}（保存后点「返回 Display 大库」）")


def apply_template_to_display_item(item, src_tpl: dict) -> None:
    """把剪贴板里的模型形状绑定到指定 Display 产品（按 SKU 存模板）。"""
    global furniture_templates
    new_tpl = copy.deepcopy(src_tpl)
    _bind_template_to_display(new_tpl, item)
    tpl_id = new_tpl["id"]
    idx = find_template_index_by_id(furniture_templates, tpl_id)
    if idx >= 0:
        furniture_templates[idx] = new_tpl
        action = "已更新"
    else:
        furniture_templates.append(new_tpl)
        action = "已粘贴"
    with open(TEMPLATES_FILE, "w", encoding="utf-8") as f:
        json.dump(furniture_templates, f, ensure_ascii=False, indent=2)
    invalidate_shop_stats_cache()
    gallery_view.invalidate_layout()
    toast.show(f"{action}模型 → {item.product_name}")


def gallery_copy_model() -> bool:
    if not selected_display_key:
        toast.show("请先单击选中一个产品")
        return False
    item = _find_display_item(selected_display_key)
    if not item:
        return False
    idx = match_template_index(item, furniture_templates)
    if idx < 0:
        toast.show("该产品尚未测绘，无法复制")
        return False
    return copy_template_to_clipboard(furniture_templates[idx])


def gallery_paste_model() -> bool:
    if not selected_display_key:
        toast.show("请先单击选中目标产品")
        return False
    if not _template_clipboard:
        toast.show("剪贴板为空，请先 Ctrl+C 复制已测绘产品")
        return False
    item = _find_display_item(selected_display_key)
    if not item:
        return False
    apply_template_to_display_item(item, _template_clipboard)
    return True


def refresh_display_data(prefer_db: bool = True) -> None:
    global display_items
    try:
        if prefer_db:
            from display_lookup import grab_and_save
            from product_images import clear_image_cache

            display_items, excel_path = grab_and_save()
            clear_image_cache()
            invalidate_shop_stats_cache()
            gallery_view.sync_search_query()
            gallery_view.invalidate_layout()
            toast.show(f"已抓取 {len(display_items)} 款 → {os.path.basename(excel_path)}")
            return
    except Exception:
        pass
    display_items = reload_display_items(prefer_db=False)
    invalidate_shop_stats_cache()
    gallery_view.sync_search_query()
    gallery_view.invalidate_layout()
    src = last_load_source() or "display.xlsx"
    bl_n, bl_src, _ = blacklist_status()
    if display_items:
        toast.show(f"已刷新 {len(display_items)} 款 · 黑名单 {bl_n} 个 ({bl_src})")
    else:
        toast.show(last_load_error() or "请先运行 grab_display.bat")


def handle_gallery_click(mx, my):
    global selected_index, selected_display_key, display_shop
    global display_survey_filter, display_blacklist_mode
    global _last_gallery_display_pick
    hit = gallery_view.handle_click(mx, my)
    if hit == "back":
        close_gallery()
        return True
    if hit == "refresh":
        refresh_display_data(prefer_db=True)
        prune_templates_against_display()
        return True
    if hit == "gallery_copy":
        gallery_copy_model()
        return True
    if hit == "gallery_paste":
        gallery_paste_model()
        return True
    if isinstance(hit, str) and hit.startswith("shop:"):
        display_shop = hit.split(":", 1)[1]
        gallery_view.scroll_y = 0
        gallery_view.invalidate_layout()
        return True
    if isinstance(hit, str) and hit.startswith("survey:"):
        display_survey_filter = hit.split(":", 1)[1]
        gallery_view.scroll_y = 0
        gallery_view.invalidate_layout()
        return True
    if isinstance(hit, str) and hit.startswith("bl:"):
        display_blacklist_mode = hit.split(":", 1)[1]
        gallery_view.scroll_y = 0
        gallery_view.invalidate_layout()
        return True
    if isinstance(hit, tuple) and hit[0] == "display":
        key = hit[1]
        item = _find_display_item(key)
        if not item:
            return True
        blur_inputs()
        now = pygame.time.get_ticks()
        is_double = key == _last_gallery_display_pick["key"] and now - _last_gallery_display_pick["time"] < 400
        _last_gallery_display_pick = {"key": key, "time": now}
        tpl_idx = match_template_index(item, furniture_templates)
        if is_double:
            selected_display_key = key
            if tpl_idx >= 0:
                open_editor_from_gallery()
                load_template_into_editor(tpl_idx)
            else:
                begin_survey_display(item)
        else:
            selected_display_key = key
            if tpl_idx >= 0:
                toast.show(f"已选中: {item.product_name}（已测绘 · 点「复制」或 Ctrl+C）")
            else:
                toast.show(f"已选中: {item.product_name}（待测绘 · 先复制已测绘款，再点「粘贴」）")
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
    else:
        prune_templates_against_display(persist=False)

    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.RESIZABLE)
    pygame.display.set_caption(f"家具模板编辑器 v{ui.__version__}")
    clock = pygame.time.Clock()

    tool_dropdown, buttons = build_sidebar()
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
                        if handled and input_search.active and event.type == pygame.KEYDOWN:
                            if event.key in (
                                pygame.K_BACKSPACE,
                                pygame.K_DELETE,
                            ) or ui.is_ctrl_key(event, "v"):
                                gallery_view.mark_search_dirty()
                        if handled and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                            gallery_view.sync_search_query()
                            gallery_view.invalidate_layout()
                elif event.type in (pygame.TEXTEDITING, pygame.TEXTINPUT):
                    if input_search.active:
                        input_search.handle_event(event)
                        if event.type == pygame.TEXTINPUT:
                            gallery_view.mark_search_dirty()

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
                                    try_sidebar_click(event.pos, tool_dropdown, buttons)
                            _sidebar_click_start = None
                        else:
                            if resizing_handle is not None:
                                resizing_handle = None
                                end_editor_mutation()
                                toast.show("尺寸已更新")
                            elif dragging_shape:
                                dragging_shape = False
                                drag_shape_last_world = None
                                end_editor_mutation()
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

                    if handle_editor_shortcuts(event):
                        pass
                    else:
                        handled = (
                            input_name.handle_event(event)
                            or input_family.handle_event(event)
                        )
                        if handled:
                            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                                handle_enter_action()
                        elif handle_global_clipboard_shortcuts(event):
                            pass
                        elif current_tool == "polygon" and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                            finish_polygon()
                        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                            handle_enter_action()
                        elif current_tool == "polygon":
                            if event.key == pygame.K_ESCAPE:
                                polygon_points = []
                                draw_phase = "idle"
                                preview_point = None
                        elif event.key == pygame.K_ESCAPE:
                            if return_to_gallery_after_edit and draw_phase == "idle":
                                if input_name.active or input_family.active:
                                    blur_inputs()
                                else:
                                    return_to_gallery_view()

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
            gallery_view.tick_search_debounce()
            gallery_view.draw(screen, furniture_templates, selected_index)
            tick_input_focus()
            toast.draw(screen, screen.get_width() // 2)
        else:
            draw_canvas(screen)
            draw_sidebar(tool_dropdown, buttons)
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
