"""OCR integration tests — spec §40: test cases derived from real invoices.

The OCR tests run only when Tesseract is installed; otherwise the pure-Python
parsing tests still run everywhere.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

from kse.infrastructure.ocr.invoice_ocr import ExtractedInvoice, ExtractedField, InvoiceOcr, OcrToken, _norm_ar  # noqa: E402


def _render_fees_list(path: str) -> str:
    """Render a synthetic 'قائمة أجور الكهرباء' (fees list) with reference numbers."""
    from PIL import Image, ImageDraw, ImageFont

    import arabic_reshaper
    from bidi.algorithm import get_display

    W, H = 1200, 720
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 30)
        fb = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 34)
    except Exception:
        f = ImageFont.load_default()
        fb = f

    y = 30
    d.text((60, y), get_display(arabic_reshaper.reshape("الشركة العامة لتوزيع الكهرباء - الوسطى")), font=fb, fill=0)
    y += 50
    d.text((60, y), get_display(arabic_reshaper.reshape("قائمة أجور الكهرباء")) + "  القائمة رقم: 24608", font=fb, fill=0)
    y += 60
    for i in range(6):
        d.line((40, y + i * 60, W - 60, y + i * 60), fill=0, width=2)
    rows = [
        ("القراءة السابقة", "13578"),
        ("القراءة اللاحقة", "17162"),
        ("الاستهلاك", "3584"),
        ("التاريخ", "20240315"),
        ("المجموع", "57344"),
    ]
    for i, (label, val) in enumerate(rows):
        d.text((80, y + i * 60 + 22), get_display(arabic_reshaper.reshape(label)), font=f, fill=0)
        d.text((W - 320, y + i * 60 + 22), "   " + val, font=f, fill=0)
    d.text((80, y + len(rows) * 60 + 20), "16 * 3584", font=f, fill=0)
    img.save(path)
    return path


# ---------------------------------------------------------------------------
# pure-Python parsing (always runs)
def test_normalize_digits_arabic_and_ascii():
    assert InvoiceOcr.normalize_digits("١٢٣٤٥٦٧٨٩٠") == "1234567890"
    assert InvoiceOcr.normalize_digits("165,") == "165"
    assert InvoiceOcr.normalize_digits("") == ""


def test_parse_fields_label_regex():
    text = "رقم الحساب: 552211\nالقراءة السابقة 13578\nالقراءة الحالية 17162\nالمبلغ الحالي 35840"
    fields = InvoiceOcr.parse_fields(text)
    assert fields["account_no"].value == "552211"
    assert fields["previous_reading"].value == "13578"
    assert fields["current_reading"].value == "17162"
    assert fields["official_amount"].value == "35840"


def test_parse_fields_english_variants():
    fields = InvoiceOcr.parse_fields("Account no: 77 Previous reading 100 Current reading 500")
    assert fields["account_no"].value == "77"
    assert fields["previous_reading"].value == "100"
    assert fields["current_reading"].value == "500"


def test_normalize_digits_strips_unicode_marks():
    assert "3584" == InvoiceOcr.normalize_digits("3584\u200f\u200e")


def test_norm_ar_loose_matching():
    assert _norm_ar("القراءة السابقة") == "القرااه السابقه"
    assert _norm_ar("القراءه السابقه") == "القرااه السابقه"
    assert _norm_ar("المجموع المطلوب") == "المجموع المطلوب"
    assert _norm_ar("أجور أخرى") == "اجور اخري"


def test_anchor_fills_value_below_only():
    fields = {"account_no": ExtractedField("account_no", "")}
    anchors_and_numbers = [
        OcrToken(text="رقم الحساب", confidence=0.8, x=100, y=100, w=140, h=30),
        OcrToken(text="310931194807", confidence=0.9, x=105, y=150, w=220, h=32),
    ]
    InvoiceOcr._anchor_extract(fields, anchors_and_numbers)
    assert fields["account_no"].value == "310931194807"
    assert fields["account_no"].confidence >= 0.6


def test_anchor_ignores_side_value_and_above():
    fields = {"previous_reading": ExtractedField("previous_reading", "")}
    tokens = [
        OcrToken(text="القراءة السابقة", confidence=0.8, x=100, y=100, w=140, h=30),
        OcrToken(text="13578", confidence=0.9, x=880, y=122, w=100, h=30),   # same-line (right), not below
        OcrToken(text="99999", confidence=0.9, x=105, y=60, w=100, h=30),    # above the anchor
    ]
    InvoiceOcr._anchor_extract(fields, tokens)
    assert fields["previous_reading"].value == ""


def test_anchor_merges_adjacent_digits():
    fields = {"account_no": ExtractedField("account_no", "")}
    tokens = [
        OcrToken(text="رقم الحساب", confidence=0.8, x=100, y=100, w=140, h=30),
        OcrToken(text="310931", confidence=0.9, x=105, y=150, w=110, h=32),
        OcrToken(text="194807", confidence=0.88, x=220, y=150, w=110, h=32),
    ]
    InvoiceOcr._anchor_extract(fields, tokens)
    assert fields["account_no"].value == "310931194807"


def test_anchor_merges_overlapping_boundary_once():
    """Overlapping boxes double-read the boundary glyphs — strip them, don't double them.

    Mirrors the real scan: tokens "8109311" (x 1316..1493) and "1194807"
    (x 1460..1633) overlap by ~one glyph; naive concatenation produced the
    14-digit "81093111194807" instead of "810931194807".
    """
    fields = {"account_no": ExtractedField("account_no", "")}
    tokens = [
        OcrToken(text="رقم الحساب", confidence=0.8, x=1300, y=550, w=180, h=30),
        OcrToken(text="8109311", confidence=0.43, x=1316, y=599, w=177, h=37),
        OcrToken(text="1194807", confidence=0.35, x=1460, y=594, w=173, h=58),
    ]
    InvoiceOcr._anchor_extract(fields, tokens)
    assert fields["account_no"].value == "810931194807"


def test_anchor_overlap_without_text_match_keeps_digits():
    fields = {"previous_reading": ExtractedField("previous_reading", "")}
    tokens = [
        OcrToken(text="القراءة السابقة", confidence=0.8, x=100, y=100, w=140, h=30),
        OcrToken(text="1357", confidence=0.9, x=105, y=150, w=100, h=30),
        OcrToken(text="8901", confidence=0.9, x=190, y=150, w=100, h=30),  # overlaps, no shared boundary
    ]
    InvoiceOcr._anchor_extract(fields, tokens)
    assert fields["previous_reading"].value == "13578901"


def test_anchor_does_not_overwrite_existing():
    fields = {"official_amount": ExtractedField("official_amount", "57344", 0.6)}
    tokens = [
        OcrToken(text="المجموع", confidence=0.8, x=100, y=100, w=100, h=30),
        OcrToken(text="999", confidence=0.9, x=105, y=150, w=60, h=30),
    ]
    InvoiceOcr._anchor_extract(fields, tokens)
    assert fields["official_amount"].value == "57344"


def test_anchor_priority_zone2_before_zone1():
    fields: dict[str, ExtractedField] = {
        "account_no": ExtractedField("account_no", ""),
        "subscription_no": ExtractedField("subscription_no", ""),
    }
    tokens = [
        OcrToken(text="رقم الحساب", confidence=0.8, x=100, y=100, w=140, h=30),
        OcrToken(text="310931194807", confidence=0.9, x=105, y=150, w=220, h=32),
        OcrToken(text="رقم الإشتراك", confidence=0.8, x=100, y=400, w=150, h=30),
        OcrToken(text="558812", confidence=0.9, x=105, y=450, w=120, h=32),
    ]
    InvoiceOcr._anchor_extract(fields, tokens)
    assert fields["account_no"].value == "310931194807"
    assert fields["subscription_no"].value == "558812"


def test_anchor_x_overlap_ties_to_nearest_center():
    fields = {"total_due": ExtractedField("total_due", "")}
    tokens = [
        OcrToken(text="المجموع المطلوب", confidence=0.8, x=100, y=100, w=260, h=30),
        OcrToken(text="11111", confidence=0.7, x=60, y=150, w=80, h=30),
        OcrToken(text="22222", confidence=0.75, x=200, y=150, w=80, h=30),
    ]
    # anchor center at x=230; "22222" (x center 240) is closer than "11111" (100)
    InvoiceOcr._anchor_extract(fields, tokens)
    assert fields["total_due"].value == "22222"


def test_anchor_enforces_account_length():
    fields = {"account_no": ExtractedField("account_no", ""),
              "total_due": ExtractedField("total_due", "")}
    tokens = [
        OcrToken(text="رقم الحساب", confidence=0.8, x=100, y=100, w=140, h=30),
        OcrToken(text="552211", confidence=0.9, x=105, y=150, w=100, h=32),
        OcrToken(text="المجموع المطلوب", confidence=0.8, x=500, y=100, w=200, h=30),
        OcrToken(text="57344", confidence=0.9, x=540, y=150, w=100, h=32),
    ]
    InvoiceOcr._anchor_extract(fields, tokens)
    assert fields["account_no"].value == ""  # 6 digits < 10 → rejected
    assert fields["total_due"].value == "57344"


# ---------------------------------------------------------------------------
# end-to-end OCR (skips when Tesseract not available)
pytestmark = pytest.mark.skipif(not InvoiceOcr.is_available(), reason="Tesseract not installed")


def test_ocr_synthetic_fees_list(tmp_path):
    img = _render_fees_list(str(tmp_path / "fees.png"))
    res: ExtractedInvoice = InvoiceOcr.extract(img)
    values = res.confirmed_values()
    assert res.engine == "tesseract"
    assert values.get("consumption_kwh") == "3584"
    assert values.get("rate") == "16"
    assert values.get("official_amount") == "57344"
    assert values.get("issue_date") == "20240315"
    assert any(t.digits == "3584" for t in res.numeric_tokens())


def test_ocr_screenshot_fixture():
    """Spec §40 discipline: the attached real invoice must be readable."""
    root = os.path.dirname(os.path.dirname(__file__))
    fixture = os.path.join(root, "Screenshot 2026-09-13 160638.png")
    if not os.path.isfile(fixture):
        pytest.skip("invoice screenshot fixture not present")
    res: ExtractedInvoice = InvoiceOcr.extract(fixture)
    tokens = {t.digits for t in res.numeric_tokens()}
    assert res.text.strip(), "expected to extract some text"
    assert tokens, "expected to extract numeric tokens"
    # the consumption 3584 must appear either directly or as the derived consumption
    assert res.confirmed_values().get("consumption_kwh") == "3584" or "3584" in tokens