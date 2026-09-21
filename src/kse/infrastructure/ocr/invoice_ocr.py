"""OCR — optional data import from invoice images (spec §15).

OCR is never trusted blindly: extracted values are always shown in a
"review extracted data" step and the user must confirm before any use.
If Tesseract is not installed the module degrades gracefully.

Pipeline:  preprocess -> word tokens (with confidence) -> field mapping
           + table structure detection + per-cell extraction.

Usage:
    from kse.infrastructure.ocr import InvoiceOcr
    res = InvoiceOcr.extract("invoice.png")
    res.text                             -> full text
    res.tokens                           -> positioned tokens + confidence
    res.fields                           -> dict[str, ExtractedField]
    res.confirmed_values()               -> dict[str, str]
"""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import date, datetime

from ...domain.errors import OcrUnavailableError

_DIGITS_AR = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

_RE_LABEL_PREV = re.compile(r"السابقة|سابقه|سابق|prev", re.IGNORECASE)
_RE_LABEL_CURR = re.compile(r"الحالية|الحالي|حالية|حالي|curr|current|present", re.IGNORECASE)
_RE_READING_NOT = re.compile(r"أجور|اجور|مبلغ|المجموع|فتيحة|فاتورة")


def _is_reading_label(token: "OcrToken", which: str) -> bool:
    txt = token.text
    if not any(ch.isalpha() for ch in txt):
        return False
    if _RE_READING_NOT.search(txt):
        return False
    if which == "prev":
        return bool(_RE_LABEL_PREV.search(txt))
    return bool(_RE_LABEL_CURR.search(txt))


@dataclass
class ExtractedField:
    name: str
    value: str
    confidence: float = 0.0  # 0..1; 0 = best-effort regex
    raw: str = ""


@dataclass
class OcrToken:
    text: str = ""
    confidence: float = 0.0  # 0..1
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0

    @property
    def digits(self) -> str:
        norm = InvoiceOcr.normalize_digits(self.text)
        return norm if norm and norm.isdigit() else ""

    @property
    def is_number(self) -> bool:
        return bool(self.digits) and len(self.digits) >= 2


@dataclass
class ExtractedTable:
    rows: list[tuple[int, int]] = field(default_factory=list)  # (top, bottom)
    cols: list[tuple[int, int]] = field(default_factory=list)  # (left, right)
    cells: list[list[str]] = field(default_factory=list)       # per-row cell texts
    digit_cells: list[list[str]] = field(default_factory=list)  # per-row cell digits
    split_boxes: list[list[tuple[int, int]]] = field(default_factory=list)  # per-row split boxes


@dataclass
class ExtractedInvoice:
    source_path: str = ""
    fields: dict[str, ExtractedField] = field(default_factory=dict)
    text: str = ""
    tokens: list[OcrToken] = field(default_factory=list)
    table: ExtractedTable = field(default_factory=ExtractedTable)
    engine: str = "none"
    warnings: list[str] = field(default_factory=list)

    def confirmed_values(self) -> dict[str, str]:
        return {k: v.value for k, v in self.fields.items() if v.value}

    def numeric_tokens(self) -> list[OcrToken]:
        return [t for t in self.tokens if t.is_number]


# --------------------------------------------------------------------------
# field vocabulary (Arabic + English variants)
_LABELS = {
    "account_no": [
        r"رقم\s+(?:الحساب|الاشتراك)\s*[:\-ـ]?", r"(?:account|acc)\s*(?:no|number)?\s*[:\-]?",
        r"\baccount\s+no\.?\b",
    ],
    "subscription_no": [
        r"رقم\s+الاشتراك\s*[:\-ـ]?", r"(?:subscription|sub)\s*(?:no|number)?\s*[:\-]?",
    ],
    "meter_no": [
        r"رقم\s+(?:المقياس|العداد)\s*[:\-ـ]?", r"(?:meter|meter\s*no)\s*[:\-]?",
        r"(?:عداد|مقياس)\s*[:\-ـ]?",
    ],
    "previous_reading": [
        r"(?:القراءة\s+)?السابقة\s*(?:القراءة)?\s*[:\-ـ]?", r"(?:previous|prev\.?)\s*(?:reading|read)?\s*[:\-]?",
    ],
    "current_reading": [
        r"(?:القراءة\s+)?الحالية\s*(?:القراءة)?\s*[:\-ـ]?", r"(?:current|present)\s*(?:reading|read)?\s*[:\-]?",
        r"الحالية\s*[:\-ـ]?",
    ],
    "issue_date": [
        r"تاريخ\s+(?:الفاتورة|الإصدار|الأصدار|الاصدار)\s*[:\-ـ]?", r"(?:issue|date)\s*[:\-]?",
    ],
    "previous_read_date": [
        r"تاريخ\s+القراءة\s+السابقة\s*[:\-ـ]?", r"prev\.?\s*(?:date|read)\s*[:\-]?",
    ],
    "current_read_date": [
        r"تاريخ\s+القراءة\s+الحالية\s*[:\-ـ]?", r"curr\.?\s*(?:date|read)\s*[:\-]?",
    ],
    "previous_debt": [
        r"الدين\s+السابق\s*[:\-ـ]?", r"(?:old|previous)\s*debt\s*[:\-]?",
    ],
    "official_amount": [
        r"(?:المبلغ|أجور)\s+الحالي\s*[:\-ـ]?", r"(?:current)?\s*(?:amount|bill)\s*(?:value)?\s*[:\-]?",
        r"المجموع\s+(?:المطلوب|الفاتورة)\s*[:\-ـ]?", r"(?:total|grand)?\s*(?:total|due)\s*[:\-]?",
        r"الأجور\s*[:\-ـ]?",
    ],
    "consumption_kwh": [
        r"الاستهلاك\s*[:\-ـ]?", r"(?:consumption|kwh|usage)\s*[:\-]?",
    ],
    "rate": [
        r"سعر\s+(?:الكيلو|الوحدة)?\s*[:\-ـ]?", r"(?:rate|price|kxh)\s*[:\-]?",
    ],
    "total_due": [
        r"المجموع\s+(?:المطلوب|الفاتورة)\s*[:\-ـ]?", r"(?:grand\s*)?total\s*[:\-]?",
    ],
}

# --------------------------------------------------------------------------
# spatial anchor map — KahrabaSmart_OCR_Config.md §2–§3
# anchors are the Arabic keywords ("الكلمة المفتاحية"); the target value sits
# BELOW the anchor (+Y) and is X-aligned with its bounding box.
_ANCHORS: dict[str, tuple[str, ...]] = {
    # Zone 2 (left) — "قائمة اجور الكهرباء", accounting priority
    "account_no": ("رقم الحساب", "رقم الحاسبة"),
    "previous_reading": ("القراءة السابقة", "القراءه السابقه", "السابقة"),
    "previous_read_date": ("تاريخها", "تاريخ القراءة السابقة", "تاريخ القراءه السابقه"),
    "current_reading": ("القراءة اللاحقة", "القراءة الحالية", "القراءه اللاحقه", "القراءه الحاليه"),
    "issue_date": ("تاريخ الإصدار", "تاريخ الاصدار", "الاصدار", "تاريخ الفاتورة", "تاريخ فاتورة"),
    "official_amount": ("المبلغ الحالي", "المبلغ الحاليه", "اجور الحالية"),
    "previous_debt": ("الديون", "ديون"),
    "additional_fees": ("أجور أخرى", "اجور اخرى", "اجور اخري"),
    "total_due": ("المجموع المطلوب", "المجموع"),
    "consumption_kwh": ("الاستهلاك", "الستهلاك"),
    "rate": ("السعر", "سعر الكيلو"),
    # Zone 1 (right) — "قسيمة دفع اجور الكهرباء", documentation
    "subscription_no": ("رقم الإشتراك", "رقم الاشتراك", "رقم الأشراك"),
    "meter_no": ("رقم المقياس", "رقم العداد", "رقم المقياس", "المقياس"),
}

_ANCHOR_PRIORITY = (
    "account_no", "previous_reading", "previous_read_date", "current_reading",
    "issue_date", "official_amount", "previous_debt", "additional_fees",
    "total_due", "consumption_kwh", "rate", "subscription_no", "meter_no",
)

# expected digit lengths per config §3 (account is explicitly 10–14 digits)
_ANCHOR_LENGTHS: dict[str, tuple[int, int]] = {
    "account_no": (10, 14),
}

_ALEF_VARIANTS = str.maketrans("أإآٱ", "اااا")


def _norm_ar(text: str) -> str:
    """Loose Arabic normalisation for anchor matching (harakat, hamza forms, taa marbuta)."""
    text = text.translate(_ALEF_VARIANTS).replace("ى", "ي").replace("ة", "ه").replace("ـ", "")
    text = text.translate(str.maketrans({c: "" for c in "ًٌٍَُِّْـ"}))
    text = text.replace("ئ", "ا").replace("ؤ", "ا").replace("ء", "ا")
    return re.sub(r"\s+", " ", text).strip()


class InvoiceOcr:
    LABELS = _LABELS

    # ------------------------------------------------------------- binary
    @staticmethod
    def binary() -> str | None:
        """Locate the tesseract executable (PATH, TESSERACT_CMD, or common install dirs)."""
        candidates: list[str] = []
        found = shutil.which("tesseract")
        if found:
            candidates.append(found)
        env = os.environ.get("TESSERACT_CMD", "")
        if env:
            candidates.append(env)
        candidates.append(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        candidates.append(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe")
        candidates.append(rf"{os.environ.get('USERPROFILE', '')}\AppData\Local\Programs\Tesseract-OCR\tesseract.exe")
        for c in candidates:
            if c and os.path.isfile(c):
                return c
        return None

    @staticmethod
    def tessdata_dir() -> str | None:
        """Return a user-writable tessdata dir when one ships our bundled data."""
        candidates: list[str] = []
        env = os.environ.get("TESSDATA_PREFIX", "")
        if env:
            candidates.append(env)
        local = rf"{os.environ.get('LOCALAPPDATA', '')}\Tesseract-OCR\tessdata"
        candidates.append(local)
        for d in candidates:
            if d and os.path.isdir(d):
                return d
        return None

    @staticmethod
    def _effective_langs(pytesseract) -> list[str]:
        """Union of languages from the bundled (user) tessdata dir and the system dir."""
        langs: list[str] = []
        dirs = [InvoiceOcr.tessdata_dir()]
        binary = InvoiceOcr.binary()
        if binary:
            dirs.append(os.path.join(os.path.dirname(binary), "tessdata"))
        for d in dirs:
            if not d or not os.path.isdir(d):
                continue
            try:
                for name in os.listdir(d):
                    if name.endswith(".traineddata"):
                        langs.append(name[:-len(".traineddata")])
            except OSError:
                continue
        for cfg in (" ", ""):
            try:
                langs += pytesseract.get_languages(config=cfg)
            except Exception:
                continue
        seen: list[str] = []
        for l in langs:
            if l not in seen:
                seen.append(l)
        return seen

    @staticmethod
    def _configured() -> "module":
        import pytesseract

        binary = InvoiceOcr.binary()
        if binary:
            pytesseract.pytesseract.tesseract_cmd = binary
        return pytesseract

    @staticmethod
    def _psm_config() -> str:
        extra = ""
        tessdata = InvoiceOcr.tessdata_dir()
        if tessdata:
            extra += f" --tessdata-dir {tessdata}"
        return extra

    # ---------------------------------------------------------- preprocess
    @staticmethod
    def _load(path: str):
        from PIL import Image

        return Image.open(path).convert("L")

    @classmethod
    def _prepare(cls, path: str, scale: int = 4):
        """Load image, preprocess (upscale + contrast), return (scaled, actual_scale).

        actual_scale is the integer factor by which the image was actually resized;
        ``1`` means the image was large enough and no upscaling occurred.
        """
        pil = cls._load(path)
        scaled = cls.preprocess(pil, scale=scale)
        actual = scaled.width // pil.width if pil.width else 1
        return pil, scaled, max(actual, 1)

    @staticmethod
    def preprocess(image, scale: int = 4):
        """Grayscale + upscale + contrast stretch for better OCR."""
        from PIL import Image, ImageOps

        if scale > 1 and min(image.size) * scale < 4200:
            image = image.resize((image.width * scale, image.height * scale), Image.LANCZOS)
        return ImageOps.autocontrast(image)

    @staticmethod
    def is_available() -> bool:
        try:
            import pytesseract  # noqa: F401
            if InvoiceOcr.binary() is None:
                return False
            return len(InvoiceOcr._effective_langs(pytesseract)) > 0
        except Exception:
            return False

    # ------------------------------------------------------------- tokens
    @classmethod
    def word_tokens(cls, path: str, langs: str = "ara+eng") -> list[OcrToken]:
        """Positioned word tokens with confidence (generic + digits-only passes)."""
        pytesseract = cls._configured()
        _, scaled, actual = cls._prepare(path)
        cfg = cls._psm_config()
        out: list[OcrToken] = []

        def collect(image, lang: str, config: str):
            try:
                data = pytesseract.image_to_data(
                    image, lang=lang, config=config, output_type=pytesseract.Output.DICT)
            except Exception:
                return
            n = len(data["text"])
            for i in range(n):
                t = (data["text"][i] or "").strip()
                if not t or data["conf"][i] in ("-1", None):
                    continue
                try:
                    conf = float(data["conf"][i])
                except (TypeError, ValueError):
                    conf = 0.0
                x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
                if w <= 0 or h <= 0:
                    continue
                out.append(OcrToken(
                    text=t.replace("\u200f", "").replace("\u200e", "").strip(),
                    confidence=conf / 100.0,
                    x=x // actual, y=y // actual, w=w // actual, h=h // actual,
                ))

        collect(scaled, lang=langs, config=f"--psm 11{cfg}")
        collect(scaled, lang="eng", config=f"--psm 11{cfg} tessedit_char_whitelist=0123456789")
        return cls._dedupe_tokens(out)

    @staticmethod
    def _dedupe_tokens(tokens: list[OcrToken]) -> list[OcrToken]:
        """Merge near-duplicate token boxes keeping the highest-confidence text."""
        kept: list[OcrToken] = []
        for tok in sorted(tokens, key=lambda t: -t.confidence):
            dup = False
            for k in kept:
                if _iou((tok.x, tok.y, tok.x + tok.w, tok.y + tok.h),
                        (k.x, k.y, k.x + k.w, k.y + k.h)) > 0.55:
                    # prefer the digits version for numbers
                    if tok.is_number and not k.is_number:
                        k.text, k.confidence = tok.text, max(k.confidence, tok.confidence)
                    dup = True
                    break
            if not dup:
                kept.append(tok)
        return sorted(kept, key=lambda t: (t.y, t.x))

    # -------------------------------------------------------------- table
    @classmethod
    def detect_table(cls, path: str) -> ExtractedTable:
        """Detect grid-like rows/columns via horizontal/vertical dark lines."""
        import numpy as np

        pil = cls._load(path)
        a = np.array(pil)
        H, W = a.shape
        ink = (a < 150).astype(np.uint8)

        def dark_ratio(vals) -> float:
            if len(vals) == 0:
                return 0.0
            return float(np.count_nonzero(vals)) / len(vals)

        # horizontal (row) lines
        row_frac = [dark_ratio(ink[i, :]) for i in range(H)]
        row_lines: list[tuple[int, int]] = _group_bands(row_frac, 0.78, 2)
        # vertical (column) lines
        col_frac = [dark_ratio(ink[:, j]) for j in range(W)]
        col_lines = _group_bands(col_frac, 0.78, 2)

        rows: list[tuple[int, int]] = []
        for idx in range(len(row_lines) - 1):
            rows.append((row_lines[idx][1] + 1, row_lines[idx + 1][0] - 1))
        rows = [(t + 2, b - 2) for (t, b) in rows if b - t >= 6]

        cols: list[tuple[int, int]] = []
        for idx in range(len(col_lines) - 1):
            cols.append((col_lines[idx][1] + 1, col_lines[idx + 1][0] - 1))
        if not cols and rows:
            cols = [(0, W - 1)]
        split_boxes: list[list[tuple[int, int]]] = []
        if len(col_lines) <= 1 and rows:
            # gridless tables: split each row into cells by whitespace gaps
            split_boxes = [[box for box in cls._split_row_boxes(a, t, b)] for (t, b) in rows]
            cells, digit_cells = cls.extract_row_cells(path, rows, split_boxes)
        else:
            cells, digit_cells = cls.extract_cells(path, rows, cols)
        return ExtractedTable(rows=rows, cols=cols, cells=cells,
                              digit_cells=digit_cells, split_boxes=split_boxes)

    @staticmethod
    def _split_row_boxes(a, top: int, bottom: int,
                         min_gap: int = 14, min_w: int = 12) -> list[tuple[int, int]]:
        """Split one row band into cells using white-column gaps."""
        try:
            import numpy as np
        except ImportError:
            return [(0, a.shape[1] - 1)]
        t = max(top - 2, 0)
        b = min(bottom + 2, a.shape[0])
        reg = a[t:b, :]
        if reg.size == 0:
            return [(0, a.shape[1] - 1)]
        ink = (reg <= 155).astype(np.uint8)
        empties = ink.sum(axis=0) == 0
        gaps: list[tuple[int, int]] = []
        start = None
        for c in range(len(empties)):
            if empties[c]:
                if start is None:
                    start = c
            elif start is not None:
                if c - start >= min_gap:
                    gaps.append((start, c - 1))
                start = None
        if start is not None and len(empties) - start >= min_gap:
            gaps.append((start, len(empties) - 1))
        mids = [(g[0] + g[1]) // 2 for g in gaps]
        bounds = [0] + mids + [a.shape[1]]
        return [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)
                if bounds[i + 1] - bounds[i] >= min_w]

    @classmethod
    def extract_row_cells(cls, path: str, rows: list[tuple[int, int]],
                          boxes: list[list[tuple[int, int]]]) -> tuple[list[list[str]], list[list[str]]]:
        """OCR each gap-split cell (text pass + digits pass)."""
        from PIL import Image, ImageOps

        pil = cls._load(path)
        cell_text: list[list[str]] = []
        cell_digits: list[list[str]] = []
        pytesseract = cls._configured()
        cfg = cls._psm_config()
        for idx, (t, b) in enumerate(rows):
            row_cells: list[str] = []
            row_digits: list[str] = []
            for (l, rgt) in boxes[idx]:
                crop = pil.crop((max(l - 1, 0), max(t - 1, 0),
                                 min(rgt + 1, pil.width), min(b + 1, pil.height)))
                if crop.width < 8 or crop.height < 6:
                    row_cells.append(""); row_digits.append(""); continue
                crop = ImageOps.autocontrast(crop.resize((crop.width * 4, crop.height * 4), Image.LANCZOS))
                text = ""
                digits = ""
                try:
                    text = pytesseract.image_to_string(crop, lang="ara+eng",
                                                       config=f"--psm 7{cfg}").strip()
                except Exception:
                    text = ""
                try:
                    digits = pytesseract.image_to_string(
                        crop, lang="eng", config=f"--psm 8{cfg} tessedit_char_whitelist=0123456789").strip()
                except Exception:
                    digits = ""
                clean = cls.normalize_digits(digits)
                if len(text) < 3 and (clean or digits):
                    text = text or digits
                row_cells.append(text)
                row_digits.append(clean or digits)
            cell_text.append(row_cells)
            cell_digits.append(row_digits)
        return cell_text, cell_digits

    @classmethod
    def extract_cells(cls, path: str, rows: list[tuple[int, int]],
                      cols: list[tuple[int, int]]) -> tuple[list[list[str]], list[list[str]]]:
        """OCR each table cell (text pass + digits pass) -> (cells, digit cells)."""
        from PIL import Image, ImageOps

        if not rows:
            return [], []
        pil = cls._load(path)
        cell_text: list[list[str]] = []
        cell_digits: list[list[str]] = []
        pytesseract = cls._configured()
        cfg = cls._psm_config()
        for (t, b) in rows:
            row_cells: list[str] = []
            row_digits: list[str] = []
            for (l, r) in cols:
                l2, r2 = max(l - 1, 0), min(r + 1, pil.width)
                crop = pil.crop((l2, max(t - 1, 0), r2, min(b + 1, pil.height)))
                if crop.width < 8 or crop.height < 6:
                    row_cells.append(""); row_digits.append(""); continue
                crop = ImageOps.autocontrast(crop.resize((crop.width * 4, crop.height * 4), Image.LANCZOS))
                text = ""
                digits = ""
                try:
                    text = pytesseract.image_to_string(crop, lang="ara+eng",
                                                       config=f"--psm 7{cfg}").strip()
                except Exception:
                    text = ""
                try:
                    digits = pytesseract.image_to_string(
                        crop, lang="eng", config=f"--psm 8{cfg} tessedit_char_whitelist=0123456789").strip()
                except Exception:
                    digits = ""
                digit_clean = cls.normalize_digits(digits)
                if len(text) < 3 and digit_clean:
                    text = digits
                row_cells.append(text)
                row_digits.append(digit_clean or digits)
            cell_text.append(row_cells)
            cell_digits.append(row_digits)
        return cell_text, cell_digits

    # ------------------------------------------------------------ extract
    @classmethod
    def extract_text(cls, image_path: str, lang: str = "ara+eng") -> str:
        if InvoiceOcr.binary() is None:
            raise OcrUnavailableError(
                "ميزة الاستيراد من الصورة (OCR) غير متوفرة: يتطلب تثبيت Tesseract OCR.\n"
                "قم بتثبيته ثم أعد تشغيل البرنامج، أو أدخل القراءات يدوياً."
            )
        try:
            pytesseract = cls._configured()
        except ImportError as exc:  # pragma: no cover
            raise OcrUnavailableError(str(exc)) from exc

        langs = []
        available = cls._effective_langs(pytesseract)
        for l in lang.split("+"):
            if l in available:
                langs.append(l)
        if not langs:
            langs = [l for l in ("eng", "ara") if l in available]
        if not langs:
            return ""

        pil = cls._load(image_path)
        scaled = cls.preprocess(pil, scale=4)
        cfg = cls._psm_config()
        texts: list[str] = []
        for psm in ("3", "6"):
            try:
                texts.append(pytesseract.image_to_string(
                    scaled, lang="+".join(langs), config=f"--psm {psm}{cfg}"))
            except Exception:
                texts.append("")
        merged = "\n".join(t for t in texts if t.strip())
        # digits-only fallback pass when little text was found
        if len(merged.strip()) < 40:
            for psm in ("11",):
                try:
                    merged += "\n" + pytesseract.image_to_string(
                        scaled, lang="eng", config=f"--psm {psm}{cfg} tessedit_char_whitelist=0123456789")
                except Exception:
                    pass
        return re.sub(r"\n{2,}", "\n", merged).strip()

    @classmethod
    def extract(cls, image_path: str) -> ExtractedInvoice:
        warnings: list[str] = []
        text = cls.extract_text(image_path)
        tokens = cls.word_tokens(image_path) + cls._scan_digits(image_path)
        tokens += cls._scan_zones(image_path)
        table: ExtractedTable
        try:
            table = cls.detect_table(image_path)
            tokens += cls._tokens_from_cells(table)
            tokens += cls._scan_footer_header(image_path, table)
        except Exception as exc:
            table = ExtractedTable()
            warnings.append(f"table: {exc}")

        # cross-pass dedupe: the same number is often found by several scan
        # passes and duplicates would corrupt adjacent-digit merging
        tokens = cls._dedupe_tokens(tokens)
        formula_text = " ".join([text, " ".join(t.text for t in tokens)])
        fields = cls.parse_fields(text)
        fields["_formula_text"] = ExtractedField("_formula_text", formula_text)
        cls._anchor_extract(fields, tokens)
        cls._enhance_from_tokens(fields, tokens, warnings)

        # reading sanity: if current < previous, warn
        prev = fields.get("previous_reading", ExtractedField("", "")).value
        curr = fields.get("current_reading", ExtractedField("", "")).value
        if prev and curr:
            try:
                if int(cls.normalize_digits(curr)) < int(cls.normalize_digits(prev)):
                    warnings.append("القراءة الحالية أصغر من السابقة — راجع البيانات قبل الحفظ.")
            except ValueError:
                pass

        # verify amounts when both consumption and a rate exist
        consumption = fields.get("consumption_kwh", ExtractedField("consumption_kwh", "")).value
        amount = fields.get("official_amount", ExtractedField("official_amount", "")).value
        rate = fields.get("rate", ExtractedField("rate", "")).value
        derived = _derive_amount(consumption, amount, rate)
        if derived:
            drate, computed, raw_official = derived
            if raw_official and computed != raw_official:
                warnings.append(
                    f"الحساب المقترح: {consumption} × {drate} = {computed} "
                    "(راجع المبلغ قبل الحفظ — قد تحتاج القائمة أصلاً للقراءات).")
                f = fields["official_amount"]
                fields["official_amount"] = ExtractedField(
                    name="official_amount", value=computed,
                    confidence=min(f.confidence, 0.45), raw=f.raw or computed)
        return ExtractedInvoice(
            source_path=image_path,
            fields=fields,
            text=text,
            tokens=tokens,
            table=table,
            engine="tesseract",
            warnings=warnings,
        )

    @classmethod
    def _anchor_extract(cls, fields: dict[str, ExtractedField], tokens: list[OcrToken]) -> None:
        """Spatial anchor extraction per KahrabaSmart_OCR_Config.md §2–§3.

        Each anchor keyword's target value sits BELOW it (+Y, next row) and its
        X-center matches/overlaps the anchor's box. Empty boxes yield no value
        (not an error). Zone 2 (left, accounting) fields are filled before
        Zone 1 (right, documentation) per _ANCHOR_PRIORITY. Only fills fields
        that are still empty, keeping parse_fields/label-adjacency as fallback.
        """
        numbers = [t for t in tokens if t.is_number and t.digits]
        alpha = [t for t in tokens if not t.is_number and any(ch.isalnum() for ch in t.text)]
        lines = cls._cluster_lines(alpha)

        for field in _ANCHOR_PRIORITY:
            if fields.get(field, ExtractedField(field, "")).value:
                continue
            phrases = [k.split() for k in (_norm_ar(k) for k in _ANCHORS.get(field, ()))]
            anchors: list[tuple[int, int, int, int]] = []
            for line in lines:
                for words in phrases:
                    sel = cls._match_phrase(line, words)
                    if sel:
                        ax1 = min(t.x for t in sel)
                        ay1 = min(t.y for t in sel)
                        ax2 = max(t.x + t.w for t in sel)
                        ay2 = max(t.y + t.h for t in sel)
                        if ax2 - ax1 >= 2 and ay2 - ay1 >= 2:
                            anchors.append((ax1, ay1, ax2, ay2))
            if not anchors:
                continue
            best = cls._value_below(anchors, numbers)
            if best:
                digits, conf = best
                lo, hi = _ANCHOR_LENGTHS.get(field, (1, 40))
                if lo <= len(digits) <= hi:
                    fields[field] = ExtractedField(
                        name=field, value=digits, confidence=max(conf, 0.6), raw=digits)

    @staticmethod
    def _cluster_lines(tokens: list[OcrToken]) -> list[list[OcrToken]]:
        """Group tokens into horizontal lines by y-overlap."""
        ordered = sorted(tokens, key=lambda t: (t.y, t.x))
        lines: list[list[OcrToken]] = []
        for t in ordered:
            for line in lines:
                y1 = min(x.y for x in line)
                y2 = max(x.y + x.h for x in line)
                if y1 - t.h <= t.y <= y2 + t.h:
                    line.append(t)
                    break
            else:
                lines.append([t])
        return [sorted(line, key=lambda x: x.x) for line in lines]

    @staticmethod
    def _match_phrase(line: list[OcrToken], words: list[str]) -> list[OcrToken] | None:
        """Return the line tokens spelling a (possibly split) anchor phrase.

        Tries both reading orders so RTL Arabic (right-to-left) and LTR tokens
        both work; one merged token containing all words is also accepted.
        """
        for toks in (line, list(reversed(line))):
            used: list[OcrToken] = []
            ok = True
            for w in words:
                hit = next((t for t in toks if len(w) >= 2 and w in _norm_ar(t.text)), None)
                if hit is None:
                    ok = False
                    break
                if hit not in used:
                    used.append(hit)
            if ok:
                return used
        return None

    @staticmethod
    def _value_below(anchor_boxes: list[tuple[int, int, int, int]],
                     numbers: list[OcrToken]) -> tuple[str, float] | None:
        """Best merged number line under any anchor box — value below + X-aligned.

        Config §3–§4: nearest row wins; X-overlap ties go to the nearest
        X-center; adjacent digits within the same field are merged
        (sanitisation). Returns (digits, conf).
        """
        candidates: list[tuple[tuple[float, float, int], str, float]] = []
        for ax1, ay1, ax2, ay2 in anchor_boxes:
            a_cx = (ax1 + ax2) / 2.0
            a_bottom = ay2
            a_h = ay2 - ay1
            a_w = ax2 - ax1
            row_limit = max(a_h * 2.2, 90)
            x_limit = max(a_w, 60) + 50
            band = [n for n in numbers
                    if 0 <= (n.y - a_bottom) <= row_limit
                    and abs((n.x + n.w / 2.0) - a_cx) <= x_limit]
            if not band:
                continue
            band.sort(key=lambda n: (n.y, n.x))
            runs: list[list[OcrToken]] = []
            for n in band:
                for run in runs:
                    ref = run[-1]
                    same_line = abs(n.y - ref.y) <= max(n.h, ref.h)
                    gap = n.x - (ref.x + ref.w)
                    wpc = max(ref.w / max(len(ref.digits), 1), 1)
                    if same_line and gap <= max(wpc * 2.2, 8):
                        run.append(n)
                        break
                else:
                    runs.append([n])
            for run in runs:
                run.sort(key=lambda n: n.x)
                parts = [run[0].digits]
                for prev, n in zip(run, run[1:]):
                    nd = n.digits
                    if n.x - (prev.x + prev.w) < 0:
                        # overlapping boxes → boundary glyphs were read by both
                        # tokens; strip the duplicated prefix (largest textual
                        # match, at most 3 digits) instead of doubling them
                        for k in (3, 2, 1):
                            if 0 < k < len(nd) and parts[-1].endswith(nd[:k]):
                                nd = nd[k:]
                                break
                    parts.append(nd)
                digits = "".join(parts)
                conf = max(n.confidence for n in run)
                dy = min(abs(n.y - a_bottom) for n in run)
                cx_diff = min(abs((n.x + n.w / 2.0) - a_cx) for n in run)
                candidates.append(((dy, cx_diff, -len(digits)), digits, conf))
        if not candidates:
            return None
        candidates.sort(key=lambda c: c[0])
        return candidates[0][1], candidates[0][2]

    @classmethod
    def _scan_digits(cls, path: str) -> list[OcrToken]:
        """Multiple whole-image digits passes to catch sparse numeric clusters."""
        pytesseract = cls._configured()
        _, scaled, actual = cls._prepare(path)
        cfg = cls._psm_config()
        out: list[OcrToken] = []

        def run(image):
            texts = []
            for psm in ("11", "6"):
                try:
                    texts.append(pytesseract.image_to_data(
                        image, lang="eng",
                        config=f"--psm {psm}{cfg} tessedit_char_whitelist=0123456789",
                        output_type=pytesseract.Output.DICT))
                except Exception:
                    texts.append(None)
            for data in texts:
                if not data:
                    continue
                n = len(data["text"])
                for i in range(n):
                    t = (data["text"][i] or "").strip()
                    if not t or not t.isdigit() or len(t) < 2:
                        continue
                    try:
                        conf = float(data["conf"][i])
                    except (TypeError, ValueError):
                        conf = 0.0
                    x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
                    if w <= 0 or h <= 0:
                        continue
                    w0, h0 = w // actual, h // actual
                    if w0 > 120 or h0 > 70:
                        continue
                    out.append(OcrToken(text=t, confidence=conf / 100.0,
                                        x=x // actual, y=y // actual, w=w0, h=h0))

        run(scaled)
        return cls._dedupe_tokens(out)

    @classmethod
    def _scan_zones(cls, path: str) -> list[OcrToken]:
        """Digit scan of left/right halves of landscape receipts.

        The scanned household receipts are landscape sheets holding two
        documents side by side; whole-image passes lose half the digits, so
        each half is scanned separately and coordinates are mapped back.
        """
        pytesseract = cls._configured()
        pil = cls._load(path)
        cfg = cls._psm_config()
        if pil.width <= pil.height or pil.width < 2:
            return []
        out: list[OcrToken] = []
        mid = pil.width // 2
        for x0, x1 in ((0, mid), (mid, pil.width)):
            crop = pil.crop((x0, 0, x1, pil.height))
            if crop.width < 40 or crop.height < 20:
                continue
            scaled = cls.preprocess(crop, scale=4)
            actual = scaled.width // crop.width if crop.width else 1
            if actual < 1:
                actual = 1
            for psm in ("11", "6"):
                try:
                    data = pytesseract.image_to_data(
                        scaled, lang="eng",
                        config=f"--psm {psm}{cfg} tessedit_char_whitelist=0123456789",
                        output_type=pytesseract.Output.DICT)
                except Exception:
                    continue
                n = len(data["text"])
                for i in range(n):
                    tok = (data["text"][i] or "").strip()
                    if not tok or not tok.isdigit() or len(tok) < 2:
                        continue
                    try:
                        conf = float(data["conf"][i])
                    except (TypeError, ValueError):
                        conf = 0.0
                    x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
                    w0, h0 = w // actual, h // actual
                    if w0 <= 0 or h0 <= 0 or w0 > 200 or h0 > 80:
                        continue
                    out.append(OcrToken(text=tok, confidence=conf / 100.0,
                                        x=x0 + x // actual, y=y // actual, w=w0, h=h0))
        return cls._dedupe_tokens(out)

    @classmethod
    def _scan_footer_header(cls, path: str, table: ExtractedTable) -> list[OcrToken]:
        """Digit scan of the bands above/below the table (headers, formula line)."""
        pytesseract = cls._configured()
        pil = cls._load(path)
        cfg = cls._psm_config()
        out: list[OcrToken] = []
        bands: list[tuple[int, int]] = []
        if table.rows:
            first_top = table.rows[0][0]
            last_bottom = table.rows[-1][1]
            if first_top > 0:
                bands.append((0, max(first_top - 2, 0)))
            if last_bottom < pil.height - 1:
                bands.append((min(last_bottom + 2, pil.height - 1), pil.height))
        else:
            bands.append((0, pil.height))
        for (t, b) in bands:
            if b - t < 12:
                continue
            crop = pil.crop((0, t, pil.width, b))
            scaled = cls.preprocess(crop, scale=4)
            actual = scaled.width // crop.width if crop.width else 1
            if actual < 1:
                actual = 1
            for psm in ("11",):
                try:
                    data = pytesseract.image_to_data(
                        scaled, lang="eng",
                        config=f"--psm {psm}{cfg} tessedit_char_whitelist=0123456789",
                        output_type=pytesseract.Output.DICT)
                except Exception:
                    continue
                n = len(data["text"])
                for i in range(n):
                    tok = (data["text"][i] or "").strip()
                    if not tok or not tok.isdigit() or len(tok) < 2:
                        continue
                    try:
                        conf = float(data["conf"][i])
                    except (TypeError, ValueError):
                        conf = 0.0
                    x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
                    w0, h0 = w // actual, h // actual
                    if w0 <= 0 or h0 <= 0 or w0 > 200 or h0 > 80:
                        continue
                    out.append(OcrToken(text=tok, confidence=conf / 100.0,
                                        x=x // actual, y=t + y // actual, w=w0, h=h0))
        return cls._dedupe_tokens(out)

    @staticmethod
    def _tokens_from_cells(table: ExtractedTable) -> list[OcrToken]:
        """Synthesize positioned tokens from per-cell digit OCR."""
        tokens: list[OcrToken] = []
        if table.split_boxes:
            for r, (t, b) in enumerate(table.rows):
                for c, ((l, rgt), digit) in enumerate(zip(table.split_boxes[r],
                                                           table.digit_cells[r])):
                    d = InvoiceOcr.normalize_digits(digit)
                    if len(d) >= 2 and rgt - l <= 200 and b - t <= 90:
                        tokens.append(OcrToken(text=d, confidence=0.55,
                                               x=l, y=t, w=rgt - l, h=b - t))
            return tokens
        for r, (t, b) in enumerate(table.rows):
            for c, ((l, rgt), digit) in enumerate(zip(table.cols, table.digit_cells[r])):
                d = InvoiceOcr.normalize_digits(digit)
                if len(d) >= 2 and rgt - l <= 200:
                    tokens.append(OcrToken(text=d, confidence=0.55,
                                           x=l, y=t, w=rgt - l, h=b - t))
        return tokens

    # ------------------------------------------------------------ parsing
    @classmethod
    def normalize_digits(cls, text: str) -> str:
        text = text.translate(_DIGITS_AR)
        return re.sub(r"[^\d]", "", text)

    @classmethod
    def _clean(cls, text: str) -> str:
        return (text.replace("\u00a0", " ").replace("\u200f", "").replace("\u200e", "").replace("٠", "0")
                .replace("١", "1").replace("٢", "2").replace("٣", "3").replace("٤", "4")
                .replace("٥", "5").replace("٦", "6").replace("٧", "7").replace("٨", "8").replace("٩", "9"))

    @classmethod
    def parse_fields(cls, text: str) -> dict[str, ExtractedField]:
        """Label-adjacency regex extraction + date/reading heuristics."""
        cleaned = cls._clean(text)
        result: dict[str, ExtractedField] = {}
        number_re = r"([\d][\d,.\-ـ]+)"

        def grab(field: str, label_sets: list[str]) -> None:
            for _label_re in label_sets:
                for m in re.finditer(_label_re + r"\s*" + number_re, cleaned,
                                     re.IGNORECASE):
                    if m:
                        value = cls.normalize_digits(m.group(1))
                        result[field] = ExtractedField(
                            name=field, value=value, confidence=0.6, raw=m.group(1))
                        return
            result[field] = ExtractedField(name=field, value="", confidence=0.0, raw="")

        for key, labels in cls.LABELS.items():
            grab(key, labels)

        cls._heuristic_dates(cleaned, result)
        return result

    @staticmethod
    def _heuristic_dates(text: str, result: dict[str, ExtractedField]) -> None:
        """Fill *_date fields from naked 6-8 digit date tokens."""
        if any(f in result and result[f].value for f in
               ("issue_date", "previous_read_date", "current_read_date")):
            return
        dates = []
        for m in re.finditer(r"(?<!\d)(\d{1,4}[/\-.]\d{1,2}[/\-.]\d{1,4}|\d{8})(?!\d)", text):
            raw = m.group(1)
            parsed = _parse_date(raw)
            if parsed:
                dates.append((raw, parsed))
        if not dates:
            return
        if "issue_date" not in result or not result["issue_date"].value:
            result["issue_date"] = ExtractedField("issue_date", dates[0][0], 0.55, dates[0][0])
        if len(dates) >= 2:
            if "previous_read_date" not in result or not result["previous_read_date"].value:
                result["previous_read_date"] = ExtractedField(
                    "previous_read_date", dates[0][0], 0.5, dates[0][0])
            if "current_read_date" not in result or not result["current_read_date"].value:
                result["current_read_date"] = ExtractedField(
                    "current_read_date", dates[1][0], 0.5, dates[1][0])

    @classmethod
    def _enhance_from_tokens(cls, fields: dict[str, ExtractedField],
                             tokens: list[OcrToken], warnings: list[str] | None = None) -> None:
        """Fill fields from positioned tokens when the label-regex found nothing."""
        warnings = warnings if warnings is not None else []
        numbers = [t for t in tokens if t.is_number]

        def fill(name: str, value: str, conf: float = 0.55) -> None:
            f = fields.get(name, ExtractedField(name, ""))
            if not f.value and value:
                fields[name] = ExtractedField(name=name, value=value, confidence=conf, raw=value)

        # ------ dates: 8-digit YYYYMMDD tokens
        date_tokens = [t for t in numbers if len(t.digits) == 8 and t.digits[:2] in ("19", "20")]
        filled_any_date = any(f.value for k, f in fields.items() if k.endswith("_date"))
        if not filled_any_date and date_tokens:
            d0 = date_tokens[0].digits
            if not fields.get("issue_date", ExtractedField("issue_date", "")).value:
                fields["issue_date"] = ExtractedField("issue_date", d0, 0.7, d0)
                if len(date_tokens) >= 2:
                    fill("previous_read_date", date_tokens[1].digits, 0.5)

        # ------ consumption from an explicit "rate * consumption" formula
        consumption = fields.get("consumption_kwh", ExtractedField("consumption_kwh", "")).value
        formula = re.findall(r"(\d{1,3})\s*[x*×]\s*(\d{3,6})", fields.get("_formula_text", ExtractedField("_formula_text", "")).value or "")
        if not consumption:
            for (r, c) in formula:
                if len(c) >= 3:
                    fill("rate", r, 0.7)
                    fill("consumption_kwh", c, 0.7)
                    consumption = c
                    break

        prev = fields.get("previous_reading", ExtractedField("previous_reading", "")).value
        curr = fields.get("current_reading", ExtractedField("current_reading", "")).value

        # ----- readings: prefer label-adjacency ("القراءة السابقة 13578")
        if not (prev and curr):
            numbers_by_line = [(t, int(t.digits)) for t in numbers
                               if len(t.digits) in (4, 5, 6) and not (1900 <= int(t.digits) <= 2100)]
            prev_lbls = [t for t in tokens if _is_reading_label(t, "prev")]
            curr_lbls = [t for t in tokens if _is_reading_label(t, "curr")]

            def nearest(labels) -> OcrToken | None:
                best: tuple[tuple, OcrToken] | None = None
                for lbl in labels:
                    for num, _ in numbers_by_line:
                        dy = abs(num.y - lbl.y)
                        if dy > max(num.h, lbl.h) * 2.2:
                            continue
                        score = (dy / max(num.h, lbl.h, 1), abs(num.x - lbl.x), -num.confidence)
                        if best is None or score < best[0]:
                            best = (score, num)
                return best[1] if best else None

            if not prev and prev_lbls:
                t = nearest(prev_lbls)
                if t is not None:
                    fill("previous_reading", t.digits, 0.6)
            if not curr and curr_lbls:
                t = nearest(curr_lbls)
                if t is not None:
                    fill("current_reading", t.digits, 0.6)
            prev = fields.get("previous_reading", ExtractedField("previous_reading", "")).value
            curr = fields.get("current_reading", ExtractedField("current_reading", "")).value

        # readings from a pair of close 4-6 digit numbers on the same line
        if not (prev and curr):
            nums = [n for n in numbers if n.h >= 24]
            if nums:
                xs = sorted(n.x for n in nums)
                med_x = xs[len(xs) // 2]
            else:
                med_x = 0
            candidates = [t for t in nums
                          if len(t.digits) in (4, 5, 6) and t.x <= med_x and 2 <= t.h <= 90
                          and not (1900 <= int(t.digits) <= 2100)]
            best: tuple[float, OcrToken, OcrToken] | None = None
            for a in candidates:
                for b in candidates:
                    if a is b:
                        continue
                    ia, ib = int(a.digits), int(b.digits)
                    if not (0 < ib - ia < 100000):
                        continue
                    dy = abs(a.y - b.y)
                    if dy > max(a.h, b.h) * 1.6:
                        continue
                    if best is None or dy < best[0]:
                        best = (dy, a, b)
            if best:
                _, prev_tok, curr_tok = best
                fill("previous_reading", prev_tok.digits, 0.55)
                fill("current_reading", curr_tok.digits, 0.6)
                prev, curr = prev_tok.digits, curr_tok.digits

        # consumption fallback from reading difference
        if not consumption and prev and curr:
            try:
                diff = int(curr) - int(prev)
                if 0 < diff < 1000000:
                    fill("consumption_kwh", str(diff), 0.85)
                    consumption = str(diff)
            except ValueError:
                pass

        # official amount: prefer a 5-6 digit token on the right/lower part of the document
        used = {f.value for f in (fields.get("previous_reading"), fields.get("current_reading"))
                if f.value}
        if not fields.get("official_amount", ExtractedField("official_amount", "")).value:
            cand_5_6 = [t for t in numbers if len(t.digits) in (5, 6)
                        and t.digits not in used and t.confidence >= 0.4]
            if cand_5_6:
                xs = sorted(t.x for t in cand_5_6)
                ys = sorted(t.y for t in cand_5_6)
                med_x = xs[len(xs) // 2]
                med_y = ys[len(ys) // 2]
                picked = sorted(cand_5_6,
                                key=lambda t: (0 if t.x >= med_x else 1,
                                               0 if t.y >= med_y else 1,
                                               -t.confidence))[0]
                fill("official_amount", picked.digits, 0.5)


# ------------------------------------------------------------------ helpers
def _group_bands(fracs: list[float], threshold: float, max_gap: int) -> list[tuple[int, int]]:
    bands: list[tuple[int, int]] = []
    start: int | None = None
    for i, f in enumerate(fracs):
        active = f >= threshold
        if active and start is None:
            start = i
        elif not active and start is not None:
            if i - start <= max_gap:
                continue  # extend through tiny gaps
            bands.append((start, i - 1))
            start = None
    if start is not None:
        bands.append((start, len(fracs) - 1))
    return bands


def _iou(box_a: tuple[int, int, int, int], box_b: tuple[int, int, int, int]) -> float:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / union if union else 0.0


def _parse_date(raw: str) -> date | None:
    raw = raw.replace("-", "/")
    if "/" in raw:
        parts = raw.split("/")
        if len(parts) != 3:
            return None
        a, b, c = parts
        if not all(p.isdigit() for p in parts):
            return None
        if len(a) == 4:
            y, m, d = int(a), int(b), int(c)
        elif len(c) == 4:
            d, m, y = int(a), int(b), int(c)
        else:
            return None
        try:
            d = date(y, m, d)
        except ValueError:
            return None
        return d if 1950 <= d.year <= 2099 else None
    if len(raw) == 8 and raw.isdigit():
        for fmt in ("%Y%m%d", "%d%m%Y"):
            try:
                d = datetime.strptime(raw, fmt).date()
            except ValueError:
                continue
            if 1950 <= d.year <= 2099:
                return d
        return None
    return None


def _derive_amount(consumption: str, amount: str, rate: str = "") -> tuple[str, str, str] | None:
    """Return (rate, computed_amount, raw_official_amount) when an arithmetic
    cross-check is possible, else None. `computed` may correct a mistyped OCR digit."""
    if not consumption:
        return None
    try:
        cons = int(consumption)
    except ValueError:
        return None
    if cons <= 0:
        return None
    raw = InvoiceOcr.normalize_digits(amount)
    if rate:
        try:
            r = int(rate)
        except ValueError:
            r = 0
        if r > 0:
            return str(r), str(cons * r), raw
    if raw:
        try:
            amt = int(raw)
        except ValueError:
            return None
        if amt % cons == 0:
            r = amt // cons
            if 0 < r <= 500:
                return str(r), str(amt), raw
    return None