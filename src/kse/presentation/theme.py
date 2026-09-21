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


def _derive(p: dict) -> dict:
    accent = p["accent"]
    return {
        **p,
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
        "hero_text_sub": _rgba("#FFFFFF", 200),
    }


_PALETTES = {
    "dark": {
        "bg": "#0B0F1A", "surface": "#141C2E", "surface_2": "#1C2740", "surface_3": "#2A3852",
        "border": "#33415E", "border_soft": "#232E49",
        "text": "#F2F6FD", "muted": "#A8B4CB",
        "accent": "#4F7CFF", "accent_dark": "#3157E8", "accent_hi": "#6E95FF", "accent_lo": "#2B4FD1",
        "success": "#36D19B", "danger": "#F26360", "warn": "#F6BC58",
        "hover": "#243152", "pressed": "#1A2238", "danger_hover": "#D44845",
        "hero1": "#3B6CFF", "hero2": "#7A4BF8",
        "table_hover": "#1F2B47",
    },
    "light": {
        "bg": "#F4F7FC", "surface": "#FFFFFF", "surface_2": "#EEF2FA", "surface_3": "#E1E8F4",
        "border": "#D3DCEA", "border_soft": "#E6ECF6",
        "text": "#10172A", "muted": "#4E5E79",
        "accent": "#2A5CE0", "accent_dark": "#2249B8", "accent_hi": "#4E7DF5", "accent_lo": "#2342A8",
        "success": "#0E8C5E", "danger": "#D0343E", "warn": "#C57600",
        "hover": "#E8EEF8", "pressed": "#DCE5F3", "danger_hover": "#B0242E",
        "hero1": "#2F63F0", "hero2": "#5B3DF0",
        "table_hover": "#EFF4FC",
    },
}

_CURRENT = "light"

THEME_AUTO = "auto"
THEME_LIGHT = "light"
THEME_DARK = "dark"
THEME_MODES = (THEME_AUTO, THEME_LIGHT, THEME_DARK)


def current_name() -> str:
    """Name of the currently active theme palette."""
    return _CURRENT


def colors() -> dict:
    """Current active palette (drawing code reads this at paint time)."""
    return _derive(_PALETTES[_CURRENT])


def palette_names() -> tuple[str, ...]:
    return tuple(_PALETTES)


def set_current(name: str) -> str:
    global _CURRENT
    if name not in _PALETTES:
        name = "light"
    _CURRENT = name
    return name


def system_prefers_dark() -> bool:
    """Best-effort detection of the OS light/dark preference (Windows-aware)."""
    try:
        from PyQt6.QtGui import QPalette
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            try:
                color = app.palette().color(QPalette.ColorRole.Window)
                if color.isValid():
                    return color.lightness() < 128
            except Exception:
                pass
            try:
                scheme = app.styleHints().colorScheme()
                return getattr(scheme, "value", 0) == 1  # Qt.ColorScheme.Dark
            except Exception:
                pass
    except Exception:
        pass
    if _sys_platform() == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            ) as key:
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                return value == 0
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
    pal.setColor(QPalette.ColorRole.BrightText, QColor("#FFFFFF"))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(p["accent"]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    pal.setColor(QPalette.ColorRole.Link, QColor(p["accent_hi"]))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(p["muted"]))
    return pal


def apply(qapp, name: str | None = None) -> str:
    """Apply the theme (QSS + QPalette) to a running QApplication. Returns the name."""
    name = resolve_theme_name(name) if name in (None, THEME_AUTO) else name
    set_current(name)
    try:
        qapp.setStyleSheet(build_qss(name))
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
    background-color: %(accent_rgba_12)s; color: %(text)s;
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
}

/* sidebar */
QFrame#Sidebar { background-color: %(surface)s; border-right: 1px solid %(border)s; }
QFrame#BrandLogo { background-color: transparent; border: none; }
QLabel#BrandName { font-size: 15px; font-weight: 800; color: %(text)s; }
QLabel#BrandSub { font-size: 11px; color: %(muted)s; }
QLabel#SectionHeader {
    font-size: 11px;
    font-weight: 700;
    color: %(muted)s;
    padding: 6px 12px 4px 12px;
    margin-top: 6px;
    border-bottom: 1px solid %(border_soft)s;
}
QFrame#NavDivider { background-color: %(border_soft)s; }
QPushButton#NavBtn {
    background-color: transparent;
    border: none;
    border-radius: 9px;
    padding: 9px 14px;
    font-size: 13px;
    font-weight: 600;
    color: %(muted)s;
}
QPushButton#NavBtn:hover { background-color: %(surface_2)s; color: %(text)s; }
QPushButton#NavBtn:checked {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 %(accent)s, stop:1 %(accent_dark)s);
    color: #FFFFFF;
}
QLabel#Version { font-size: 11px; color: %(muted)s; }

/* page chrome */
QLabel#PageTitle { font-size: 22px; font-weight: 800; }
QLabel#PageSub { color: %(muted)s; font-size: 12px; }
QLabel#CardTitle { font-size: 15px; font-weight: 700; }
QLabel#StepTitle { font-size: 12px; font-weight: 700; color: %(accent)s; }
QLabel#Muted { color: %(muted)s; }
QLabel#Error { color: %(danger)s; font-weight: 600; }
QLabel#Success { color: %(success)s; font-weight: 600; }

/* cards */
QFrame#Card, QFrame#StatCard, QFrame#Hero { border-radius: 12px; }
QFrame#Card { background-color: %(surface)s; border: 1px solid %(border)s; }
QFrame#StatCard { background-color: %(surface)s; border: 1px solid %(border)s; }
QFrame#Hero {
    background-color: %(hero1)s;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 %(hero1)s, stop:1 %(hero2)s);
    border: none;
}
QLabel#HeroTitle { color: #FFFFFF; font-size: 22px; font-weight: 800; }
QLabel#HeroSub { color: %(hero_text_sub)s; font-size: 13px; }
QLabel#HeroChip {
    color: %(text)s;
    font-size: 12px;
    font-weight: 700;
    background-color: %(white_rgba_14)s;
    border: 1px solid %(white_rgba_26)s;
    border-radius: 8px;
    padding: 6px 12px;
}
QLabel#KpiIcon { font-size: 19px; border-radius: 10px; }
QLabel#StatValue { font-size: 20px; font-weight: 800; color: %(text)s; }
QLabel#StatLabel { color: %(muted)s; font-size: 12px; }
QLabel#StatSub { color: %(muted)s; font-size: 11px; }

/* buttons */
QPushButton {
    background-color: %(surface_2)s;
    border: 1px solid %(border)s;
    border-radius: 9px;
    padding: 8px 16px;
    min-height: 32px;
    font-weight: 600;
}
QPushButton:hover { background-color: %(hover)s; border-color: %(surface_3)s; }
QPushButton:pressed { background-color: %(pressed)s; }
QPushButton:disabled { background-color: %(surface)s; color: %(muted)s; border-color: %(border)s; }
QPushButton#Primary {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 %(accent_hi)s, stop:1 %(accent_lo)s);
    border: none;
    color: #FFFFFF;
    font-weight: 700;
}
QPushButton#Primary:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 %(accent)s, stop:1 %(accent_hi)s); }
QPushButton#Primary:pressed { background: %(accent_dark)s; }
QPushButton#Danger { background-color: %(danger)s; border: none; color: #FFFFFF; font-weight: 700; }
QPushButton#Danger:hover { background-color: %(danger_hover)s; }
QPushButton#Ghost { background-color: transparent; border: 1px solid %(border)s; color: %(text)s; }
QPushButton#Ghost:hover { background-color: %(surface_2)s; }
QPushButton#GhostOnHero {
    background-color: %(white_rgba_14)s;
    border: 1px solid %(white_rgba_26)s;
    color: #FFFFFF;
    border-radius: 9px;
    padding: 8px 18px;
    font-weight: 600;
}
QPushButton#GhostOnHero:hover { background-color: %(white_rgba_26)s; }
QPushButton#Small { padding: 4px 12px; font-size: 12px; border-radius: 7px; min-height: 26px; font-weight: 600; }
QPushButton#DangerSmall {
    background-color: %(danger_rgba)s;
    border: 1px solid %(danger)s;
    color: %(danger)s;
    padding: 4px 12px;
    font-size: 12px;
    border-radius: 7px;
    font-weight: 600;
}
QPushButton#DangerSmall:hover { background-color: %(danger)s; color: #FFFFFF; }

/* inputs */
QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox {
    background-color: %(surface)s;
    border: 1px solid %(border)s;
    border-radius: 8px;
    padding: 7px 10px;
    min-height: 30px;
    selection-background-color: %(accent)s;
    font-size: 13px;
}
QPlainTextEdit, QTextEdit {
    background-color: %(surface)s;
    border: 1px solid %(border)s;
    border-radius: 8px;
    padding: 7px 10px;
    selection-background-color: %(accent)s;
    font-size: 13px;
}
QComboBox::drop-down, QDateEdit::drop-down { border: none; width: 26px; }
QComboBox::down-arrow { width: 12px; height: 12px; margin-right: 6px; }
QAbstractSpinBox { min-height: 30px; }
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
    selection-background-color: %(accent)s;
    selection-color: #FFFFFF;
}
QCheckBox { spacing: 6px; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; border: 1px solid %(border)s; background-color: %(surface)s; }
QCheckBox::indicator:checked { background-color: %(accent)s; border-color: %(accent)s; }

/* tables */
QTableWidget, QTableView {
    background-color: %(surface)s;
    alternate-background-color: %(surface_2)s;
    gridline-color: %(border)s;
    border: 1px solid %(border)s;
    border-radius: 9px;
    font-size: 13px;
}
QHeaderView::section {
    background-color: %(surface_2)s;
    color: %(muted)s;
    padding: 9px 10px;
    border: none;
    border-bottom: 1px solid %(border)s;
    font-size: 12px;
    font-weight: 700;
}
QTableWidget::item, QTableView::item { padding: 6px 8px; border: none; }
QTableWidget::item:hover, QTableView::item:hover { background-color: %(table_hover)s; }
QTableWidget::item:selected, QTableView::item:selected { background-color: %(accent_rgba_12)s; color: %(text)s; }

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
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: %(surface_3)s; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: %(accent)s; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: %(surface_3)s; border-radius: 5px; min-width: 30px; }
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
QMenu::item:selected { background-color: %(accent)s; color: #FFFFFF; }
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
    border-radius: 8px;
    padding: 5px 10px;
    font-size: 12px;
    font-weight: 600;
}
QFrame#TopBar QToolButton:hover { background-color: %(surface_2)s; color: %(text)s; border-color: %(surface_3)s; }
QFrame#TopBar QToolButton:pressed { background-color: %(pressed)s; }
QFrame#TopBar QToolButton::menu-indicator { image: none; width: 0; }
QLineEdit#CurrencySearch, QFrame#TopBar QLineEdit {
    background-color: %(surface_2)s;
    border: 1px solid %(border)s;
    border-radius: 7px;
    padding: 6px 9px;
}
QMenu QListWidget { background-color: transparent; border: none; }
QMenu QListWidget::item { padding: 6px 10px; }
QMenu QListWidget::item:hover { background-color: %(surface_2)s; }
"""


def build_qss(palette: str | None = None) -> str:
    p = _derive(_PALETTES[palette if palette in _PALETTES else _CURRENT])
    return _QSS % p