"""Generate the small PNG icons used by the Qt style sheet and the compact sidebar.

Qt style sheets cannot draw a combo-box arrow or a check mark by themselves once the
widget is restyled - without an ``image`` the arrow simply disappears (see the
combo boxes in the old screenshots). The compact sidebar uses the same generator so
every language shows the same drawn icon instead of a font-dependent glyph.

    python scripts/make_icons.py

Requires Pillow. Output: assets/icons/<theme>/{chevron-down,check,nav-*}[@2x].png
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kse.presentation import theme  # noqa: E402  (pure-python; Qt is imported lazily)

SS = 16  # supersampling factor for smooth edges


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _polyline(size: int, points, color, stroke: float) -> Image.Image:
    big = size * SS
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pts = [(x * big, y * big) for x, y in points]
    w = max(1, round(stroke * big))
    d.line(pts, fill=color + (255,), width=w, joint="curve")
    r = w / 2
    for x, y in (pts[0], pts[-1]):  # round caps
        d.ellipse((x - r, y - r, x + r, y + r), fill=color + (255,))
    return img.resize((size, size), Image.LANCZOS)


def _strokes(size: int, color, draw) -> Image.Image:
    """Render one icon: several strokes share a canvas so line caps overlap cleanly."""
    big = size * SS
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w = max(1, round(0.095 * big))

    def line(points, closed=False):
        pts = [(x * big, y * big) for x, y in points]
        if closed:
            pts.append(pts[0])
        d.line(pts, fill=color + (255,), width=w, joint="curve")
        r = w / 2
        for x, y in (pts[0], pts[-1]):
            d.ellipse((x - r, y - r, x + r, y + r), fill=color + (255,))

    def circle(cx, cy, r, filled=False):
        box = ((cx - r) * big, (cy - r) * big, (cx + r) * big, (cy + r) * big)
        if filled:
            d.ellipse(box, fill=color + (255,))
        else:
            d.ellipse(box, outline=color + (255,), width=w)

    draw(line, circle)
    return img.resize((size, size), Image.LANCZOS)


def _home(line, circle):
    line([(0.18, 0.47), (0.50, 0.18), (0.82, 0.47)])
    line([(0.27, 0.42), (0.27, 0.81), (0.73, 0.81), (0.73, 0.42)])


def _plus(line, circle):
    line([(0.50, 0.20), (0.50, 0.80)])
    line([(0.20, 0.50), (0.80, 0.50)])


def _invoices(line, circle):
    line([(0.30, 0.17), (0.70, 0.17), (0.70, 0.83), (0.30, 0.83)], closed=True)
    line([(0.40, 0.37), (0.60, 0.37)])
    line([(0.40, 0.52), (0.60, 0.52)])
    line([(0.40, 0.67), (0.52, 0.67)])


def _verify(line, circle):
    line([(0.19, 0.53), (0.42, 0.76), (0.81, 0.26)])


def _review(line, circle):
    line([(0.20, 0.27), (0.80, 0.27), (0.80, 0.83), (0.20, 0.83)], closed=True)
    line([(0.20, 0.43), (0.80, 0.43)])
    line([(0.34, 0.15), (0.34, 0.32)])
    line([(0.66, 0.15), (0.66, 0.32)])


def _analytics(line, circle):
    line([(0.22, 0.80), (0.78, 0.80)])
    line([(0.32, 0.70), (0.32, 0.50)])
    line([(0.50, 0.70), (0.50, 0.30)])
    line([(0.68, 0.70), (0.68, 0.58)])


def _tariffs(line, circle):
    line([(0.22, 0.24), (0.52, 0.24), (0.80, 0.50), (0.52, 0.78), (0.22, 0.50)],
         closed=True)
    circle(0.36, 0.37, 0.045, filled=True)


def _subscribers(line, circle):
    circle(0.50, 0.33, 0.13)
    line([(0.24, 0.81), (0.31, 0.64), (0.50, 0.57), (0.69, 0.64), (0.76, 0.81)])


def _settings(line, circle):
    """Sliders, not a gear: at 18px a toothed ring reads as a sun."""
    for y, knob in ((0.30, 0.40), (0.50, 0.62), (0.70, 0.46)):
        line([(0.22, y), (0.78, y)])
        circle(knob, y, 0.075, filled=True)


NAV_ICONS = {
    "dashboard": _home,
    "new_invoice": _plus,
    "invoices": _invoices,
    "verify": _verify,
    "review": _review,
    "analytics": _analytics,
    "tariffs": _tariffs,
    "subscribers": _subscribers,
    "settings": _settings,
}

NAV_SIZE = 18


def make(theme_name: str) -> None:
    palette = theme._PALETTES[theme_name]
    check_rgb = _rgb(palette.get("on_accent", "#FFFFFF"))
    out = ROOT / "assets" / "icons" / theme_name
    out.mkdir(parents=True, exist_ok=True)
    for scale, suffix in ((1, ""), (2, "@2x")):
        size = 12 * scale
        _polyline(size, [(0.20, 0.36), (0.50, 0.66), (0.80, 0.36)],
                  _rgb(palette["muted"]), 0.14).save(out / f"chevron-down{suffix}.png")
        _polyline(size, [(0.66, 0.20), (0.36, 0.50), (0.66, 0.80)],
                  _rgb(palette["muted"]), 0.14).save(out / f"chevron-left{suffix}.png")
        _polyline(size, [(0.34, 0.20), (0.64, 0.50), (0.34, 0.80)],
                  _rgb(palette["muted"]), 0.14).save(out / f"chevron-right{suffix}.png")
        _polyline(size, [(0.20, 0.54), (0.42, 0.75), (0.82, 0.28)],
                  check_rgb, 0.15).save(out / f"check{suffix}.png")
        nav_size = NAV_SIZE * scale
        for key, draw in NAV_ICONS.items():
            _strokes(nav_size, _rgb(palette["muted"]), draw) \
                .save(out / f"nav-{key}{suffix}.png")
            _strokes(nav_size, check_rgb, draw) \
                .save(out / f"nav-{key}-on{suffix}.png")


if __name__ == "__main__":
    for name in theme.palette_names():
        make(name)
        print("icons written for", name)
