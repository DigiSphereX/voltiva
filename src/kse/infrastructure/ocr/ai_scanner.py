"""AI invoice scanning — read a bill photo with a vision model.

Two engines are offered by the program: a built-in free service (only a free
API key is needed) and a custom OpenAI-compatible endpoint. The offline
Tesseract reader stays available as the local engine and as the automatic
fallback, so scanning never depends on the network alone.

The image is sent as a base64 data URL and the model is asked for strict JSON;
the reply is mapped onto :class:`ExtractedInvoice`, which the import dialog
already knows how to apply.
"""
from __future__ import annotations

import base64
import io
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from ...domain.errors import OcrUnavailableError
from .invoice_ocr import ExtractedField, ExtractedInvoice, InvoiceOcr, OcrToken

MODE_AUTO = "auto"
MODE_CUSTOM = "custom"
MODE_LOCAL = "local"
MODES = (MODE_AUTO, MODE_CUSTOM, MODE_LOCAL)

AUTO_ENDPOINT = "https://gen.pollinations.ai/v1/chat/completions"
AUTO_MODEL = "openai"
AUTO_KEY_URL = "https://enter.pollinations.ai/keys"
DEFAULT_TIMEOUT = 60

_SETTING_KEYS = (
    ("mode", "ai_scan_mode"),
    ("url", "ai_scan_url"),
    ("api_key", "ai_scan_key"),
    ("model", "ai_scan_model"),
    ("timeout", "ai_scan_timeout"),
)

_FIELDS = (
    "account_no", "subscription_no", "subscriber_name", "meter_no",
    "previous_reading", "current_reading", "multiplier", "consumption_kwh",
    "official_amount", "issue_date", "previous_read_date", "current_read_date",
)

_DATE_KEYS = {"issue_date", "previous_read_date", "current_read_date"}
_INT_KEYS = {
    "account_no", "subscription_no", "meter_no",
    "previous_reading", "current_reading", "consumption_kwh", "multiplier",
}
_NUMERIC_KEYS = _INT_KEYS | {"official_amount"}

_ALIASES = {
    "account": "account_no", "account_number": "account_no",
    "account_id": "account_no", "حساب": "account_no", "رقم_الحساب": "account_no",
    "subscription": "subscription_no", "subscription_number": "subscription_no",
    "رقم_الاشتراك": "subscription_no",
    "name": "subscriber_name", "subscriber": "subscriber_name",
    "customer_name": "subscriber_name", "اسم_المشترك": "subscriber_name",
    "meter": "meter_no", "meter_number": "meter_no", "meter_id": "meter_no",
    "رقم_العداد": "meter_no", "رقم_المقياس": "meter_no",
    "prev_reading": "previous_reading", "previous_read": "previous_reading",
    "reading_previous": "previous_reading", "القراءة_السابقة": "previous_reading",
    "curr_reading": "current_reading", "current_read": "current_reading",
    "reading_current": "current_reading", "القراءة_الحالية": "current_reading",
    "consumption": "consumption_kwh", "usage": "consumption_kwh",
    "الاستهلاك": "consumption_kwh",
    "amount": "official_amount", "total": "official_amount",
    "total_due": "official_amount", "current_amount": "official_amount",
    "المبلغ": "official_amount", "المجموع": "official_amount",
    "date": "issue_date", "bill_date": "issue_date", "تاريخ_الإصدار": "issue_date",
    "prev_date": "previous_read_date", "previous_date": "previous_read_date",
    "تاريخ_القراءة_السابقة": "previous_read_date",
    "curr_date": "current_read_date", "current_date": "current_read_date",
    "تاريخ_القراءة_الحالية": "current_read_date",
    "meter_multiplier": "multiplier", "factor": "multiplier", "المعامل": "multiplier",
}

_SYSTEM_PROMPT = (
    "You are a precise OCR assistant for electricity bills, including Arabic "
    "handwritten and printed bills. Read the attached image and return ONLY one "
    "JSON object. Use these keys exactly: "
    + ", ".join(_FIELDS)
    + ". Rules: use null when a value is not visible; never invent or guess a "
    "value; write numbers in Western digits (0-9) without thousands separators; "
    "write dates as YYYY-MM-DD; official_amount is the current bill amount only; "
    "consumption_kwh is the consumed kilowatt-hours; previous_reading and "
    "current_reading are meter readings; multiplier is the meter factor (1 when "
    "not shown). Return the JSON object only, with no explanation and no markdown."
)


@dataclass(frozen=True)
class AiScanConfig:
    """Persisted AI scanning preferences (Settings → AI image scanning)."""

    mode: str = MODE_AUTO
    url: str = ""
    api_key: str = ""
    model: str = ""
    timeout: int = DEFAULT_TIMEOUT

    @classmethod
    def load(cls, repo) -> "AiScanConfig":
        def read(key: str, default: str = "") -> str:
            try:
                return repo.get(key, default)
            except Exception:
                return default

        values = {name: read(key) for name, key in _SETTING_KEYS}
        mode = values["mode"] if values["mode"] in MODES else MODE_AUTO
        try:
            timeout = int(values["timeout"] or DEFAULT_TIMEOUT)
        except ValueError:
            timeout = DEFAULT_TIMEOUT
        timeout = min(max(timeout, 10), 300)
        return cls(mode=mode, url=values["url"], api_key=values["api_key"],
                   model=values["model"], timeout=timeout)

    def save(self, repo) -> None:
        for name, key in _SETTING_KEYS:
            value = getattr(self, name)
            repo.set(key, "" if value is None else str(value))

    # ---- derived values ------------------------------------------------
    def endpoint(self) -> str:
        """Chat-completions URL for the selected engine (empty for local)."""
        if self.mode == MODE_LOCAL:
            return ""
        if self.mode == MODE_AUTO:
            return AUTO_ENDPOINT
        return _chat_url(self.url)

    def effective_model(self) -> str:
        model = self.model.strip()
        if model:
            return model
        return AUTO_MODEL if self.mode == MODE_AUTO else "gpt-4o-mini"

    def is_ready(self) -> bool:
        if self.mode == MODE_LOCAL:
            return InvoiceOcr.is_available()
        if self.mode == MODE_CUSTOM:
            return bool(self.endpoint())
        return True  # automatic still falls back to the local reader

    def engine_key(self) -> str:
        return {
            MODE_AUTO: "ocr_engine_auto",
            MODE_CUSTOM: "ocr_engine_custom",
            MODE_LOCAL: "ocr_engine_local",
        }[self.mode]


def _chat_url(url: str) -> str:
    """Accept a base URL, a /v1 URL or a full chat-completions URL."""
    url = url.strip().rstrip("/")
    if not url:
        return ""
    if not re.match(r"^https?://", url, re.IGNORECASE):
        host = url.split("/")[0].lower()
        scheme = "http" if host.startswith(
            ("localhost", "127.0.0.1", "0.0.0.0", "[::1]")) else "https"
        url = f"{scheme}://{url}"
    low = url.lower()
    if low.endswith("/chat/completions") or low.endswith("/openai"):
        return url
    if low.endswith("/v1"):
        return url + "/chat/completions"
    return url + "/v1/chat/completions"


def _image_data_url(path: str) -> str:
    try:
        from PIL import Image, ImageOps

        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
            img.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=88, optimize=True)
    except Exception as exc:
        raise OcrUnavailableError(f"image: {exc}") from exc
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _message_text(body: dict) -> str:
    choices = body.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content", choices[0].get("text", ""))
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                parts.append(str(part.get("text", "")))
            else:
                parts.append(str(part))
        content = "".join(parts)
    return str(content or "")


def _json_object(text: str) -> dict:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise OcrUnavailableError("ai-json: the reply did not contain a JSON object")
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise OcrUnavailableError(f"ai-json: {exc}") from exc
    if not isinstance(data, dict):
        raise OcrUnavailableError("ai-json: expected a JSON object")
    return data


def _iso_digits(text: str) -> str:
    """Turn 2024-03-15 / 15/03/2024 / 20240315 into YYYYMMDD."""
    groups = re.findall(r"\d+", text)
    if len(groups) == 1:
        return groups[0] if len(groups[0]) == 8 else ""
    if len(groups) >= 3:
        year, month, day = groups[0], groups[1], groups[2]
        if len(year) != 4:
            year, month, day = groups[2], groups[1], groups[0]
        if len(year) == 4:
            return f"{year}{month.zfill(2)}{day.zfill(2)}"
    return ""


def _clean_value(key: str, value) -> str:
    if value is None or isinstance(value, (dict, list, bool)):
        return ""
    text = str(value).strip()
    if not text or text.lower() in ("null", "none", "n/a", "-", "غير_متوفر"):
        return ""
    text = InvoiceOcr._clean(text)
    if key in _DATE_KEYS:
        return _iso_digits(text)
    if key in _INT_KEYS:
        return re.sub(r"\D", "", text)
    if key == "official_amount":
        text = text.replace("٬", "").replace(",", "").replace("٫", ".")
        match = re.search(r"\d+(?:\.\d+)?", text)
        if not match:
            return ""
        number = match.group(0)
        if "." in number:
            number = number.rstrip("0").rstrip(".")
        return number
    return re.sub(r"\s+", " ", text).strip()


def fields_from_json(data: dict) -> dict[str, ExtractedField]:
    fields: dict[str, ExtractedField] = {}
    for raw_key, raw_value in data.items():
        key = str(raw_key).strip().lower().replace(" ", "_").replace("-", "_")
        key = _ALIASES.get(key, key)
        if key not in _FIELDS:
            continue
        value = _clean_value(key, raw_value)
        if value:
            fields[key] = ExtractedField(
                name=key, value=value, confidence=0.9, raw=str(raw_value))
    return fields


class AiScanner:
    """OpenAI-compatible vision client (automatic free service or custom URL)."""

    @staticmethod
    def payload(path: str, cfg: AiScanConfig) -> dict:
        return {
            "model": cfg.effective_model(),
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "text",
                     "text": "Read this electricity bill and return the JSON object."},
                    {"type": "image_url",
                     "image_url": {"url": _image_data_url(path)}},
                ]},
            ],
            "temperature": 0,
            "max_tokens": 800,
        }

    @staticmethod
    def _post(cfg: AiScanConfig, payload: dict) -> dict:
        request = urllib.request.Request(
            cfg.endpoint(),
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                **({"Authorization": f"Bearer {cfg.api_key.strip()}"}
                   if cfg.api_key.strip() else {}),
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=cfg.timeout) as response:
                raw = response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise OcrUnavailableError(f"ai-http {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise OcrUnavailableError(f"ai-network: {exc}") from exc
        try:
            body = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OcrUnavailableError(f"ai-json: {raw[:300]}") from exc
        if not isinstance(body, dict):
            raise OcrUnavailableError("ai-json: unexpected response")
        if body.get("error"):
            error = body["error"]
            message = error.get("message") if isinstance(error, dict) else error
            raise OcrUnavailableError(f"ai-error: {message}")
        return body

    @classmethod
    def scan(cls, path: str, cfg: AiScanConfig) -> ExtractedInvoice:
        if not cfg.endpoint():
            raise OcrUnavailableError("ai-config: the custom endpoint URL is empty")
        body = cls._post(cfg, cls.payload(path, cfg))
        text = _message_text(body)
        if not text.strip():
            raise OcrUnavailableError("ai-empty: the model returned no text")
        fields = fields_from_json(_json_object(text))
        tokens = [
            OcrToken(text=field.value, confidence=field.confidence)
            for key, field in fields.items() if key in _NUMERIC_KEYS
        ]
        summary = "\n".join(f"{key}: {field.value}" for key, field in fields.items())
        return ExtractedInvoice(
            source_path=path,
            fields=fields,
            text=summary,
            tokens=tokens,
            engine="ai-auto" if cfg.mode == MODE_AUTO else "ai-custom",
        )

    @classmethod
    def ping(cls, cfg: AiScanConfig) -> str:
        """Send a tiny generated image to verify URL, key, model and vision support."""
        if not cfg.endpoint():
            raise OcrUnavailableError("ai-config: the custom endpoint URL is empty")
        try:
            from PIL import Image, ImageDraw

            image = Image.new("RGB", (96, 96), "white")
            ImageDraw.Draw(image).text((38, 30), "7", fill="black")
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=90)
        except Exception as exc:
            raise OcrUnavailableError(f"image: {exc}") from exc
        data_url = "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
        payload = {
            "model": cfg.effective_model(),
            "messages": [
                {"role": "system", "content": "Answer with one short line only."},
                {"role": "user", "content": [
                    {"type": "text", "text": "What digit is shown in the image?"},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ]},
            ],
            "temperature": 0,
            "max_tokens": 20,
        }
        text = _message_text(cls._post(cfg, payload)).strip()
        if not text:
            raise OcrUnavailableError("ai-empty: the model returned no text")
        return re.sub(r"\s+", " ", text)[:60]


def scan_invoice(path: str, cfg: AiScanConfig | None = None) -> ExtractedInvoice:
    """Scan with the configured engine, falling back to local OCR in automatic mode."""
    cfg = cfg or AiScanConfig()
    if cfg.mode == MODE_LOCAL:
        if not InvoiceOcr.is_available():
            raise OcrUnavailableError("local: Tesseract OCR is not installed")
        return InvoiceOcr.extract(path)
    if cfg.mode == MODE_CUSTOM:
        if not cfg.endpoint():
            raise OcrUnavailableError("ai-config: the custom endpoint URL is empty")
        return AiScanner.scan(path, cfg)

    ai_error: OcrUnavailableError | None = None
    if cfg.api_key.strip():
        try:
            return AiScanner.scan(path, cfg)
        except OcrUnavailableError as exc:
            ai_error = exc
    else:
        ai_error = OcrUnavailableError(
            "ai-key: the automatic engine needs a free API key in Settings")
    if InvoiceOcr.is_available():
        result = InvoiceOcr.extract(path)
        result.engine = "tesseract-fallback"
        return result
    raise ai_error
