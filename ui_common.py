"""Shared UI theme and widgets for layout tools."""
from __future__ import annotations

import pygame

__version__ = "18"

# Input field colors — always high contrast
INPUT_BG = (255, 255, 255)
INPUT_TEXT = (0, 0, 0)
INPUT_PLACEHOLDER = (100, 116, 139)
INPUT_COMPOSITION = (30, 64, 175)

SCREEN_WIDTH, SCREEN_HEIGHT = 1280, 800
SIDEBAR_WIDTH = 340

# ifurniture ERP palette
C_BG = (255, 255, 255)
C_SIDEBAR = (44, 62, 80)
C_SIDEBAR_DARK = (33, 47, 61)
C_SIDEBAR_TEXT = (236, 240, 241)
C_SIDEBAR_MUTED = (149, 165, 166)
C_SIDEBAR_HOVER = (52, 73, 94)
C_SIDEBAR_ACTIVE = (52, 152, 219)
C_CANVAS = (245, 247, 250)
C_GRID = (213, 219, 219)
C_TEXT = (44, 62, 80)
C_MUTED = (127, 140, 141)
C_BORDER = (213, 219, 219)
C_ACCENT = (52, 152, 219)
C_ACCENT_LIGHT = (214, 234, 248)
C_ACCENT_HOVER = (41, 128, 185)
C_SUCCESS = (46, 204, 113)
C_SUCCESS_LIGHT = (212, 239, 223)
C_DANGER = (231, 76, 60)
C_DANGER_LIGHT = (250, 219, 216)
C_DISCONTINUED = (192, 57, 43)
C_DISCONTINUED_BG = (255, 241, 235)
C_DISCONTINUED_BORDER = (211, 84, 0)
DISCONTINUED_LABEL = "停产"
C_PREVIEW = (52, 152, 219)
C_PREVIEW_FILL = (214, 234, 248)

FONT_CANDIDATES = ["Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "SimHei", "Arial"]

FONT_TITLE = None
FONT_BODY = None
FONT_SMALL = None
FONT_LABEL = None
FONT_MARK = None


_tk_root = None


def get_tk_root():
    global _tk_root
    if _tk_root is None:
        import tkinter as tk

        _tk_root = tk.Tk()
        _tk_root.withdraw()
    return _tk_root


_CTRL_UNICODE = {
    "a": "\x01",
    "c": "\x03",
    "s": "\x13",
    "v": "\x16",
    "x": "\x18",
    "z": "\x1a",
}
_CTRL_SCANCODES = {
    "a": 4,
    "c": 6,
    "s": 22,
    "v": 25,
    "x": 45,
    "z": 29,
}


def is_ctrl_key(event, letter: str) -> bool:
    """Detect Ctrl shortcuts reliably on Windows IME / pygame-ce."""
    letter = letter.lower()
    mods = getattr(event, "mod", 0)
    if not (mods & (pygame.KMOD_CTRL | pygame.KMOD_META)):
        return False
    key_const = getattr(pygame, f"K_{letter}", None)
    if key_const is not None and event.key == key_const:
        return True
    if getattr(event, "unicode", "") == _CTRL_UNICODE.get(letter):
        return True
    if getattr(event, "scancode", -1) == _CTRL_SCANCODES.get(letter, -2):
        return True
    return False


def _init_clipboard() -> None:
    try:
        import pygame.scrap as scrap

        if not scrap.get_init():
            scrap.init()
    except Exception:
        pass


def clipboard_get() -> str:
    _init_clipboard()
    try:
        import pygame.scrap as scrap

        if scrap.has_text():
            return scrap.get_text()
    except Exception:
        pass
    try:
        root = get_tk_root()
        root.update_idletasks()
        root.update()
        return root.clipboard_get()
    except Exception:
        return ""


def clipboard_set(text: str) -> None:
    value = "" if text is None else str(text)
    _init_clipboard()
    try:
        import pygame.scrap as scrap

        scrap.put_text(value)
    except Exception:
        pass
    try:
        root = get_tk_root()
        root.clipboard_clear()
        root.clipboard_append(value)
        root.update_idletasks()
        root.update()
    except Exception:
        pass


def _normalize_paste(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n", 1)[0]


def init_fonts():
    """Load fonts after pygame.init(). Safe to call multiple times."""
    global FONT_TITLE, FONT_BODY, FONT_SMALL, FONT_LABEL, FONT_MARK
    if FONT_TITLE is not None:
        return

    if not pygame.get_init():
        pygame.init()
    if not pygame.font.get_init():
        pygame.font.init()

    def load_font(size: int, bold: bool = False) -> pygame.font.Font:
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

    def draw(self, surface, mouse_pos, on_dark=False):
        init_fonts()
        hover = self.enabled and self.rect.collidepoint(mouse_pos)
        if self.toggle and self.active:
            if on_dark:
                bg, fg, border = C_SIDEBAR_ACTIVE, (255, 255, 255), C_SIDEBAR_ACTIVE
            else:
                bg, fg, border = C_ACCENT, (255, 255, 255), C_ACCENT
        elif self.danger:
            bg = C_DANGER if hover else C_DANGER_LIGHT
            fg = (255, 255, 255) if hover else C_DANGER
            border = C_DANGER
        elif self.primary:
            bg = C_ACCENT_HOVER if hover else C_ACCENT
            fg = (255, 255, 255)
            border = C_ACCENT
        elif on_dark:
            bg = C_SIDEBAR_HOVER if hover else C_SIDEBAR_DARK
            fg = C_SIDEBAR_TEXT
            border = C_SIDEBAR_HOVER if hover else C_SIDEBAR_DARK
        else:
            bg = C_ACCENT_LIGHT if hover else (255, 255, 255)
            fg = C_ACCENT if hover else C_TEXT
            border = C_BORDER
        if not self.enabled:
            bg, fg, border = (241, 245, 249), C_MUTED, C_BORDER
        pygame.draw.rect(surface, bg, self.rect, border_radius=4)
        pygame.draw.rect(surface, border, self.rect, 1, border_radius=4)
        text = FONT_SMALL.render(self.label, True, fg)
        surface.blit(text, text.get_rect(center=self.rect.center))


class Dropdown:
    """Traditional dropdown: click trigger to open a list, pick one option."""

    ITEM_H = 28

    def __init__(
        self,
        rect,
        options: list[tuple[str, str]],
        selected: str = "",
        *,
        label: str = "",
        dropdown_id: str = "",
        max_visible: int = 10,
    ):
        self.rect = pygame.Rect(rect)
        self.options = list(options)
        self.selected = selected or (options[0][0] if options else "")
        self.label = label
        self.dropdown_id = dropdown_id
        self.open = False
        self.enabled = True
        self.max_visible = max_visible

    def set_options(self, options: list[tuple[str, str]], *, keep_selection: bool = True) -> None:
        self.options = list(options)
        values = {v for v, _ in self.options}
        if not keep_selection or self.selected not in values:
            self.selected = self.options[0][0] if self.options else ""

    def selected_label(self) -> str:
        for value, text in self.options:
            if value == self.selected:
                return text
        return self.selected

    def trigger_label(self) -> str:
        text = self.selected_label()
        if self.label:
            return f"{self.label}  {text}  ▾"
        return f"{text}  ▾"

    def menu_rect(self) -> pygame.Rect:
        count = min(len(self.options), self.max_visible)
        return pygame.Rect(self.rect.x, self.rect.bottom + 2, self.rect.width, count * self.ITEM_H + 4)

    def contains_trigger(self, pos) -> bool:
        return self.enabled and self.rect.collidepoint(pos)

    def hit_test(self, pos):
        """Return 'trigger', ('pick', value), 'outside', or None."""
        if not self.enabled:
            return None
        if self.open:
            menu = self.menu_rect()
            if menu.collidepoint(pos):
                idx = int((pos[1] - menu.y - 2) // self.ITEM_H)
                if 0 <= idx < len(self.options):
                    return ("pick", self.options[idx][0])
                return "outside"
            if self.rect.collidepoint(pos):
                return "trigger"
            return "outside"
        if self.rect.collidepoint(pos):
            return "trigger"
        return None

    def draw(self, surface, mouse_pos, *, on_dark: bool = False, draw_menu: bool = True):
        init_fonts()
        hover = self.enabled and self.rect.collidepoint(mouse_pos)
        if on_dark:
            bg = C_SIDEBAR_HOVER if hover or self.open else C_SIDEBAR_DARK
            fg = C_SIDEBAR_TEXT
            border = C_SIDEBAR_ACTIVE if self.open else C_SIDEBAR_HOVER
        else:
            bg = C_ACCENT_LIGHT if hover or self.open else (255, 255, 255)
            fg = C_ACCENT if hover or self.open else C_TEXT
            border = C_ACCENT if self.open else C_BORDER
        if not self.enabled:
            bg, fg, border = (241, 245, 249), C_MUTED, C_BORDER
        pygame.draw.rect(surface, bg, self.rect, border_radius=6)
        pygame.draw.rect(surface, border, self.rect, 1, border_radius=6)
        label_surf = FONT_SMALL.render(self.trigger_label(), True, fg)
        clip = label_surf.get_rect(centery=self.rect.centery)
        clip.x = self.rect.x + 8
        clip.width = self.rect.width - 16
        surface.set_clip(clip)
        surface.blit(label_surf, (self.rect.x + 8, self.rect.centery - label_surf.get_height() // 2))
        surface.set_clip(None)

        if draw_menu and self.open and self.options:
            self.draw_menu(surface, mouse_pos)

    def draw_menu(self, surface, mouse_pos):
        init_fonts()
        if not self.open or not self.options:
            return
        menu = self.menu_rect()
        pygame.draw.rect(surface, (255, 255, 255), menu, border_radius=6)
        pygame.draw.rect(surface, C_ACCENT, menu, 2, border_radius=6)
        shadow = menu.copy()
        shadow.y += 1
        pygame.draw.rect(surface, (226, 232, 240), shadow, border_radius=6)
        pygame.draw.rect(surface, (255, 255, 255), menu, border_radius=6)
        pygame.draw.rect(surface, C_ACCENT, menu, 2, border_radius=6)
        for i, (value, text) in enumerate(self.options[: self.max_visible]):
            row = pygame.Rect(menu.x + 2, menu.y + 2 + i * self.ITEM_H, menu.width - 4, self.ITEM_H)
            active = value == self.selected
            if row.collidepoint(mouse_pos):
                pygame.draw.rect(surface, C_ACCENT_LIGHT, row, border_radius=4)
            elif active:
                pygame.draw.rect(surface, (241, 245, 249), row, border_radius=4)
            color = C_ACCENT if active else C_TEXT
            surface.blit(FONT_SMALL.render(text, True, color), (row.x + 8, row.y + 6))


class InputBox:
    def __init__(self, rect, placeholder="", numeric=False):
        self.rect = pygame.Rect(rect)
        self.text = ""
        self.placeholder = placeholder
        self.active = False
        self.numeric = numeric
        self.select_all = False
        self._skip_next_textinput = False
        self.composition = ""
        self.composition_pos = 0

    def contains(self, pos):
        return self.rect.collidepoint(pos)

    def get_text(self):
        return self.text.strip()

    def get_float(self, default=0.0):
        try:
            return float(self.text)
        except ValueError:
            return default

    def set_text(self, value):
        self.text = "" if value is None else str(value)
        self.select_all = False
        self.composition = ""
        self.composition_pos = 0

    def select_all_text(self):
        if self.text:
            self.select_all = True
        self.composition = ""
        self.composition_pos = 0

    def refresh_text_input(self):
        """Keep SDL text input attached — needed after programmatic focus on Windows."""
        if not self.active:
            return
        try:
            pygame.key.start_text_input()
            pygame.key.set_text_input_rect(self.rect)
        except Exception:
            pass

    def _filter_text(self, text: str) -> str:
        if not text:
            return ""
        if self.numeric:
            return "".join(ch for ch in text if ch in "0123456789.")
        return text

    def _insert_text(self, text: str) -> None:
        text = self._filter_text(text)
        if not text:
            return
        if self.select_all:
            self.text = ""
            self.select_all = False
        self.text += text

    def _delete_backward(self) -> None:
        self.composition = ""
        if self.select_all:
            self.text = ""
            self.select_all = False
        elif self.text:
            self.text = self.text[:-1]

    def _pause_text_input(self):
        try:
            pygame.key.stop_text_input()
        except Exception:
            pass

    def _resume_text_input(self):
        if not self.active:
            return
        try:
            pygame.key.start_text_input()
            pygame.key.set_text_input_rect(self.rect)
        except Exception:
            pass

    def _copy_text(self) -> None:
        if self.text:
            clipboard_set(self.text)

    def _cut_text(self) -> None:
        if not self.text:
            return
        clipboard_set(self.text)
        self.text = ""
        self.select_all = False
        self.composition = ""

    def _paste_text(self) -> None:
        pasted = _normalize_paste(clipboard_get())
        if pasted:
            self._skip_next_textinput = True
            self._insert_text(pasted)

    def activate(self):
        self.active = True
        self.composition = ""
        self.composition_pos = 0
        try:
            pygame.key.start_text_input()
            pygame.key.set_text_input_rect(self.rect)
            pygame.key.set_repeat(400, 35)
        except Exception:
            pass

    def deactivate(self):
        self.active = False
        self.select_all = False
        self.composition = ""
        self.composition_pos = 0
        try:
            pygame.key.stop_text_input()
            pygame.key.set_repeat(0)
        except Exception:
            pass

    def handle_event(self, event):
        if not self.active:
            return False
        if event.type == pygame.TEXTEDITING:
            self.composition = event.text or ""
            self.composition_pos = int(getattr(event, "length", 0) or 0)
            if self.composition:
                self.select_all = False
            return True
        if event.type == pygame.TEXTINPUT:
            text = event.text or ""
            self.composition = ""
            self.composition_pos = 0
            if self._skip_next_textinput:
                self._skip_next_textinput = False
                return True
            self._insert_text(text)
            return True
        if event.type == pygame.KEYDOWN:
            if is_ctrl_key(event, "a"):
                self.select_all_text()
                return True
            if is_ctrl_key(event, "c"):
                self._copy_text()
                return True
            if is_ctrl_key(event, "x"):
                self._cut_text()
                return True
            if is_ctrl_key(event, "v"):
                self._paste_text()
                return True

            if event.key == pygame.K_BACKSPACE:
                self._delete_backward()
                return True
            if event.key == pygame.K_DELETE:
                self._delete_backward()
                return True
            if event.key == pygame.K_ESCAPE:
                self.deactivate()
                return True
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                return True
        return False

    def _render_glyph(self, text: str, color):
        """Render with explicit white background so text is never invisible."""
        init_fonts()
        try:
            return FONT_SMALL.render(text, True, color, INPUT_BG)
        except TypeError:
            return FONT_SMALL.render(text, True, color)

    def draw(self, surface, label=None, on_dark=False):
        init_fonts()
        label_color = C_SIDEBAR_MUTED if on_dark else C_MUTED
        if label:
            surface.blit(FONT_SMALL.render(label, True, label_color), (self.rect.x, self.rect.y - 18))

        border = C_ACCENT if self.active else ((180, 190, 200) if on_dark else C_BORDER)
        border_w = 2 if self.active else 1
        pygame.draw.rect(surface, INPUT_BG, self.rect, border_radius=4)
        pygame.draw.rect(surface, border, self.rect, border_w, border_radius=4)

        text_x = self.rect.x + 10
        text_y = self.rect.y + 9
        cursor_x = text_x

        if self.text:
            text_surf = self._render_glyph(self.text, INPUT_TEXT)
            if self.active and self.select_all:
                highlight = pygame.Rect(
                    text_x - 2, self.rect.y + 6, text_surf.get_width() + 4, self.rect.height - 12
                )
                pygame.draw.rect(surface, C_ACCENT_LIGHT, highlight, border_radius=4)
            surface.blit(text_surf, (text_x, text_y))
            cursor_x = text_x + text_surf.get_width()

        if self.composition and self.active:
            before = self.composition[: self.composition_pos]
            after = self.composition[self.composition_pos :]
            if before:
                surface.blit(self._render_glyph(before, INPUT_COMPOSITION), (cursor_x, text_y))
                cursor_x += self._render_glyph(before, INPUT_COMPOSITION).get_width()
            caret = "|" if pygame.time.get_ticks() % 1000 < 500 else " "
            caret_surf = self._render_glyph(caret, INPUT_COMPOSITION)
            surface.blit(caret_surf, (cursor_x, text_y))
            cursor_x += caret_surf.get_width()
            if after:
                surface.blit(self._render_glyph(after, INPUT_COMPOSITION), (cursor_x, text_y))
                cursor_x += self._render_glyph(after, INPUT_COMPOSITION).get_width()
        elif self.active and not self.select_all and not self.text and not self.composition:
            if pygame.time.get_ticks() % 1000 < 500:
                pygame.draw.line(
                    surface,
                    C_ACCENT,
                    (text_x + 1, self.rect.y + 8),
                    (text_x + 1, self.rect.bottom - 8),
                    2,
                )
        elif self.active and not self.select_all and self.text and not self.composition:
            if pygame.time.get_ticks() % 1000 < 500:
                pygame.draw.line(
                    surface,
                    C_ACCENT,
                    (cursor_x + 1, self.rect.y + 8),
                    (cursor_x + 1, self.rect.bottom - 8),
                    2,
                )

        if not self.text and not self.composition:
            surface.blit(self._render_glyph(self.placeholder, INPUT_PLACEHOLDER), (text_x, text_y))


class Toast:
    def __init__(self):
        self.message = ""
        self.until = 0

    def show(self, msg, duration_ms=2500):
        self.message = msg
        self.until = pygame.time.get_ticks() + duration_ms
        print(msg)

    def draw(self, surface, x_center, y=16):
        init_fonts()
        if pygame.time.get_ticks() > self.until or not self.message:
            return
        text = FONT_BODY.render(self.message, True, (255, 255, 255))
        pad = 14
        rect = text.get_rect()
        rect.width += pad * 2
        rect.height += pad
        rect.centerx = x_center
        rect.y = y
        pygame.draw.rect(surface, (30, 41, 59), rect, border_radius=10)
        surface.blit(text, (rect.x + pad, rect.y + pad // 2))


def draw_sidebar_bg(surface):
    pygame.draw.rect(surface, C_SIDEBAR, (0, 0, SIDEBAR_WIDTH, SCREEN_HEIGHT))
    pygame.draw.line(surface, C_SIDEBAR_HOVER, (SIDEBAR_WIDTH - 1, 0), (SIDEBAR_WIDTH - 1, SCREEN_HEIGHT))


def draw_sidebar_header(surface, title, subtitle=None):
    """ERP-style sidebar title block."""
    init_fonts()
    pygame.draw.rect(surface, C_SIDEBAR_DARK, (0, 0, SIDEBAR_WIDTH, 56))
    surface.blit(FONT_TITLE.render(title, True, C_SIDEBAR_TEXT), (16, 12))
    if subtitle:
        surface.blit(FONT_SMALL.render(subtitle, True, C_SIDEBAR_MUTED), (16, 36))


def draw_discontinued_badge(
    surface,
    anchor: pygame.Rect,
    *,
    align: str = "topright",
    label: str = DISCONTINUED_LABEL,
) -> pygame.Rect:
    """醒目「停产」角标，用于卡片/画布/侧栏。"""
    init_fonts()
    text_surf = FONT_MARK.render(label, True, (255, 255, 255))
    pad_x, pad_y = 5, 2
    badge = pygame.Rect(0, 0, text_surf.get_width() + pad_x * 2, text_surf.get_height() + pad_y * 2)
    if align == "topright":
        badge.topright = anchor.topright
    elif align == "topleft":
        badge.topleft = anchor.topleft
    elif align == "center":
        badge.center = anchor.center
    else:
        badge.topright = anchor.topright
    badge.inflate_ip(0, 0)
    pygame.draw.rect(surface, C_DISCONTINUED, badge, border_radius=4)
    surface.blit(text_surf, text_surf.get_rect(center=badge.center))
    return badge


def draw_discontinued_card_stripe(surface, rect: pygame.Rect, *, radius: int = 8) -> None:
    """卡片左侧停产色条 + 浅底，与正常产品一眼可辨。"""
    tint = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    tint.fill((*C_DISCONTINUED_BG, 120))
    surface.blit(tint, rect.topleft)
    stripe = pygame.Rect(rect.x, rect.y, 5, rect.height)
    pygame.draw.rect(surface, C_DISCONTINUED, stripe, border_radius=max(2, radius // 2))
    pygame.draw.rect(surface, C_DISCONTINUED_BORDER, rect, 2, border_radius=radius)


def draw_discontinued_canvas_mark(
    surface,
    cx: float,
    top_y: float,
    *,
    span_px: float = 80,
) -> None:
    """布局画布上家具顶部的停产标记。"""
    init_fonts()
    label = DISCONTINUED_LABEL
    scale = max(0.65, min(1.15, span_px / 100.0))
    font_size = max(10, int(12 * scale))
    try:
        font = pygame.font.SysFont(FONT_CANDIDATES[0], font_size, bold=True)
    except Exception:
        font = FONT_MARK
    text = font.render(label, True, (255, 255, 255))
    pad_x, pad_y = max(4, int(6 * scale)), max(2, int(3 * scale))
    badge = pygame.Rect(0, 0, text.get_width() + pad_x * 2, text.get_height() + pad_y * 2)
    badge.midbottom = (int(cx), int(top_y) - 2)
    pygame.draw.rect(surface, C_DISCONTINUED, badge, border_radius=5)
    pygame.draw.rect(surface, C_DISCONTINUED_BORDER, badge, 2, border_radius=5)
    surface.blit(text, text.get_rect(center=badge.center))
