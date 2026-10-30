"""Static lint for the application style sheet (Qt silently drops rules it cannot parse).

    python scripts/lint_qss.py      # exit code 1 on problems

Checks, for BOTH palettes: balanced braces, every declaration is ``property: value;``, the
property name is a known Qt Style Sheet property, colours/rgba()/url() values are well formed,
every referenced image file exists, no unresolved %(...)s placeholders remain.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from kse.presentation import theme  # noqa: E402

KNOWN = set("""
alternate-background-color background background-color background-position background-repeat background-clip
background-origin background-attachment border border-top border-right border-bottom border-left border-color
border-top-color border-right-color border-bottom-color border-left-color border-image border-radius
border-top-left-radius border-top-right-radius border-bottom-left-radius border-bottom-right-radius border-style
border-width border-top-width border-right-width border-bottom-width border-left-width bottom button-layout color
dialogbuttonbox-buttons-have-icons font font-family font-size font-style font-weight gridline-color height icon
icon-size image image-position left lineedit-password-character margin margin-top margin-right margin-bottom
margin-left max-height max-width messagebox-text-interaction-flags min-height min-width opacity outline padding
padding-top padding-right padding-bottom padding-left paint-alternating-row-colors-for-empty-area position
right selection-background-color selection-color show-decoration-selected spacing subcontrol-origin
subcontrol-position text-align text-decoration top widget-animation-duration width
""".split())
COLOR = re.compile(r"^(#[0-9A-Fa-f]{3,8}|rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*(,\s*\d+\s*)?\)|[A-Za-z]+)$")   # hex, rgb()/rgba(), named colour (red, transparent, ...)


def lint(name: str) -> list[str]:
    qss = theme.build_qss(name)
    problems: list[str] = []
    if qss.count("{") != qss.count("}"):
        problems.append(f"[{name}] unbalanced braces: {qss.count('{')} '{{' vs {qss.count('}')} '}}'")
    if re.search(r"%\(\w+\)s", qss):
        problems.append(f"[{name}] unresolved placeholder: {re.search(r'%\(\w+\)s', qss).group(0)}")
    body = re.sub(r"/\*.*?\*/", "", qss, flags=re.S)
    for block in re.finditer(r"([^{}]+)\{([^{}]*)\}", body):
        selector = " ".join(block.group(1).split())
        for decl in [d.strip() for d in block.group(2).split(";") if d.strip()]:
            if ":" not in decl:
                problems.append(f"[{name}] '{selector}': malformed declaration {decl!r}")
                continue
            prop, value = (x.strip() for x in decl.split(":", 1))
            if prop not in KNOWN:
                problems.append(f"[{name}] '{selector}': unknown property {prop!r}")
            if prop in ("color", "background-color", "border-color", "gridline-color",
                        "selection-background-color", "selection-color", "alternate-background-color") \
                    and not COLOR.match(value):
                problems.append(f"[{name}] '{selector}': bad colour {prop}: {value!r}")
            for m in re.finditer(r"""url\(\s*(?:"([^"]*)"|'([^']*)'|([^)]*))\s*\)""", value):
                target = next((g for g in m.groups() if g is not None), "").strip()
                if target and not Path(target).is_file():
                    problems.append(f"[{name}] '{selector}': missing image {target}")
            for m in re.finditer(r"#[0-9A-Fa-f]+", value):
                if len(m.group(0)) not in (4, 5, 7, 9):
                    problems.append(f"[{name}] '{selector}': malformed hex {m.group(0)}")
            if prop in ("border", "border-top", "border-right", "border-bottom", "border-left") \
                    and value != "none":
                if not re.match(r"^\d+px\s+(solid|dashed|dotted|none)\s+\S.*$", value):
                    problems.append(f"[{name}] '{selector}': odd border shorthand {value!r}")
    return problems


def main() -> int:
    problems = [p for n in theme.palette_names() for p in lint(n)]
    for p in problems:
        print("PROBLEM", p)
    print("QSS lint:", "FAILED" if problems else "OK", f"({len(problems)} problem(s))")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
