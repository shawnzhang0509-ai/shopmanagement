"""Shared UI theme and widgets for layout tools."""
from __future__ import annotations

import pygame

__version__ = "7"

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
    "v": "\x16",
    "x": "\x18",
}
_CTRL_SCANCODES = {
    "a": 4,
    "c": 6,
    "v": 25,
    "x": 45,
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


class InputBox:
    def __init__(self, rect, placeholder="", numeric=False):
        self.rect = pygame.Rect(rect)
        self.text = ""
        self.placeholder = placeholder
        self.active = False
        self.numeric = numeric
        self.select_all = False
        self._skip_next_textinput = False

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

    def select_all_text(self):
        if self.text:
            self.select_all = True

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
        if not self.text:
            return
        self._pause_text_input()
        clipboard_set(self.text)
        self._resume_text_input()

    def _cut_text(self) -> None:
        if not self.text:
            return
        self._pause_text_input()
        clipboard_set(self.text)
        self.text = ""
        self.select_all = False
        self._resume_text_input()

    def _paste_text(self) -> None:
        self._pause_text_input()
        pasted = _normalize_paste(clipboard_get())
        if pasted:
            self._skip_next_textinput = True
            self._insert_text(pasted)
        self._resume_text_input()

    def activate(self):
        self.active = True
        try:
            pygame.key.start_text_input()
            pygame.key.set_text_input_rect(self.rect)
            pygame.key.set_repeat(400, 35)
        except Exception:
            pass

    def deactivate(self):
        self.active = False
        self.select_all = False
        try:
            pygame.key.stop_text_input()
            pygame.key.set_repeat(0)
        except Exception:
            pass

    def handle_event(self, event):
        if not self.active:
            return False
        if event.type == pygame.TEXTINPUT:
            text = event.text or ""
            if self._skip_next_textinput:
                self._skip_next_textinput = False
                return True
            if len(text) > 1:
                self._insert_text(_normalize_paste(text))
                return True
            if pygame.key.get_mods() & (pygame.KMOD_CTRL | pygame.KMOD_META):
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

    def draw(self, surface, label=None, on_dark=False):
        init_fonts()
        label_color = C_SIDEBAR_MUTED if on_dark else C_MUTED
        if label:
            surface.blit(FONT_SMALL.render(label, True, label_color), (self.rect.x, self.rect.y - 18))
        bg = (255, 255, 255) if self.active else ((60, 80, 100) if on_dark else (248, 250, 252))
        pygame.draw.rect(surface, bg, self.rect, border_radius=4)
        border = C_ACCENT if self.active else (C_SIDEBAR_HOVER if on_dark else C_BORDER)
        pygame.draw.rect(surface, border, self.rect, 2 if self.active else 1, border_radius=4)
        text_x = self.rect.x + 10
        text_y = self.rect.y + 9
        if self.text:
            display = self.text
            color = C_TEXT if not on_dark else C_SIDEBAR_TEXT
            text_surf = FONT_SMALL.render(display, True, color)
            if self.active and self.select_all:
                highlight = pygame.Rect(text_x - 2, self.rect.y + 6, text_surf.get_width() + 4, self.rect.height - 12)
                pygame.draw.rect(surface, C_ACCENT_LIGHT, highlight, border_radius=4)
            surface.blit(text_surf, (text_x, text_y))
        else:
            display = self.placeholder
            color = C_SIDEBAR_MUTED if on_dark else C_MUTED
            text_surf = FONT_SMALL.render(display, True, color)
            surface.blit(text_surf, (text_x, text_y))
        if self.active and not self.select_all:
            caret_color = C_ACCENT if not on_dark else (255, 255, 255)
            caret_x = text_x + (FONT_SMALL.render(self.text, True, caret_color).get_width() if self.text else 0) + 1
            if pygame.time.get_ticks() % 1000 < 500:
                pygame.draw.line(
                    surface,
                    caret_color,
                    (caret_x, self.rect.y + 8),
                    (caret_x, self.rect.bottom - 8),
                    2,
                )


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
