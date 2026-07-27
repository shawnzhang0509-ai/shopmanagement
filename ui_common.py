"""Shared UI theme and widgets for layout tools."""
from __future__ import annotations

import pygame

__version__ = "2"

SCREEN_WIDTH, SCREEN_HEIGHT = 1280, 800
SIDEBAR_WIDTH = 300

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
C_PREVIEW = (96, 165, 250)
C_PREVIEW_FILL = (191, 219, 254)

FONT_CANDIDATES = ["Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "SimHei", "Arial"]

FONT_TITLE = None
FONT_BODY = None
FONT_SMALL = None
FONT_LABEL = None
FONT_MARK = None


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

    def draw(self, surface, mouse_pos):
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
    def __init__(self, rect, placeholder="", numeric=False):
        self.rect = pygame.Rect(rect)
        self.text = ""
        self.placeholder = placeholder
        self.active = False
        self.numeric = numeric

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

    def draw(self, surface, label=None):
        if label:
            surface.blit(FONT_SMALL.render(label, True, C_MUTED), (self.rect.x, self.rect.y - 18))
        bg = (255, 255, 255) if self.active else (248, 250, 252)
        pygame.draw.rect(surface, bg, self.rect, border_radius=8)
        border = C_ACCENT if self.active else C_BORDER
        pygame.draw.rect(surface, border, self.rect, 2 if self.active else 1, border_radius=8)
        display = self.text if self.text else self.placeholder
        color = C_TEXT if self.text else C_MUTED
        surface.blit(FONT_SMALL.render(display, True, color), (self.rect.x + 10, self.rect.y + 9))


class Toast:
    def __init__(self):
        self.message = ""
        self.until = 0

    def show(self, msg, duration_ms=2500):
        self.message = msg
        self.until = pygame.time.get_ticks() + duration_ms
        print(msg)

    def draw(self, surface, x_center, y=16):
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
    pygame.draw.line(surface, C_BORDER, (SIDEBAR_WIDTH - 1, 0), (SIDEBAR_WIDTH - 1, SCREEN_HEIGHT))
