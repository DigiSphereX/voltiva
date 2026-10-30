"""Static guards for the presentation layer (run without Qt)."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def test_qss_lint_clean_for_both_palettes():
    import lint_qss
    from kse.presentation import theme
    for name in theme.palette_names():
        assert lint_qss.lint(name) == []


def test_palette_contrast_passes_wcag_aa():
    import check_contrast
    assert check_contrast.main() == 0


def test_rtl_qss_pins_every_field_to_the_leading_edge():
    """Without this, numeric/date text hugs the left edge in Arabic forms while the
    label sits on the right, so each field looks half empty."""
    from kse.presentation import theme
    assert "qproperty-alignment" not in theme.build_qss("light")
    rtl = theme.build_qss("light", rtl=True)
    assert "QLineEdit { qproperty-alignment: 'AlignRight | AlignVCenter'; }" in rtl


def test_generated_icons_exist_for_every_palette():
    from kse.presentation import theme
    from kse.presentation.main_window import MainWindow
    files = ["chevron-down.png", "chevron-left.png", "chevron-right.png", "check.png"]
    for key, _ in [item for _, items in MainWindow.NAV_GROUPS for item in items] + \
            [("settings", "nav_settings")]:
        files += [f"nav-{key}.png", f"nav-{key}-on.png"]
    for name in theme.palette_names():
        for f in files:
            assert (ROOT / "assets" / "icons" / name / f).is_file(), (name, f)


def test_every_palette_declares_kind_and_complete_tokens():
    from kse.presentation import theme
    required = (
        "bg", "surface", "surface_2", "surface_3", "border", "border_soft",
        "text", "muted", "accent", "accent_dark", "accent_hi", "accent_lo",
        "accent_solid", "on_accent", "on_danger",
        "success", "danger", "warn", "hover", "pressed", "danger_hover",
        "hero1", "hero2", "table_hover", "grid",
        "violet", "teal", "orange", "gold", "series",
    )
    for name in theme.palette_names():
        p = theme._PALETTES[name]
        assert p.get("kind") in ("light", "dark"), name
        assert not [k for k in required if k not in p], (name, [k for k in required if k not in p])
        assert isinstance(p["series"], tuple) and len(p["series"]) >= 6, name


def test_theme_modes_cover_auto_and_every_palette_once():
    from kse.presentation import theme
    assert set(theme.THEME_MODES) == {"auto"} | set(theme.palette_names())
    assert len(theme.THEME_UI_ORDER) == len(set(theme.THEME_UI_ORDER))
    assert set(theme.THEME_UI_ORDER) == set(theme.THEME_MODES)
    assert theme.THEME_UI_ORDER[0] == theme.THEME_AUTO
    for name in theme.palette_names():
        assert name in theme.THEME_LABEL_KEYS


def test_auto_theme_follows_windows_not_the_applied_palette(monkeypatch):
    """Auto mode must read Windows, not QApplication.palette().

    The app replaces the application palette with its own theme; reading it back made
    auto resolve to whatever was already applied (always light after a light start).
    """
    from kse.presentation import theme
    monkeypatch.setattr(theme, "_sys_platform", lambda: "win32")
    try:
        monkeypatch.setattr(theme, "_windows_apps_use_light", lambda: False)
        theme.set_current("light")          # the applied palette must not matter
        assert theme.system_prefers_dark() is True
        assert theme.resolve_theme_name("auto") == "dark"

        monkeypatch.setattr(theme, "_windows_apps_use_light", lambda: True)
        theme.set_current("dark")
        assert theme.system_prefers_dark() is False
        assert theme.resolve_theme_name("auto") == "light"
    finally:
        theme.set_current("light")


def test_status_chip_background_is_opaque_and_readable_on_selected_rows():
    """A translucent chip tint let the selected row's accent bleed through (red on amber)."""
    from kse.presentation import theme
    sys.path.insert(0, str(ROOT / "scripts"))
    from check_contrast import ratio
    try:
        for name in theme.palette_names():
            theme.set_current(name)
            p = theme.colors()
            for key in ("success", "danger", "warn", "muted"):
                chip_bg = theme.blend_hex(p[key], p["surface"], 16 / 255)
                assert ratio(p[key], chip_bg) >= 4.5, (name, key, ratio(p[key], chip_bg))
    finally:
        theme.set_current("light")


def test_theme_labels_are_translated_in_every_language():
    from kse.presentation import i18n, theme
    for lang in i18n.LANGS:
        for key in list(theme.THEME_LABEL_KEYS.values()) + ["st_theme_active"]:
            assert key in i18n._STRINGS[lang], (lang, key)


def _used_keys():
    # only complete literal keys: tr("key") / tr("key", x=1); "prefix_" + variable is skipped
    pat = re.compile(r"""\.tr\(\s*["']([a-z0-9_]+)["']\s*[,)]""")
    keys = {}
    for path in (ROOT / "src" / "kse").rglob("*.py"):
        if path.name == "i18n.py":
            continue
        for m in pat.finditer(path.read_text(encoding="utf-8")):
            keys.setdefault(m.group(1), path.name)
    return keys


def test_every_translation_key_used_in_code_exists_in_english_and_arabic():
    from kse.presentation import i18n
    missing_en = {k: f for k, f in _used_keys().items() if k not in i18n._STRINGS["en"]}
    missing_ar = {k: f for k, f in _used_keys().items() if k not in i18n._STRINGS["ar"]}
    assert not missing_en, f"missing in EN: {missing_en}"
    assert not missing_ar, f"missing in AR: {missing_ar}"


def test_format_placeholders_match_between_languages():
    """A translation with different {placeholders} raises KeyError at runtime."""
    from kse.presentation import i18n
    ph = re.compile(r"{(\w+)}")
    bad = []
    for key, en in i18n._STRINGS["en"].items():
        for lang, table in i18n._STRINGS.items():
            other = table.get(key)
            if other and set(ph.findall(other)) != set(ph.findall(en)):
                bad.append((key, lang))
    assert not bad, bad[:20]


def test_dynamic_payment_error_keys_exist():
    from kse.domain.errors import PaymentError
    from kse.presentation import i18n
    for reason in PaymentError._MESSAGES:
        for lang in ("en", "ar"):
            assert f"err_payment_{reason}" in i18n._STRINGS[lang], (reason, lang)


def test_no_duplicate_keys_in_any_dictionary_literal_of_i18n():
    """A duplicated key silently overrides the first text (the earlier wording is lost)."""
    import ast
    tree = ast.parse((ROOT / "src" / "kse" / "presentation" / "i18n.py").read_text(encoding="utf-8"))
    dups = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            seen = set()
            for k in node.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    if k.value in seen:
                        dups.append((k.value, k.lineno))
                    seen.add(k.value)
    assert not dups, dups
