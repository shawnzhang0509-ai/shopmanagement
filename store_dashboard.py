#!/usr/bin/env python3
"""多店汇总 · 系列横向对比 — 一屏看多店，可选 4/8/12 周。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import traceback

from layout_preview_render import render_layout_preview

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

import pygame

from store_dashboard_data import (
    FILTER_ALL,
    FILTER_LAYOUT,
    STORE_COLORS,
    STORE_ENTRIES,
    WEEK_OPTIONS,
    aggregate_family_comparison,
    aggregate_store_overviews,
    compare_store_columns,
    count_attention_families,
    entries_for_ui,
    filter_attention_rows,
    sidebar_color_index,
    list_recent_week_keys_global,
    slug_to_entry,
    week_range_label,
)
from layout_family_lookup import families_in_layout, families_in_layouts, layout_file_exists, load_layout_snapshot
from sales_lookup import sales_data_available
from ui_common import (
    C_ACCENT,
    C_BG,
    C_BORDER,
    C_MUTED,
    C_SIDEBAR,
    C_SIDEBAR_DARK,
    C_SIDEBAR_TEXT,
    C_TEXT,
    Button,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    init_fonts,
    load_font,
)

SIDEBAR_W = 260
HEADER_H = 92
PAD = 14
C_WARN = (234, 88, 12)
C_ATTENTION_BG = (255, 247, 237)
C_ROW_EVEN = (255, 255, 255)
C_ROW_ODD = (238, 242, 248)
C_ROW_LINE = (203, 213, 225)
C_ROW_HOVER = (219, 234, 254)
C_LABEL_COL = (252, 253, 255)

VIEW_OVERVIEW = "overview"
VIEW_COMPARE = "compare"
VIEW_LAYOUTS = "layouts"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _money(n: float) -> str:
    v = float(n or 0)
    if v >= 1_000_000:
        return f"${v / 1_000_000:.1f}M"
    if v >= 1000:
        return f"${v:,.0f}"
    if v >= 1:
        return f"${v:.0f}"
    return "$0"


def _truncate(font, text: str, max_w: int) -> str:
    if font.size(text)[0] <= max_w:
        return text
    ell = "…"
    t = text
    while t and font.size(t + ell)[0] > max_w:
        t = t[:-1]
    return (t + ell) if t else ell


class StoreDashboard:
    def __init__(self) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.RESIZABLE)
        pygame.display.set_caption("多店汇总 · 系列对比")
        self.clock = pygame.time.Clock()
        init_fonts()
        self.font_title = load_font(20, bold=True)
        self.font_body = load_font(15)
        self.font_small = load_font(12)
        self.font_tiny = load_font(11)

        self.view = VIEW_LAYOUTS
        self.family_filter = FILTER_LAYOUT
        self.remediation_only = False
        self.num_weeks = 8
        self.attention_count = 0
        self.compare_hover_row: int | None = None
        self.week_keys: list[str] = []
        self.scroll_y = 0
        self._data_dirty = True
        self.overviews = []
        self.compare_columns: list = []
        self.compare_rows = []

        self.selected_slugs: set[str] = {e["slug"] for e in STORE_ENTRIES}
        self.store_toggles: list[tuple[pygame.Rect, dict]] = []
        self.buttons: list[Button] = []
        self.layout_cards: list[tuple[pygame.Rect, str]] = []
        self.status = ""

        self._rebuild_toolbar()
        self.refresh_data()

    def _shop_ids(self) -> list[str]:
        from store_dashboard_data import unique_shop_ids_from_entries

        return unique_shop_ids_from_entries(self.selected_slugs)

    def refresh_data(self) -> None:
        if not sales_data_available():
            self.week_keys = []
            self.overviews = []
            self.compare_columns = []
            self.compare_rows = []
            from sales_lookup import resolve_weekly_sales_path

            rel = os.path.relpath(resolve_weekly_sales_path(), os.path.dirname(__file__))
            self.status = f"缺少 {rel} — 请在当前区域运行 grab_sales.bat"
            self._data_dirty = False
            return

        self.week_keys = list_recent_week_keys_global(self.num_weeks)
        shop_ids = self._shop_ids()
        self.overviews = aggregate_store_overviews(
            shop_ids, self.week_keys, selected_slugs=self.selected_slugs
        )
        self.compare_columns = compare_store_columns(self.selected_slugs, self.overviews)
        top_n = None if self.family_filter == FILTER_LAYOUT else 100
        self.compare_rows = aggregate_family_comparison(
            shop_ids,
            self.week_keys,
            selected_slugs=self.selected_slugs,
            family_filter=self.family_filter,
            top_n=top_n,
        )
        self.attention_count = count_attention_families(self.compare_rows)
        self._update_status_line()
        self._data_dirty = False

    def _rebuild_toolbar(self) -> None:
        self.buttons = []
        y = 8
        x = SIDEBAR_W + PAD
        for label, view in (("门店汇总", VIEW_OVERVIEW), ("系列对比", VIEW_COMPARE), ("布局预览", VIEW_LAYOUTS)):
            self.buttons.append(Button((x, y, 80, 30), label, lambda v=view: self._set_view(v), toggle=True))
            self.buttons[-1].active = self.view == view
            x += 86
        x += 8
        for label, n in WEEK_OPTIONS:
            def make_week(w=n):
                return lambda: self._set_weeks(w)

            self.buttons.append(Button((x, y, 52, 30), label, make_week(), toggle=True))
            self.buttons[-1].active = self.num_weeks == n
            x += 58
        y += 36
        x = SIDEBAR_W + PAD
        self.buttons.append(
            Button((x, y, 88, 28), "全部系列", lambda: self._set_family_filter(FILTER_ALL), toggle=True)
        )
        self.buttons[-1].active = self.family_filter == FILTER_ALL
        x += 96
        self.buttons.append(
            Button((x, y, 88, 28), "布局系列", lambda: self._set_family_filter(FILTER_LAYOUT), toggle=True)
        )
        self.buttons[-1].active = self.family_filter == FILTER_LAYOUT
        x += 96
        rem_label = f"整改提醒 ({self.attention_count})" if self.attention_count else "整改提醒"
        self.buttons.append(
            Button((x, y, 96, 28), rem_label, lambda: self._toggle_remediation(), toggle=True)
        )
        self.buttons[-1].active = self.remediation_only

    def _visible_compare_rows(self):
        if self.remediation_only:
            return filter_attention_rows(self.compare_rows)
        return self.compare_rows

    def _toggle_remediation(self) -> None:
        self.remediation_only = not self.remediation_only
        self.scroll_y = 0
        self._rebuild_toolbar()
        self._update_status_line()

    def _update_status_line(self) -> None:
        if not self.week_keys:
            return
        layout_n = len(families_in_layouts(self.selected_slugs))
        filt = "布局系列" if self.family_filter == FILTER_LAYOUT else "全部系列"
        visible_n = len(self._visible_compare_rows())
        self.status = (
            f"近 {self.num_weeks} 周 · {week_range_label(self.week_keys)} · "
            f"{filt} · 显示 {visible_n} 行"
        )
        if self.attention_count:
            self.status += f" · ⚠ {self.attention_count} 系列方差大/垫店需整改"
        if self.family_filter == FILTER_LAYOUT:
            self.status += f"（布局共 {layout_n} 个系列）"

    def _set_family_filter(self, mode: str) -> None:
        self.family_filter = mode
        self._data_dirty = True
        self._rebuild_toolbar()

    def _set_view(self, view: str) -> None:
        self.view = view
        self.scroll_y = 0
        self._rebuild_toolbar()

    def _set_weeks(self, n: int) -> None:
        self.num_weeks = n
        self._data_dirty = True
        self._rebuild_toolbar()

    def _toggle_slug(self, slug: str) -> None:
        if slug in self.selected_slugs:
            if len(self.selected_slugs) <= 1:
                self.status = "至少保留一个门店"
                return
            self.selected_slugs.remove(slug)
        else:
            self.selected_slugs.add(slug)
        self._data_dirty = True

    def run(self) -> None:
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
                if event.type == pygame.VIDEORESIZE:
                    self.screen = pygame.display.set_mode(event.size, pygame.RESIZABLE)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self._click(event.pos)
                elif event.type == pygame.MOUSEWHEEL:
                    self.scroll_y = max(0, self.scroll_y - event.y * 36)

            if self._data_dirty:
                self.refresh_data()

            w, h = self.screen.get_size()
            mouse = pygame.mouse.get_pos()
            self.screen.fill(C_BG)
            self._draw_sidebar(w, h, mouse)
            self._draw_header(w, mouse)
            if self.view == VIEW_OVERVIEW:
                self._draw_overview(w, h)
            elif self.view == VIEW_COMPARE:
                self._draw_compare(w, h, mouse)
            else:
                self._draw_layouts(w, h)
            if self.status:
                surf = self.font_small.render(self.status, True, C_MUTED)
                self.screen.blit(surf, (SIDEBAR_W + PAD, h - 24))
            pygame.display.flip()
            self.clock.tick(60)

    def _click(self, pos: tuple[int, int]) -> None:
        mx, my = pos
        for rect, entry in self.store_toggles:
            if rect.collidepoint(mx, my):
                self._toggle_slug(entry["slug"])
                return
        for btn in self.buttons:
            if btn.contains(pos):
                btn.action()
                return
        for rect, slug in self.layout_cards:
            if rect.collidepoint(mx, my):
                self._open_layout_editor(slug)
                return

    def _draw_sidebar(self, w: int, h: int, mouse: tuple[int, int]) -> None:
        pygame.draw.rect(self.screen, C_SIDEBAR, (0, 0, SIDEBAR_W, h))
        title = self.font_title.render("门店选择", True, C_SIDEBAR_TEXT)
        self.screen.blit(title, (PAD, PAD))
        hint = self.font_tiny.render("勾选要一起看的店", True, (149, 165, 166))
        self.screen.blit(hint, (PAD, PAD + 28))

        self.store_toggles = []
        y = 72
        for i, entry in enumerate(entries_for_ui()):
            checked = entry["slug"] in self.selected_slugs
            rect = pygame.Rect(PAD, y, SIDEBAR_W - PAD * 2, 36)
            self.store_toggles.append((rect, entry))
            hover = rect.collidepoint(mouse)
            bg = C_SIDEBAR_DARK if hover else C_SIDEBAR
            pygame.draw.rect(self.screen, bg, rect, border_radius=6)
            box = pygame.Rect(rect.x + 8, rect.centery - 8, 16, 16)
            pygame.draw.rect(self.screen, (255, 255, 255), box, border_radius=3)
            if checked:
                pygame.draw.rect(self.screen, C_ACCENT, box.inflate(-4, -4), border_radius=2)
            color = STORE_COLORS[i % len(STORE_COLORS)]
            pygame.draw.circle(self.screen, color, (rect.x + 36, rect.centery), 5)
            label = _truncate(self.font_body, entry["name"], rect.width - 52)
            self.screen.blit(self.font_body.render(label, True, C_SIDEBAR_TEXT), (rect.x + 48, rect.y + 8))
            y += 42

    def _draw_header(self, w: int, mouse: tuple[int, int]) -> None:
        pygame.draw.line(self.screen, C_BORDER, (SIDEBAR_W, HEADER_H), (w, HEADER_H), 1)
        for btn in self.buttons:
            btn.draw(self.screen, mouse)

    def _draw_overview(self, w: int, h: int) -> None:
        area = pygame.Rect(SIDEBAR_W + PAD, HEADER_H + PAD, w - SIDEBAR_W - PAD * 2, h - HEADER_H - PAD * 2 - 28)
        if not self.overviews:
            msg = "暂无数据" if sales_data_available() else "请先抓取周销量"
            surf = self.font_body.render(msg, True, C_MUTED)
            self.screen.blit(surf, (area.x, area.y))
            return

        cols = 2 if area.width < 900 else 3
        gap = 12
        card_w = (area.width - gap * (cols - 1)) // cols
        card_h = min(220, (area.height - gap) // 2)

        for i, ov in enumerate(self.overviews):
            col = i % cols
            row = i // cols
            x = area.x + col * (card_w + gap)
            y = area.y + row * (card_h + gap) - self.scroll_y
            if y + card_h < area.y or y > area.bottom:
                continue
            self._draw_store_card(pygame.Rect(x, y, card_w, card_h), ov, i)

    def _draw_store_card(self, rect: pygame.Rect, ov, color_idx: int) -> None:
        pygame.draw.rect(self.screen, (255, 255, 255), rect, border_radius=10)
        pygame.draw.rect(self.screen, C_BORDER, rect, 1, border_radius=10)
        accent = STORE_COLORS[color_idx % len(STORE_COLORS)]
        pygame.draw.rect(self.screen, accent, (rect.x, rect.y, 6, rect.height), border_radius=10)

        self.screen.blit(self.font_title.render(ov.name, True, C_TEXT), (rect.x + 16, rect.y + 12))
        total_s = self.font_body.render(f"销售额 {_money(ov.total_amount)}", True, C_TEXT)
        self.screen.blit(total_s, (rect.x + 16, rect.y + 42))
        qty_s = self.font_small.render(f"销量 {ov.total_qty:,.0f}", True, C_MUTED)
        self.screen.blit(qty_s, (rect.x + 16, rect.y + 64))
        lay_s = self.font_tiny.render(f"布局 {ov.layout_family_count} 系列", True, C_MUTED)
        self.screen.blit(lay_s, (rect.x + 16, rect.y + 80))

        self.screen.blit(self.font_small.render("Top 系列", True, C_MUTED), (rect.x + 16, rect.y + 96))
        max_amt = max((a for _, a in ov.top_families), default=1.0) or 1.0
        bar_x = rect.x + 16
        bar_w = rect.width - 32
        y = rect.y + 116
        for fam, amt in ov.top_families[:5]:
            if y + 22 > rect.bottom - 8:
                break
            label = _truncate(self.font_tiny, fam, int(bar_w * 0.42))
            self.screen.blit(self.font_tiny.render(label, True, C_TEXT), (bar_x, y))
            bw = max(4, int((amt / max_amt) * (bar_w * 0.52)))
            bar_rect = pygame.Rect(bar_x + int(bar_w * 0.44), y + 2, bw, 12)
            pygame.draw.rect(self.screen, accent, bar_rect, border_radius=3)
            amt_s = self.font_tiny.render(_money(amt), True, C_MUTED)
            self.screen.blit(amt_s, (bar_rect.right + 6, y))
            y += 22

    def _compare_row_index(self, mouse: tuple[int, int], area: pygame.Rect, bar_area_top: int, row_h: int, n_rows: int) -> int | None:
        mx, my = mouse
        if not area.collidepoint(mx, my) or my < bar_area_top:
            return None
        rel = my - bar_area_top + self.scroll_y
        idx = int(rel // row_h)
        if 0 <= idx < n_rows:
            return idx
        return None

    def _draw_compare(self, w: int, h: int, mouse: tuple[int, int] = (0, 0)) -> None:
        area = pygame.Rect(SIDEBAR_W + PAD, HEADER_H + PAD, w - SIDEBAR_W - PAD * 2, h - HEADER_H - PAD * 2 - 28)

        rows = self._visible_compare_rows()
        if not rows:
            if self.remediation_only and self.compare_rows:
                msg = "当前筛选下无「方差大且垫店」系列，可取消「整改提醒」查看全部"
            else:
                msg = "暂无系列数据" if sales_data_available() else "请先抓取周销量"
            self.screen.blit(self.font_body.render(msg, True, C_MUTED), (area.x, area.y))
            return

        columns = self.compare_columns or self.overviews
        row_h = 32
        header_h = 26
        meta_w = 132
        label_w = min(168, int(area.width * 0.2))
        chart_x = area.x + label_w + 6
        chart_w = max(120, area.width - label_w - meta_w - 20)
        n_stores = max(1, len(columns))
        seg_w = max(24, (chart_w - (n_stores - 1) * 6) // n_stores)
        bar_area_top = area.y + header_h

        for i, col in enumerate(columns):
            bx = chart_x + i * (seg_w + 6)
            ci = sidebar_color_index(col.slug)
            c = STORE_COLORS[ci % len(STORE_COLORS)]
            hdr = pygame.Rect(bx, area.y + 2, seg_w, header_h - 4)
            pygame.draw.rect(self.screen, (250, 251, 253), hdr, border_radius=4)
            pygame.draw.rect(self.screen, C_ROW_LINE, hdr, 1, border_radius=4)
            pygame.draw.rect(self.screen, c, (bx + 4, area.y + 6, 10, 10), border_radius=2)
            short = col.name.replace("店", "").replace("基督城 ", "")
            short = _truncate(self.font_tiny, short, seg_w - 18)
            self.screen.blit(self.font_tiny.render(short, True, C_TEXT), (bx + 16, area.y + 5))

        chart_h = len(rows) * row_h
        content_h = chart_h + header_h + 12
        max_scroll = max(0, content_h - area.height + 40)
        self.scroll_y = min(self.scroll_y, max_scroll)

        max_val = max((max(r.by_store.values(), default=0) for r in rows), default=1.0) or 1.0
        hover_idx = self._compare_row_index(mouse, area, bar_area_top, row_h, len(rows))
        self.compare_hover_row = hover_idx

        label_col = pygame.Rect(area.x, area.y, label_w, area.height)
        pygame.draw.rect(self.screen, C_LABEL_COL, label_col)
        pygame.draw.line(self.screen, C_ROW_LINE, (chart_x - 1, area.y), (chart_x - 1, area.bottom), 2)
        pygame.draw.line(
            self.screen,
            C_ROW_LINE,
            (area.right - meta_w, area.y),
            (area.right - meta_w, area.bottom),
            2,
        )

        prev_clip = self.screen.get_clip()
        self.screen.set_clip(area)
        y = bar_area_top - self.scroll_y
        row_idx = 0
        for row in rows:
            if y + row_h < area.y or y > area.bottom:
                y += row_h
                row_idx += 1
                continue
            row_band = pygame.Rect(area.x, y, area.width, row_h)
            hovered = hover_idx is not None and row_idx == hover_idx
            if hovered:
                pygame.draw.rect(self.screen, C_ROW_HOVER, row_band)
                pygame.draw.line(self.screen, C_ACCENT, (area.x, y + row_h // 2), (area.right - meta_w, y + row_h // 2), 1)
            elif row.attention:
                pygame.draw.rect(self.screen, C_ATTENTION_BG, row_band)
            else:
                pygame.draw.rect(
                    self.screen,
                    C_ROW_EVEN if row_idx % 2 == 0 else C_ROW_ODD,
                    row_band,
                )
            label_bg = pygame.Rect(area.x, y, label_w, row_h)
            if hovered:
                pygame.draw.rect(self.screen, C_ROW_HOVER, label_bg)
            else:
                pygame.draw.rect(
                    self.screen,
                    C_LABEL_COL if row_idx % 2 == 0 else (248, 250, 252),
                    label_bg,
                )
            pygame.draw.line(
                self.screen,
                C_ROW_LINE,
                (area.x, y + row_h),
                (area.right, y + row_h),
                1,
            )
            fam = _truncate(self.font_small, row.family, label_w - 28)
            label_x = area.x + 4
            if row.on_layout:
                pygame.draw.circle(self.screen, C_ACCENT, (area.x + 10, y + row_h // 2), 4)
                label_x += 14
            if row.attention:
                self.screen.blit(self.font_small.render("⚠", True, C_WARN), (label_x, y + 7))
                label_x += 16
            self.screen.blit(self.font_small.render(fam, True, C_TEXT), (label_x, y + 8))
            for i, col in enumerate(columns):
                bx = chart_x + i * (seg_w + 6)
                seg_rect = pygame.Rect(bx, y + 2, seg_w, row_h - 4)
                ci = sidebar_color_index(col.slug)
                c = STORE_COLORS[ci % len(STORE_COLORS)]
                amt = row.by_slug.get(col.slug, row.by_store.get(col.shop_id, 0.0))
                bw = max(2, int((amt / max_val) * (seg_w - 8))) if amt > 0 else 0
                is_min = row.attention and col.slug == row.min_slug
                cell_bg = (255, 255, 255) if row_idx % 2 == 0 else (248, 250, 253)
                if hovered:
                    cell_bg = C_ROW_HOVER
                pygame.draw.rect(self.screen, cell_bg, seg_rect, border_radius=2)
                pygame.draw.rect(self.screen, (230, 235, 242), seg_rect, 1, border_radius=2)
                bar_x = bx + 4
                bar_y = y + 10
                if bw > 0:
                    bar = pygame.Rect(bar_x, bar_y, bw, 12)
                    pygame.draw.rect(self.screen, c, bar, border_radius=3)
                    if is_min:
                        pygame.draw.rect(self.screen, c, bar.inflate(4, 4), 2, border_radius=4)
                elif is_min:
                    pygame.draw.rect(self.screen, c, seg_rect.inflate(-4, -4), 2, border_radius=3)
                    dash = self.font_tiny.render("—", True, C_MUTED)
                    self.screen.blit(dash, dash.get_rect(center=seg_rect.center))
                if hovered and amt > 0:
                    val = _truncate(self.font_tiny, _money(amt), seg_w - 6)
                    val_s = self.font_tiny.render(val, True, C_TEXT)
                    vx = min(seg_rect.right - val_s.get_width() - 2, bar_x + bw + 2)
                    self.screen.blit(val_s, (vx, y + 8))
            meta_x = area.right - meta_w + 4
            if row.attention and row.spread_cv > 0:
                short_min = (row.min_store_name or "").replace("店", "").replace("基督城 ", "")
                meta = f"↓{_truncate(self.font_tiny, short_min, 36)} CV{int(row.spread_cv * 100)}%"
                meta += f"  {_money(row.total)}"
                meta_s = self.font_tiny.render(_truncate(self.font_tiny, meta, meta_w - 8), True, C_MUTED)
            else:
                meta_s = self.font_tiny.render(_money(row.total), True, C_MUTED)
            self.screen.blit(meta_s, (meta_x + meta_w - 8 - meta_s.get_width(), y + 9))
            y += row_h
            row_idx += 1
        self.screen.set_clip(prev_clip)

        for i in range(n_stores + 1):
            gx = chart_x + i * (seg_w + 6) - 3
            pygame.draw.line(
                self.screen,
                (236, 240, 245),
                (gx, bar_area_top - self.scroll_y),
                (gx, min(area.bottom, bar_area_top - self.scroll_y + chart_h)),
                1,
            )

        hint = "● = 布局已摆 · 鼠标移入高亮整行 · 滚轮浏览"
        if self.remediation_only:
            hint = "整改模式：列色粗框/「—」= 该店垫底 · 悬停看各店金额"
        elif self.family_filter == FILTER_LAYOUT:
            hint = "仅显示布局里有的系列 · 滚轮浏览"
        axis = self.font_tiny.render(hint, True, C_MUTED)
        self.screen.blit(axis, (area.x, area.bottom - 18))

    def _open_layout_editor(self, slug: str) -> None:
        from layout_family_lookup import layout_path_for_slug

        path = layout_path_for_slug(slug)
        if not os.path.isfile(path):
            self.status = f"找不到布局文件: {slug}"
            return
        from region_config import layouts_dir
        from display_lookup import load_grabber_config

        layouts_root = layouts_dir(load_grabber_config())
        last = os.path.join(layouts_root, "_last.json")
        os.makedirs(layouts_root, exist_ok=True)
        try:
            rel = os.path.relpath(path, layouts_root).replace("\\", "/")
            stored = rel if not rel.startswith("..") else path
        except ValueError:
            stored = path
        with open(last, "w", encoding="utf-8") as f:
            json.dump({"path": stored, "slug": slug}, f, ensure_ascii=False)
        kwargs: dict = {"cwd": SCRIPT_DIR}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
        subprocess.Popen([sys.executable, "layout.py"], **kwargs)
        name = slug_to_entry().get(slug, {}).get("name", slug)
        self.status = f"已打开布局编辑器: {name}"

    def _draw_layout_mini(self, surface, rect: pygame.Rect, slug: str, accent, title: str) -> None:
        pygame.draw.rect(surface, (255, 255, 255), rect, border_radius=10)
        pygame.draw.rect(surface, C_BORDER, rect, 1, border_radius=10)
        pygame.draw.rect(surface, accent, (rect.x, rect.y, 5, rect.height), border_radius=10)

        data = load_layout_snapshot(slug)
        store = (data or {}).get("store") or {}
        sw = float(store.get("width_mm", 0)) / 1000
        sh = float(store.get("height_mm", 0)) / 1000
        meta = f"{sw:g}×{sh:g} m" if sw and sh else ""
        surface.blit(self.font_body.render(title, True, C_TEXT), (rect.x + 12, rect.y + 8))
        if meta:
            surface.blit(self.font_tiny.render(meta, True, C_MUTED), (rect.x + 12, rect.y + 28))

        preview = pygame.Rect(rect.x + 8, rect.y + 44, rect.width - 16, rect.height - 68)
        if not data:
            msg = "无布局文件" if not layout_file_exists(slug) else "读取失败"
            surface.blit(self.font_small.render(msg, True, C_MUTED), (preview.centerx - 40, preview.centery))
            return

        stats = render_layout_preview(surface, preview, data)
        fam_n = len(families_in_layout(slug))
        footer = f"{stats['furniture_count']} 件 · {stats['obstacle_count']} 障碍 · {fam_n} 系列 · 点击打开编辑器"
        surface.blit(
            self.font_tiny.render(_truncate(self.font_tiny, footer, rect.width - 24), True, C_MUTED),
            (rect.x + 12, rect.bottom - 18),
        )

    def _draw_layouts(self, w: int, h: int) -> None:
        area = pygame.Rect(SIDEBAR_W + PAD, HEADER_H + PAD, w - SIDEBAR_W - PAD * 2, h - HEADER_H - PAD * 2 - 28)
        self.layout_cards = []
        entries = [e for e in entries_for_ui() if e["slug"] in self.selected_slugs]
        if not entries:
            self.screen.blit(self.font_body.render("请至少选一个门店", True, C_MUTED), (area.x, area.y))
            return

        cols = 1 if len(entries) <= 2 else 2
        gap = 16
        rows = (len(entries) + cols - 1) // cols
        card_h = max(280, (area.height - gap * (rows - 1)) // max(1, rows))
        card_w = (area.width - gap * (cols - 1)) // cols

        for i, entry in enumerate(entries):
            col = i % cols
            row = i // cols
            x = area.x + col * (card_w + gap)
            y = area.y + row * (card_h + gap) - self.scroll_y
            card = pygame.Rect(x, y, card_w, card_h)
            if y + card_h < area.y or y > area.bottom:
                continue
            self.layout_cards.append((card, entry["slug"]))
            self._draw_layout_mini(
                self.screen, card, entry["slug"], STORE_COLORS[i % len(STORE_COLORS)], entry["name"]
            )

        tip = self.font_tiny.render(
            "预览自动缩放到家具+墙体区域（与 layout 一致）· 点击卡片打开该店编辑器",
            True,
            C_MUTED,
        )
        self.screen.blit(tip, (area.x, area.bottom - 18))


def _show_fatal_error(detail: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("多店对比启动失败", detail[:2000])
        root.destroy()
    except Exception:
        print(detail, file=sys.stderr)
        try:
            input("按 Enter 关闭…")
        except EOFError:
            pass


def main() -> None:
    try:
        StoreDashboard().run()
    except Exception:
        _show_fatal_error(traceback.format_exc())
        raise SystemExit(1)


if __name__ == "__main__":
    main()
