"""WCAG contrast audit of the light/dark palettes (pure Python, no Qt needed).

    python scripts/check_contrast.py        # exit code 1 if a required pair fails
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from kse.presentation import theme  # noqa: E402


def _rgb(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def _lum(h):
    def f(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (f(c) for c in _rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(a, b):
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def blend(fg, bg, alpha):
    f, b = _rgb(fg), _rgb(bg)
    return "#%02X%02X%02X" % tuple(round(f[i] * alpha + b[i] * (1 - alpha)) for i in range(3))


def main() -> int:
    failed = 0
    for name in theme.palette_names():
        p = theme._derive(theme._PALETTES[name])
        checks = []  # (label, fg, bg, minimum)
        for k in ("text", "muted", "accent", "success", "danger", "warn"):
            checks.append((f"{k} on surface", p[k], p["surface"], 4.5 if k != "accent" else 4.5))
            checks.append((f"{k} on page bg", p[k], p["bg"], 4.5))
        for k in ("success", "danger", "warn"):  # status chips: text on its own 6% tint
            checks.append((f"{k} chip text", p[k], blend(p[k], p["surface"], 16 / 255), 4.5))
        # table text on alternating and hovered rows, not just the base surface
        for bg_key in ("surface_2", "table_hover"):
            for k in ("text", "muted", "success", "danger", "warn"):
                checks.append((f"{k} on {bg_key}", p[k], p[bg_key], 4.5))
        for k in ("violet", "teal", "orange", "gold"):
            checks.append((f"KPI icon {k}", p[k], p["surface"], 3.0))
        for i, c in enumerate(p["series"]):
            checks.append((f"chart series {i + 1}", c, p["surface"], 3.0))
        # filled controls: primary button gradient, active nav, selected menu rows
        for key in ("accent_solid", "accent_hi", "accent_lo"):
            checks.append((f"on_accent over {key}", p["on_accent"], p[key], 4.5))
        checks.append(("on_danger over danger", p["on_danger"], p["danger"], 4.5))
        # hero: white text on the darker overlay chip over both gradient ends
        for end in ("hero1", "hero2"):
            chip = blend("#000000", p[end], 58 / 255)
            checks.append((f"hero chip text over {end}", "#FFFFFF", chip, 4.5))
            checks.append((f"hero title over {end}", "#FFFFFF", p[end], 4.5))
        print(f"== {name}")
        for label, fg, bg, need in checks:
            r = ratio(fg, bg)
            ok = r >= need
            failed += not ok
            print(f"  {'OK  ' if ok else 'FAIL'} {label:28s} {r:5.2f}  (need {need})")
    print("\nFAILED" if failed else "\nall pairs pass", failed or "")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
