from __future__ import annotations

from pathlib import Path

_FONT_PATHS = [
    Path(__file__).resolve().parents[3] / "assets" / "fonts" / f"cairo-{w}.ttf"
    for w in ("400", "600", "700", "800")
]


def register_fonts() -> bool:
    """Register bundled fonts (Cairo, OFL) with QFontDatabase; True if any loaded."""
    from PyQt6.QtGui import QFontDatabase

    loaded = False
    for path in _FONT_PATHS:
        try:
            if path.is_file() and QFontDatabase.addApplicationFont(str(path)) >= 0:
                loaded = True
        except Exception:
            continue
    return loaded


def _sys_platform() -> str:
    import sys

    return sys.platform


def _rgba(hex_color: str, alpha: int) -> str:
    """'#RRGGBB' -> 'rgba(r, g, b, a)' string, a in 0..255 (rounded)."""
    rgb = int(hex_color.lstrip("#"), 16)
    return f"rgba({(rgb >> 16) & 255}, {(rgb >> 8) & 255}, {rgb & 255}, {alpha})"


def blend_hex(fg: str, bg: str, alpha: float) -> str:
    """Opaque hex of ``fg`` mixed over ``bg`` at ``alpha`` (0..1).

    Alpha-tinted chips let the row's own background (alternating, hover, selected
    accent) show through, which made their text unreadable on coloured rows; painting
    the tint onto the surface colour keeps the chip identical wherever it sits.
    """
    f = int(fg.lstrip("#"), 16)
    b = int(bg.lstrip("#"), 16)
    channels = []
    for shift in (16, 8, 0):
        fc, bc = (f >> shift) & 255, (b >> shift) & 255
        channels.append(round(fc * alpha + bc * (1 - alpha)))
    return "#%02X%02X%02X" % tuple(channels)



def _is_dark_hex(hex_color: str) -> bool:
    """Human-perceived lightness of '#RRGGBB' below 50% (same weights as WCAG)."""
    rgb = int(hex_color.lstrip("#"), 16)
    r, g, b = (rgb >> 16) & 255, (rgb >> 8) & 255, rgb & 255
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) < 128


def _derive(p: dict) -> dict:
    accent = p["accent"]
    return {
        **p,
        "kind": p.get("kind", "dark" if _is_dark_hex(p["bg"]) else "light"),
        # filled controls (primary buttons, active nav, menus) use a tone that keeps
        # on_accent readable at BOTH ends of the gradient - the raw accent is tuned for
        # text on the page background and would fail there in several palettes.
        "accent_solid": p.get("accent_solid") or accent,
        "on_accent": p.get("on_accent", "#FFFFFF"),
        "on_danger": p.get("on_danger", "#FFFFFF"),
        "accent_hi": p.get("accent_hi") or accent,
        "accent_lo": p.get("accent_lo") or p["accent_dark"],
        "accent_rgba_12": _rgba(accent, 12),
        "accent_rgba_20": _rgba(accent, 20),
        "text_rgba_6": _rgba(p["text"], 6),
        "danger_rgba": _rgba(p["danger"], 16),
        "success_rgba": _rgba(p["success"], 16),
        "warn_rgba": _rgba(p["warn"], 16),
        "white_rgba_14": _rgba("#FFFFFF", 14),
        "white_rgba_26": _rgba("#FFFFFF", 26),
        "hero_text_sub": _rgba("#FFFFFF", 232),
        # translucent DARK overlay: white text on it stays readable over any hero gradient
        "hero_chip_bg": _rgba("#000000", 58),
    }


_PALETTES = {
    "light": {
        "kind": "light",
        "bg": "#F4F7FC", "surface": "#FFFFFF", "surface_2": "#EEF2FA", "surface_3": "#E1E8F4",
        "border": "#D3DCEA", "border_soft": "#E6ECF6",
        "text": "#10172A", "muted": "#4E5E79",
        "accent": "#2A5CE0", "accent_dark": "#2249B8", "accent_hi": "#3E6BE6", "accent_lo": "#2244A8",
        "accent_solid": "#2A5CE0", "on_accent": "#FFFFFF", "on_danger": "#FFFFFF",
        "success": "#0B7A52", "danger": "#C22F39", "warn": "#9A5A00",
        "hover": "#E8EEF8", "pressed": "#DCE5F3", "danger_hover": "#A32029",
        "hero1": "#2F63F0", "hero2": "#5B3DF0",
        "table_hover": "#EFF4FC",
        # KPI / chart tokens (>= 3:1 on the white surface)
        "violet": "#6D3FE0", "teal": "#0B7F74", "orange": "#B85A14", "gold": "#9A5A00",
        "series": ("#2A5CE0", "#0B8F84", "#C57600", "#7A4BF8", "#C22F39", "#64748B"),
        "grid": "#E1E8F4",
    },
    "dark": {
        "kind": "dark",
        "bg": "#0B0F1A", "surface": "#141C2E", "surface_2": "#1C2740", "surface_3": "#2A3852",
        "border": "#33415E", "border_soft": "#232E49",
        "text": "#F2F6FD", "muted": "#A8B4CB",
        "accent": "#4F7CFF", "accent_dark": "#3157E8", "accent_hi": "#3E67EE", "accent_lo": "#1F3FAE",
        "accent_solid": "#2F53D0", "on_accent": "#FFFFFF", "on_danger": "#2A0708",
        "success": "#36D19B", "danger": "#F26360", "warn": "#F6BC58",
        "hover": "#243152", "pressed": "#1A2238", "danger_hover": "#D44845",
        "hero1": "#3358E6", "hero2": "#6E3FE8",
        "table_hover": "#1F2B47",
        # KPI / chart tokens (>= 3:1 on the dark surface)
        "violet": "#A78BFA", "teal": "#2DD4BF", "orange": "#F2944C", "gold": "#F6BC58",
        "series": ("#6E95FF", "#2DD4BF", "#F6BC58", "#A78BFA", "#F26360", "#94A3B8"),
        "grid": "#2A3852",
    },
    # ---- deep navy with a cyan accent (dark)
    "midnight": {
        "kind": "dark",
        "bg": "#060B18", "surface": "#0D1526", "surface_2": "#15203A", "surface_3": "#22314F",
        "border": "#2C3D5C", "border_soft": "#1B2740",
        "text": "#EAF2FF", "muted": "#94A6C4",
        "accent": "#38BDF8", "accent_dark": "#0E86C4", "accent_hi": "#A5E8FF", "accent_lo": "#4CC9F0",
        "accent_solid": "#38BDF8", "on_accent": "#04202E", "on_danger": "#2A0708",
        "success": "#34D399", "danger": "#F87171", "warn": "#FBBF24",
        "hover": "#182A4A", "pressed": "#101B33", "danger_hover": "#DC2626",
        "hero1": "#0E7490", "hero2": "#4338CA",
        "table_hover": "#13203A",
        "violet": "#A78BFA", "teal": "#2DD4BF", "orange": "#FB923C", "gold": "#FBBF24",
        "series": ("#7DD3FC", "#2DD4BF", "#FBBF24", "#A78BFA", "#F87171", "#94A3B8"),
        "grid": "#22314F",
    },
    # ---- neutral charcoal with an amber accent (dark)
    "graphite": {
        "kind": "dark",
        "bg": "#101114", "surface": "#1A1C20", "surface_2": "#23262C", "surface_3": "#31353D",
        "border": "#3A3F48", "border_soft": "#262A31",
        "text": "#F4F5F7", "muted": "#A9AFBA",
        "accent": "#F0A93B", "accent_dark": "#C47F16", "accent_hi": "#FFC266", "accent_lo": "#B87812",
        "accent_solid": "#D99423", "on_accent": "#1A1205", "on_danger": "#2A0708",
        "success": "#4ADE80", "danger": "#F87171", "warn": "#FBBF24",
        "hover": "#262A31", "pressed": "#1E2126", "danger_hover": "#DC2626",
        "hero1": "#B45309", "hero2": "#7C2D12",
        "table_hover": "#242830",
        "violet": "#C4B5FD", "teal": "#5EEAD4", "orange": "#FB923C", "gold": "#FBBF24",
        "series": ("#FFC266", "#5EEAD4", "#C4B5FD", "#F87171", "#94A3B8", "#E5E7EB"),
        "grid": "#31353D",
    },
    # ---- warm paper with a terracotta accent (light)
    "sepia": {
        "kind": "light",
        "bg": "#F7F1E6", "surface": "#FFFDF8", "surface_2": "#F1E9DA", "surface_3": "#E5D8C2",
        "border": "#DCCDB3", "border_soft": "#EBE0CE",
        "text": "#2E2618", "muted": "#6E5F49",
        "accent": "#A8542C", "accent_dark": "#83401F", "accent_hi": "#B45E33", "accent_lo": "#7A3A1B",
        "accent_solid": "#A8542C", "on_accent": "#FFFFFF", "on_danger": "#FFFFFF",
        "success": "#2F6B40", "danger": "#B23A3A", "warn": "#8A5B00",
        "hover": "#F0E5D2", "pressed": "#E7D9C2", "danger_hover": "#932F2F",
        "hero1": "#A8542C", "hero2": "#6D4C2A",
        "table_hover": "#F5EDDE",
        "violet": "#7C5AA6", "teal": "#2F7D74", "orange": "#A8542C", "gold": "#8A5B00",
        "series": ("#A8542C", "#2F7D74", "#B08A37", "#7C5AA6", "#B23A3A", "#8A7C66"),
        "grid": "#E5D8C2",
    },
    # ---- cool blue-grey with a teal accent (light)
    "frost": {
        "kind": "light",
        "bg": "#F2F6F9", "surface": "#FFFFFF", "surface_2": "#E9F0F5", "surface_3": "#D9E5ED",
        "border": "#C9D8E3", "border_soft": "#E1EAF1",
        "text": "#16232E", "muted": "#52697A",
        "accent": "#0E7490", "accent_dark": "#0A5A70", "accent_hi": "#147B96", "accent_lo": "#085063",
        "accent_solid": "#0E7490", "on_accent": "#FFFFFF", "on_danger": "#FFFFFF",
        "success": "#0F766E", "danger": "#BE3A4A", "warn": "#9A5B00",
        "hover": "#E4EEF4", "pressed": "#D6E4EC", "danger_hover": "#A32E3D",
        "hero1": "#0E7490", "hero2": "#4338CA",
        "table_hover": "#EDF4F8",
        "violet": "#6D4AC4", "teal": "#0F766E", "orange": "#B45309", "gold": "#8A5B00",
        "series": ("#0E7490", "#6D4AC4", "#B45309", "#0F766E", "#BE3A4A", "#5B7183"),
        "grid": "#D9E5ED",
    },
}

_CURRENT = "light"


class Metrics:
    """Shared geometry so pages, tables and dialogs never drift apart.

    Values are CSS pixels and are mirrored by the style sheet below: when one changes,
    change the other.
    """

    RADIUS = 10
    RADIUS_SM = 8
    CONTROL_H = 36          # line edits, combos, date edits (style-sheet content box)
    CONTROL_CHROME = 14     # padding 6+6 + 1px border on each side
    BUTTON_H = 36
    BUTTON_SM_H = 28
    ROW_H = 42              # table rows
    HEADER_H = 40           # table header
    NAV_ROW_H = 36          # sidebar destination row (style sheet: 28px content + 8px padding)
    NAV_CAPTION_H = 28      # sidebar section caption ("Operations", "Reports", ...)
    NAV_ICON = 18           # compact sidebar icon
    PAGE_MARGIN = 24
    PAGE_SPACING = 14
    CARD_PADDING = 18


THEME_AUTO = "auto"
THEME_LIGHT = "light"
THEME_DARK = "dark"
# every selectable mode: "auto" (follow the OS) plus each concrete palette
THEME_MODES = (THEME_AUTO,) + tuple(_PALETTES)
# display order: automatic, then the light palettes, then the dark ones
THEME_UI_ORDER = (
    THEME_AUTO, "light", "sepia", "frost", "dark", "midnight", "graphite",
)
THEME_LABEL_KEYS = {
    "light": "thm_light",
    "sepia": "thm_sepia",
    "frost": "thm_frost",
    "dark": "thm_dark",
    "midnight": "thm_midnight",
    "graphite": "thm_graphite",
}


def current_name() -> str:
    """Name of the currently active theme palette."""
    return _CURRENT


_COLORS_CACHE: dict[str, dict] = {}


def colors() -> dict:
    """Current active palette (drawing code reads this at paint time)."""
    cached = _COLORS_CACHE.get(_CURRENT)
    if cached is None:
        cached = _COLORS_CACHE[_CURRENT] = _derive(_PALETTES[_CURRENT])
    return cached



def palette_names() -> tuple[str, ...]:
    return tuple(_PALETTES)


def palette_kind(name: str) -> str:
    """'light' or 'dark' for a palette (falls back to the active one)."""
    palette = _PALETTES.get(name) or _PALETTES[_CURRENT]
    return palette.get("kind") or ("dark" if _is_dark_hex(palette["bg"]) else "light")


def is_dark(name: str | None = None) -> bool:
    return palette_kind(name or _CURRENT) == "dark"


def set_current(name: str) -> str:
    global _CURRENT
    if name not in _PALETTES:
        name = "light"
    _CURRENT = name
    return name


def _windows_apps_use_light() -> bool | None:
    """Windows' "app mode" light/dark switch, or None when it cannot be read."""
    if _sys_platform() != "win32":
        return None
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return bool(value)
    except Exception:
        return None


def system_prefers_dark() -> bool:
    """Detect the OS light/dark preference.

    Windows is asked first: ``AppsUseLightTheme`` is exactly the switch that changes
    the Settings app, Explorer and everything else. Qt's color scheme is the fallback
    for other platforms. The *application* palette is deliberately not consulted — the
    app replaces it with its own theme, so it only ever echoed the palette that was
    already applied (auto mode stayed light no matter what Windows was set to).
    """
    apps_light = _windows_apps_use_light()
    if apps_light is not None:
        return not apps_light
    try:
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            scheme = app.styleHints().colorScheme()
            if scheme == Qt.ColorScheme.Dark:
                return True
            if scheme == Qt.ColorScheme.Light:
                return False
    except Exception:
        pass
    return False



def resolve_theme_name(mode: str | None) -> str:
    """Map a stored theme mode to an actual palette name (auto follows the OS)."""
    mode = mode or THEME_AUTO
    if mode in _PALETTES:
        return mode
    return THEME_DARK if system_prefers_dark() else THEME_LIGHT


def palette_for(name: str) -> "QPalette":
    """Build a QPalette matching the palette so unstyled widgets render correctly
    in both themes (fixes white containers inside dark mode)."""
    from PyQt6.QtGui import QColor, QPalette

    p = _derive(_PALETTES[name if name in _PALETTES else _CURRENT])
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(p["bg"]))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(p["text"]))
    pal.setColor(QPalette.ColorRole.Base, QColor(p["surface"]))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(p["surface_2"]))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(p["surface_3"]))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(p["text"]))
    pal.setColor(QPalette.ColorRole.Text, QColor(p["text"]))
    pal.setColor(QPalette.ColorRole.Button, QColor(p["surface"]))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(p["text"]))
    pal.setColor(QPalette.ColorRole.BrightText, QColor(p["on_accent"]))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(p["accent"]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(p["on_accent"]))
    pal.setColor(QPalette.ColorRole.Link, QColor(p["accent_hi"]))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(p["muted"]))
    # Fusion derives frames, empty header space and separators from these roles; leaving the
    # defaults produced solid black/dark-grey strips in the light theme (see invoices table).
    pal.setColor(QPalette.ColorRole.Light, QColor(p["surface"]))
    pal.setColor(QPalette.ColorRole.Midlight, QColor(p["surface_2"]))
    pal.setColor(QPalette.ColorRole.Mid, QColor(p["border"]))
    pal.setColor(QPalette.ColorRole.Dark, QColor(p["border"]))
    pal.setColor(QPalette.ColorRole.Shadow, QColor(p["border_soft"]))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, QColor(p["muted"]))
    return pal


def apply(qapp, name: str | None = None, *, rtl: bool | None = None) -> str:
    """Apply the theme (QSS + QPalette) to a running QApplication. Returns the name."""
    name = resolve_theme_name(name) if name in (None, THEME_AUTO) else name
    set_current(name)
    if rtl is None:
        from .widgets import rtl_active

        rtl = rtl_active()
    try:
        qapp.setStyleSheet(build_qss(name, rtl=rtl))
        qapp.setPalette(palette_for(name))
    except Exception:
        pass
    return name


# module-level names kept for backwards-compatible imports (default dark)
_dark = _derive(_PALETTES["dark"])
ACCENT = _dark["accent"]
ACCENT_DARK = _dark["accent_dark"]
BG = _dark["bg"]
SURFACE = _dark["surface"]
SURFACE_2 = _dark["surface_2"]
TEXT = _dark["text"]
TEXT_MUTED = _dark["muted"]
SUCCESS = _dark["success"]
DANGER = _dark["danger"]
WARN = _dark["warn"]
BORDER = _dark["border"]

_QSS = """
QWidget {
    color: %(text)s;
    font-family: "Cairo", "Segoe UI", "Tahoma";
    font-size: 13px;
}
QLabel { background-color: transparent; }
QToolTip {
    background-color: %(surface_3)s;
    color: %(text)s;
    border: 1px solid %(border)s;
    border-radius: 6px;
    padding: 6px 8px;
    font-size: 12px;
}
QMainWindow, QStackedWidget { background-color: %(bg)s; }

/* page chrome: every QWidget placed directly inside the stack must carry the
   page background (kept separate from the global QLabel rule so hero/labels
   stay transparent, not solid boxes). */
QStackedWidget > QWidget { background-color: %(bg)s; }
QScrollArea { background-color: %(bg)s; border: none; }
QScrollArea QWidget[objectName="qt_scrollarea_viewport"] { background-color: %(bg)s; }
/* plain QWidgets inside a scroll content area fall back to the palette window
   (white in dark mode) unless painted explicitly: give them the page background,
   then restore tables to their surface so they do not darken underneath. */
QScrollArea > QWidget > QWidget { background-color: %(bg)s; }
QScrollArea QTableWidget { background-color: %(surface)s; }
QScrollArea QTableWidget QWidget { background-color: %(surface)s; }
QListWidget, QListView, QTreeView {
    background-color: %(surface)s;
    border: 1px solid %(border)s;
    border-radius: 8px;
    outline: none;
}
QListWidget::item, QListView::item, QTreeView::item { padding: 5px 9px; border-radius: 6px; }
QListWidget::item:selected, QListView::item:selected, QTreeView::item:selected {
    background-color: %(accent_rgba_20)s; color: %(text)s;
}
QListWidget::item:hover, QListView::item:hover, QTreeView::item:hover { background-color: %(table_hover)s; }
QGroupBox {
    background-color: transparent;
    border: 1px solid %(border)s;
    border-radius: 9px;
    margin-top: 12px;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; color: %(muted)s; font-weight: 700; }
QPlainTextEdit, QTextEdit { background-color: %(surface)s; }
QSplitter::handle { background-color: %(border)s; }

QStatusBar {
    background-color: %(surface)s;
    color: %(muted)s;
    border-top: 1px solid %(border)s;
    font-size: 12px;
    padding: 2px 10px;
}

/* sidebar */
QFrame#Sidebar { background-color: %(surface)s; border-right: 1px solid %(border)s; }
QFrame#Sidebar[rtl="true"] { border-right: none; border-left: 1px solid %(border)s; }
QFrame#BrandLogo { background-color: transparent; border: none; }
QLabel#BrandName { font-size: 16px; font-weight: 800; color: %(text)s; }
QLabel#BrandSub { font-size: 11px; color: %(muted)s; }
/* section labels are captions, not destinations: no hover, no border, visibly
   smaller than the clickable rows below them */
QLabel#SectionHeader {
    font-size: 10px;
    font-weight: 700;
    color: %(muted)s;
    padding: 5px 14px 2px 14px;
    background-color: transparent;
}
QFrame#NavDivider { background-color: %(border_soft)s; }
/* Nav rows opt out of the generic QPushButton height: every language must draw
   the same 36px row even when the font falls back (e.g. Devanagari). */
QPushButton#NavBtn {
    background-color: transparent;
    border: none;
    border-radius: 8px;
    padding: 4px 14px;
    min-height: 28px;
    max-height: 28px;
    font-size: 13px;
    font-weight: 600;
    color: %(muted)s;
    text-align: left;
}
QPushButton#NavBtn[rtl="true"] { text-align: right; }
QPushButton#NavBtn[compact="true"] { text-align: center; padding: 4px 4px; }
QPushButton#NavBtn:hover { background-color: %(surface_2)s; color: %(text)s; }
QPushButton#NavBtn:checked {
    background-color: %(accent_solid)s;
    color: %(on_accent)s;
}
QPushButton#NavBtn:checked:hover { color: %(on_accent)s; }
QLabel#Version { font-size: 11px; color: %(muted)s; }

/* page chrome */
QLabel#PageTitle { font-size: 24px; font-weight: 800; }
QLabel#PageSub { color: %(muted)s; font-size: 13px; }
QLabel#CardTitle { font-size: 16px; font-weight: 700; }
QLabel#StepTitle { font-size: 12px; font-weight: 700; color: %(accent)s; }
QLabel#FieldLabel { color: %(muted)s; font-size: 12px; font-weight: 600; }
QLabel#Muted { color: %(muted)s; }
QLabel#Empty { color: %(muted)s; font-size: 13px; }
QLabel#Error { color: %(danger)s; font-weight: 600; }
QLabel#Success { color: %(success)s; font-weight: 600; }
QLabel#DetailLabel { color: %(muted)s; font-size: 12px; }
QLabel#DetailValue { font-size: 13px; font-weight: 600; color: %(text)s; }
QLabel#DetailTotal { font-size: 15px; font-weight: 800; color: %(accent)s; }
QListWidget#AuditList { border: none; background: transparent; font-size: 12px; color: %(muted)s; }
QListWidget#AuditList::item { padding: 5px 0; border-bottom: 1px solid %(border_soft)s; }

/* cards */
QFrame#Card, QFrame#StatCard, QFrame#Hero { border-radius: 12px; }
QFrame#Card { background-color: %(surface)s; border: 1px solid %(border)s; }
QFrame#StatCard { background-color: %(surface)s; border: 1px solid %(border)s; }
QWidget#ActionBar { background-color: %(surface)s; border-top: 1px solid %(border)s; }
QFrame#Hero {
    background-color: %(hero1)s;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 %(hero1)s, stop:1 %(hero2)s);
    border: none;
}
QLabel#HeroTitle { color: #FFFFFF; font-size: 24px; font-weight: 800; }
QLabel#HeroSub { color: %(hero_text_sub)s; font-size: 13px; }
QLabel#HeroChip {
    color: #FFFFFF;
    font-size: 12px;
    font-weight: 700;
    background-color: %(hero_chip_bg)s;
    border: 1px solid %(white_rgba_26)s;
    border-radius: 9px;
    padding: 7px 13px;
}
QWidget#KpiIcon { border-radius: 10px; }
QLabel#StatValue { font-size: 21px; font-weight: 800; color: %(text)s; }
QLabel#StatLabel { color: %(muted)s; font-size: 12px; }
QLabel#StatSub { color: %(muted)s; font-size: 11px; }

/* buttons: one height for every variant, one radius scale */
QPushButton {
    background-color: %(surface)s;
    border: 1px solid %(border)s;
    border-radius: 10px;
    padding: 7px 18px;
    min-height: 34px;
    font-size: 13px;
    font-weight: 600;
}
QPushButton:hover { background-color: %(hover)s; border-color: %(surface_3)s; }
QPushButton:pressed { background-color: %(pressed)s; }
QPushButton:disabled { background-color: %(surface)s; color: %(muted)s; border-color: %(border_soft)s; }
QPushButton#Primary {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 %(accent_hi)s, stop:1 %(accent_lo)s);
    border: none;
    color: %(on_accent)s;
    font-weight: 700;
}
QPushButton#Primary:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 %(accent)s, stop:1 %(accent_hi)s); }
QPushButton#Primary:pressed { background: %(accent_dark)s; }
QPushButton#Primary:disabled { background: %(surface_3)s; color: %(muted)s; }
QPushButton:focus { border: 1px solid %(accent)s; }
QPushButton#Primary:focus { border: 2px solid %(accent_hi)s; }
QPushButton#NavBtn:focus { border: 1px solid %(accent)s; }
QPushButton#Danger { background-color: %(danger)s; border: none; color: %(on_danger)s; font-weight: 700; }
QPushButton#Danger:hover { background-color: %(danger_hover)s; }
QPushButton#Ghost { background-color: transparent; border: 1px solid %(border)s; color: %(text)s; }
QPushButton#Ghost:hover { background-color: %(surface_2)s; }
QPushButton#GhostOnHero {
    background-color: %(hero_chip_bg)s;
    border: 1px solid %(white_rgba_26)s;
    color: #FFFFFF;
    border-radius: 10px;
    padding: 7px 20px;
    font-weight: 600;
}
QPushButton#GhostOnHero:hover { background-color: %(white_rgba_26)s; }
QPushButton#Small {
    padding: 4px 13px;
    font-size: 12px;
    border-radius: 8px;
    min-height: 26px;
    font-weight: 600;
}
QPushButton#DangerSmall {
    background-color: %(danger_rgba)s;
    border: 1px solid %(danger)s;
    color: %(danger)s;
    padding: 4px 13px;
    font-size: 12px;
    border-radius: 8px;
    min-height: 26px;
    font-weight: 600;
}
QPushButton#DangerSmall:hover { background-color: %(danger)s; color: %(on_danger)s; }

/* inputs: same visual height as buttons */
QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox {
    background-color: %(surface)s;
    border: 1px solid %(border)s;
    border-radius: 9px;
    padding: 6px 10px;
    min-height: 36px;   /* 36 + padding + border = the 50px button height */
    selection-background-color: %(accent)s;
    font-size: 13px;
}
QLineEdit#PathField {
    background-color: %(surface_2)s;
    border-color: %(border_soft)s;
    color: %(muted)s;
    font-size: 12px;
}
QLineEdit#PathField:focus { border-color: %(accent)s; }
QPlainTextEdit, QTextEdit {
    background-color: %(surface)s;
    border: 1px solid %(border)s;
    border-radius: 9px;
    padding: 7px 10px;
    selection-background-color: %(accent)s;
    font-size: 13px;
}
QComboBox::drop-down, QDateEdit::drop-down { border: none; width: 28px; }
QComboBox::down-arrow { width: 12px; height: 12px; margin-right: 8px; }
QAbstractSpinBox { min-height: 36px; }
/* QDateEdit's popup button adds 3px to the style's content hint, which made date
   fields taller than every other input; pin the content box to the shared height */
QDateEdit { max-height: 36px; }
/* the edit inside a spin box is an implementation detail: keep the outer frame
   as the only border, otherwise date fields render 3px taller than the rest */
QAbstractSpinBox QLineEdit {
    background: transparent;
    border: none;
    padding: 0px;
    min-height: 0px;
}
/* A cell editor lives inside a table row, not on a page: it must fit the row
   (34px in the tariff dialog), otherwise it covers the row borders and the user
   cannot see where typing happens. */
QTableWidget QLineEdit, QTableView QLineEdit,
QTableWidget QComboBox, QTableView QComboBox,
QTableWidget QDateEdit, QTableView QDateEdit,
QTableWidget QSpinBox, QTableView QSpinBox,
QTableWidget QDoubleSpinBox, QTableView QDoubleSpinBox {
    min-height: 0px;
    max-height: 26px;
    padding: 0px 8px;
    border-radius: 5px;
    font-size: 12px;
}
QTableWidget QComboBox::drop-down, QTableView QComboBox::drop-down,
QTableWidget QDateEdit::drop-down, QTableView QDateEdit::drop-down { width: 20px; }
QTableWidget QComboBox::down-arrow, QTableView QComboBox::down-arrow,
QTableWidget QDateEdit::down-arrow, QTableView QDateEdit::down-arrow {
    width: 10px;
    height: 10px;
    margin-right: 4px;
}
QLineEdit:hover, QComboBox:hover, QDateEdit:hover, QSpinBox:hover,
QDoubleSpinBox:hover, QPlainTextEdit:hover, QTextEdit:hover { border-color: %(surface_3)s; }
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QPlainTextEdit:focus, QTextEdit:focus {
    border: 1px solid %(accent)s;
    background-color: %(surface)s;
}
QComboBox QAbstractItemView {
    background-color: %(surface_2)s;
    border: 1px solid %(border)s;
    border-radius: 6px;
    selection-background-color: %(accent_solid)s;
    selection-color: %(on_accent)s;
}
/* calendar popup: the global table/header rules clip day cells and hide the
   weekday names, so the month grid gets its own scoped styling */
QCalendarWidget QWidget#qt_calendar_navigationbar {
    background-color: %(surface_2)s;
    border-bottom: 1px solid %(border)s;
}
QCalendarWidget QToolButton {
    background-color: transparent;
    border: none;
    border-radius: 6px;
    padding: 4px 10px;
    color: %(text)s;
    font-size: 13px;
    font-weight: 700;
}
QCalendarWidget QToolButton:hover { background-color: %(hover)s; }
QCalendarWidget QToolButton::menu-indicator { image: none; width: 0; }
QCalendarWidget QSpinBox {
    background-color: %(surface)s;
    border: 1px solid %(border)s;
    border-radius: 6px;
    padding: 2px 6px;
    min-height: 24px;
    color: %(text)s;
    selection-background-color: %(accent_solid)s;
    selection-color: %(on_accent)s;
}
QCalendarWidget QAbstractItemView {
    background-color: %(surface)s;
    color: %(text)s;
    selection-background-color: %(accent_solid)s;
    selection-color: %(on_accent)s;
    border: none;
    outline: none;
    font-size: 12px;
}
QCalendarWidget QAbstractItemView:disabled { color: %(muted)s; }
QCalendarWidget QTableView { border: none; border-radius: 0; }
QCalendarWidget QTableView::item { padding: 0; }
QCalendarWidget QHeaderView { background-color: transparent; border: none; }
QCalendarWidget QHeaderView::section {
    background-color: transparent;
    border: none;
    padding: 2px 0;
    color: %(muted)s;
}
QCheckBox { spacing: 6px; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; border: 1px solid %(border)s; background-color: %(surface)s; }
QCheckBox::indicator:checked { background-color: %(accent)s; border-color: %(accent)s; }

/* disabled inputs must look disabled (they used to look editable) */
QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled, QSpinBox:disabled,
QDoubleSpinBox:disabled, QPlainTextEdit:disabled, QTextEdit:disabled {
    background-color: %(surface_2)s;
    color: %(muted)s;
    border-color: %(border_soft)s;
}
QCheckBox::indicator:hover { border-color: %(accent)s; }
QCheckBox::indicator:disabled { background-color: %(surface_2)s; border-color: %(border_soft)s; }
QTableCornerButton::section { background-color: %(surface_2)s; border: none; }

/* tables */
QTableWidget, QTableView {
    background-color: %(surface)s;
    alternate-background-color: %(surface_2)s;
    gridline-color: %(border)s;      /* every row/column must be visibly divided */
    border: 1px solid %(border)s;
    border-radius: 10px;
    font-size: 13px;
    outline: none;
}
QFrame#Card QTableWidget, QFrame#Card QTableView { border: 1px solid %(border_soft)s; border-radius: 9px; }
QHeaderView { background-color: %(surface_2)s; border: none; }
QHeaderView::section {
    background-color: %(surface_2)s;
    color: %(muted)s;
    padding: 0 12px;
    border: none;
    border-bottom: 1px solid %(border)s;
    border-right: 1px solid %(border)s;   /* keep columns readable above the grid */
    font-size: 12px;
    font-weight: 700;
}
QHeaderView::section:first { border-top-left-radius: 9px; }
QHeaderView::section:last { border-top-right-radius: 9px; }
QHeaderView::section:vertical {
    padding: 0 8px;
    border-bottom: none;
    border-right: 1px solid %(border_soft)s;
    font-weight: 600;
}
QTableWidget::item, QTableView::item { padding: 0 12px; border: none; }
QTableWidget::item:hover, QTableView::item:hover { background-color: %(table_hover)s; }
/* the palette highlight paints the row solid accent underneath the item, so the
   text has to be the on-accent tone (light text on the amber accent was unreadable) */
QTableWidget::item:selected, QTableView::item:selected {
    background-color: %(accent_solid)s;
    color: %(on_accent)s;
}

/* tabs */
QTabWidget::pane { border: 1px solid %(border)s; border-radius: 0 0 10px 10px; background-color: %(bg)s; top: -1px; }
QTabBar::tab {
    background: %(surface_2)s;
    color: %(muted)s;
    padding: 9px 18px;
    border: 1px solid %(border)s;
    border-bottom: none;
    font-weight: 600;
}
QTabBar::tab:first { border-top-left-radius: 9px; }
QTabBar::tab:last { border-top-right-radius: 9px; }
QTabBar::tab:selected { background: %(surface)s; color: %(text)s; border-top: 2px solid %(accent)s; }
QTabBar::tab:hover:!selected { background: %(surface_3)s; }

/* scrollbars */
QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
QScrollBar::handle:vertical { background: %(surface_3)s; border-radius: 6px; min-height: 32px; }
QScrollBar::handle:vertical:hover { background: %(accent)s; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 2px; }
QScrollBar::handle:horizontal { background: %(surface_3)s; border-radius: 6px; min-width: 32px; }
QScrollBar::handle:horizontal:hover { background: %(accent)s; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* menus / dialogs */
QMenuBar {
    background-color: transparent;
    border: none;
    border-bottom: 1px solid %(border_soft)s;
    padding: 2px 6px;
}
QMenuBar::item {
    background: transparent;
    color: %(muted)s;
    padding: 6px 10px;
    border-radius: 6px;
    font-weight: 600;
}
QMenuBar::item:selected { background-color: %(surface_2)s; color: %(text)s; }
QMenuBar::item:pressed { background-color: %(surface_2)s; color: %(text)s; }
QMenu {
    background-color: %(surface)s;
    border: 1px solid %(border)s;
    border-radius: 8px;
    padding: 4px;
}
QMenu::item { padding: 7px 22px; border-radius: 6px; font-size: 13px; }
QMenu::item:selected { background-color: %(accent_solid)s; color: %(on_accent)s; }
QMenu::item:disabled { color: %(muted)s; }
QMenu::separator { height: 1px; background-color: %(border_soft)s; margin: 5px 10px; }
QMenu::item:checked { font-weight: 700; }
QMenu::icon { padding-left: 6px; }
QMessageBox, QDialog { background-color: %(surface)s; }

/* top bar (language / currency / theme selectors) */
QFrame#TopBar { background-color: %(bg)s; border-bottom: 1px solid %(border_soft)s; }
QFrame#TopBar QToolButton {
    background-color: transparent;
    color: %(muted)s;
    border: 1px solid %(border)s;
    border-radius: 9px;
    padding: 5px 12px;
    min-height: 28px;
    font-size: 12px;
    font-weight: 600;
}
QFrame#TopBar QToolButton:hover { background-color: %(surface_2)s; color: %(text)s; border-color: %(surface_3)s; }
QFrame#TopBar QToolButton:pressed { background-color: %(pressed)s; }
QFrame#TopBar QToolButton::menu-indicator { image: none; width: 0; }
QLineEdit#CurrencySearch, QFrame#TopBar QLineEdit {
    background-color: %(surface_2)s;
    border: 1px solid %(border)s;
    border-radius: 8px;
    padding: 6px 9px;
}
QMenu QListWidget { background-color: transparent; border: none; }
QMenu QListWidget::item { padding: 6px 10px; }
QMenu QListWidget::item:hover { background-color: %(surface_2)s; }
"""


_ICON_DIR = Path(__file__).resolve().parents[3] / "assets" / "icons"


def _icon(theme_name: str, file: str) -> str:
    """Absolute, forward-slash path of a generated icon, or '' if it is missing."""
    path = _ICON_DIR / theme_name / file
    return path.as_posix() if path.is_file() else ""


def icon_file(name: str, theme_name: str | None = None) -> str:
    """Path of a generated icon (e.g. "chevron-left") for the active or given palette."""
    return _icon(theme_name or _CURRENT, f"{name}.png")


def _icon_qss(theme_name: str) -> str:
    """Rules that need image files. Without an ``image`` Qt draws NO combo arrow and
    no check mark once ``::drop-down`` / ``::indicator`` are styled. Generated by
    ``scripts/make_icons.py``; silently skipped when the icons are absent."""
    rules = []
    down = _icon(theme_name, "chevron-down.png")
    if down:
        rules.append(
            f'QComboBox::down-arrow, QDateEdit::down-arrow {{ image: url("{down}");'
            " width: 12px; height: 12px; margin-right: 8px; }")
    check = _icon(theme_name, "check.png")
    if check:
        rules.append(f'QCheckBox::indicator:checked {{ image: url("{check}"); }}')
    return "\n".join(rules)


def build_qss(palette: str | None = None, *, rtl: bool = False) -> str:
    name = palette if palette in _PALETTES else _CURRENT
    p = _derive(_PALETTES[name])
    qss = (_QSS % p) + "\n" + _icon_qss(name)
    if rtl:
        # numeric/date text is left-to-right by nature, so a plain line edit hugs the
        # left edge and detaches from its right-hand label: pin every field to the
        # leading (right) edge in RTL layouts.
        qss += "\nQLineEdit { qproperty-alignment: 'AlignRight | AlignVCenter'; }"
    return qss