#!/usr/bin/env python3
"""多店汇总 · 系列横向对比 — 一屏看多店，可选 4/8/12 周。"""
from __future__ import annotations

import os
import sys
import traceback

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

import pygame

from store_dashboard_data import (
    STORE_COLORS,
    STORE_ENTRIES,
    WEEK_OPTIONS,
    aggregate_family_comparison,
    aggregate_store_overviews,
    entries_for_ui,
    list_recent_week_keys_global,
    week_range_label,
)
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
HEADER_H = 56
PAD = 14

VIEW_OVERVIEW = "overview"
VIEW_COMPARE = "compare"


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

        self.view = VIEW_OVERVIEW
        self.num_weeks = 8
        self.week_keys: list[str] = []
        self.scroll_y = 0
        self._data_dirty = True
        self.overviews = []
        self.compare_rows = []

        self.selected_slugs: set[str] = {e["slug"] for e in STORE_ENTRIES}
        self.store_toggles: list[tuple[pygame.Rect, dict]] = []
        self.buttons: list[Button] = []
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
            self.compare_rows = []
            self.status = "缺少 data/weekly_sales.xlsx — 请先运行 grab_sales.bat"
            self._data_dirty = False
            return

        self.week_keys = list_recent_week_keys_global(self.num_weeks)
        shop_ids = self._shop_ids()
        self.overviews = aggregate_store_overviews(shop_ids, self.week_keys)
        self.compare_rows = aggregate_family_comparison(shop_ids, self.week_keys, top_n=20)
        self.status = f"近 {self.num_weeks} 周 · {week_range_label(self.week_keys)} · {len(shop_ids)} 个销售门店"
        self._data_dirty = False

    def _rebuild_toolbar(self) -> None:
        self.buttons = []
        y = 12
        x = SIDEBAR_W + PAD
        self.buttons.append(
            Button((x, y, 88, 32), "门店汇总", lambda: self._set_view(VIEW_OVERVIEW), toggle=True)
        )
        self.buttons[0].active = self.view == VIEW_OVERVIEW
        x += 96
        self.buttons.append(
            Button((x, y, 88, 32), "系列对比", lambda: self._set_view(VIEW_COMPARE), toggle=True)
        )
        self.buttons[1].active = self.view == VIEW_COMPARE
        x += 104
        for label, n in WEEK_OPTIONS:
            def make_week(w=n):
                return lambda: self._set_weeks(w)

            self.buttons.append(Button((x, y, 56, 32), label, make_week(), toggle=True))
            self.buttons[-1].active = self.num_weeks == n
            x += 64

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
            else:
                self._draw_compare(w, h)
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

        self.screen.blit(self.font_small.render("Top 系列", True, C_MUTED), (rect.x + 16, rect.y + 88))
        max_amt = max((a for _, a in ov.top_families), default=1.0) or 1.0
        bar_x = rect.x + 16
        bar_w = rect.width - 32
        y = rect.y + 108
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

    def _draw_compare(self, w: int, h: int) -> None:
        area = pygame.Rect(SIDEBAR_W + PAD, HEADER_H + PAD, w - SIDEBAR_W - PAD * 2, h - HEADER_H - PAD * 2 - 28)

        if not self.compare_rows:
            msg = "暂无系列数据" if sales_data_available() else "请先抓取周销量"
            self.screen.blit(self.font_body.render(msg, True, C_MUTED), (area.x, area.y))
            return

        lx = area.x
        ly = area.y
        for i, ov in enumerate(self.overviews):
            c = STORE_COLORS[i % len(STORE_COLORS)]
            pygame.draw.rect(self.screen, c, (lx, ly + 4, 12, 12), border_radius=2)
            short = ov.name.replace("店", "")
            self.screen.blit(self.font_tiny.render(short, True, C_TEXT), (lx + 16, ly))
            lx += self.font_tiny.size(short)[0] + 36

        row_h = 28
        bar_area_top = area.y + 28
        chart_h = len(self.compare_rows) * row_h
        content_h = chart_h + 20
        max_scroll = max(0, content_h - area.height + 40)
        self.scroll_y = min(self.scroll_y, max_scroll)

        max_val = max((max(r.by_store.values(), default=0) for r in self.compare_rows), default=1.0) or 1.0
        label_w = min(160, int(area.width * 0.22))
        chart_x = area.x + label_w + 8
        chart_w = area.width - label_w - 16
        n_stores = max(1, len(self.overviews))
        seg_w = max(20, (chart_w - (n_stores - 1) * 4) // n_stores)

        y = bar_area_top - self.scroll_y
        for row in self.compare_rows:
            if y + row_h < area.y or y > area.bottom:
                y += row_h
                continue
            fam = _truncate(self.font_small, row.family, label_w - 8)
            self.screen.blit(self.font_small.render(fam, True, C_TEXT), (area.x, y + 4))
            bx = chart_x
            for i, ov in enumerate(self.overviews):
                amt = row.by_store.get(ov.shop_id, 0.0)
                bw = max(2, int((amt / max_val) * seg_w)) if amt > 0 else 0
                c = STORE_COLORS[i % len(STORE_COLORS)]
                if bw > 0:
                    pygame.draw.rect(self.screen, c, (bx, y + 6, bw, 16), border_radius=3)
                bx += seg_w + 4
            total_s = self.font_tiny.render(_money(row.total), True, C_MUTED)
            self.screen.blit(total_s, (area.right - total_s.get_width(), y + 6))
            y += row_h

        axis = self.font_tiny.render("横向柱 = 各店该系列销售额（滚轮上下浏览）", True, C_MUTED)
        self.screen.blit(axis, (area.x, area.bottom - 18))


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
