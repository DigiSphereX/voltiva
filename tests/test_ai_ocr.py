"""AI scanning: configuration, OpenAI-compatible payloads, JSON mapping and fallback."""
from __future__ import annotations

import io
import json
import urllib.error

import pytest

from kse.domain.errors import OcrUnavailableError
from kse.infrastructure.ocr import ai_scanner
from kse.infrastructure.ocr.ai_scanner import (
    AUTO_ENDPOINT, AUTO_MODEL, MODE_AUTO, MODE_CUSTOM, MODE_LOCAL,
    AiScanConfig, AiScanner, _json_object, fields_from_json, scan_invoice,
)
from kse.infrastructure.ocr.invoice_ocr import ExtractedField, ExtractedInvoice, InvoiceOcr


class _Repo:
    def __init__(self, data=None):
        self.data = dict(data or {})

    def get(self, key, default=""):
        return self.data.get(key, default)

    def set(self, key, value, source=None):
        self.data[key] = value


class _Response:
    def __init__(self, body: dict):
        self._body = json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


def _reply(content: str) -> _Response:
    return _Response({"choices": [{"message": {"role": "assistant", "content": content}}]})


def _image(tmp_path):
    from PIL import Image

    path = tmp_path / "bill.png"
    Image.new("RGB", (32, 32), "white").save(path)
    return str(path)


def test_config_defaults_and_roundtrip():
    repo = _Repo()
    cfg = AiScanConfig.load(repo)
    assert cfg.mode == MODE_AUTO and cfg.timeout == 60
    assert cfg.endpoint() == AUTO_ENDPOINT and cfg.effective_model() == AUTO_MODEL

    chosen = AiScanConfig(mode=MODE_CUSTOM, url="https://api.example.com/v1",
                          api_key="k-1", model="vision-x", timeout=45)
    chosen.save(repo)
    assert AiScanConfig.load(repo) == chosen


def test_config_load_ignores_invalid_mode_and_clamps_timeout():
    cfg = AiScanConfig.load(_Repo({"ai_scan_mode": "bogus", "ai_scan_timeout": "9999"}))
    assert cfg.mode == MODE_AUTO and cfg.timeout == 300
    cfg = AiScanConfig.load(_Repo({"ai_scan_mode": "custom", "ai_scan_timeout": "x"}))
    assert cfg.mode == MODE_CUSTOM and cfg.timeout == 60


def test_endpoint_normalization_accepts_base_v1_and_full_urls():
    assert AiScanConfig(mode=MODE_CUSTOM, url="localhost:11434").endpoint() == \
        "http://localhost:11434/v1/chat/completions"
    assert AiScanConfig(mode=MODE_CUSTOM, url="https://host/v1").endpoint() == \
        "https://host/v1/chat/completions"
    assert AiScanConfig(mode=MODE_CUSTOM,
                        url="https://host/v1/chat/completions").endpoint() == \
        "https://host/v1/chat/completions"
    assert AiScanConfig(mode=MODE_CUSTOM, url="https://text.host/openai").endpoint() == \
        "https://text.host/openai"
    assert AiScanConfig(mode=MODE_CUSTOM, url="  ").endpoint() == ""
    assert AiScanConfig(mode=MODE_LOCAL, url="https://host/v1").endpoint() == ""


def test_fields_from_json_maps_aliases_and_normalizes_values():
    fields = fields_from_json({
        "Account Number": "١٢٣٤",
        "رقم الاشتراك": "sub-77",
        "subscriber_name": "  علي حسن ",
        "Previous Reading": "13,578",
        "current_reading": 17162,
        "المبلغ": "٥٧٬٣٤٤",
        "تاريخ الإصدار": "15/03/2024",
        "previous_read_date": "2024-02-01",
        "multiplier": None,
        "unknown_key": "ignored",
    })
    assert fields["account_no"].value == "1234"
    assert fields["subscription_no"].value == "77"
    assert fields["subscriber_name"].value == "علي حسن"
    assert fields["previous_reading"].value == "13578"
    assert fields["current_reading"].value == "17162"
    assert fields["official_amount"].value == "57344"
    assert fields["issue_date"].value == "20240315"
    assert fields["previous_read_date"].value == "20240201"
    assert "multiplier" not in fields and "unknown_key" not in fields
    assert fields["account_no"].confidence == 0.9


def test_json_object_accepts_fences_and_surrounding_prose():
    assert _json_object('Here you go:\n```json\n{"account_no": "1"}\n```') == {"account_no": "1"}
    with pytest.raises(OcrUnavailableError):
        _json_object("no object here")


def test_scan_posts_openai_compatible_payload(monkeypatch, tmp_path):
    seen = {}

    def fake_urlopen(request, timeout=None):
        seen["url"] = request.full_url
        seen["auth"] = request.get_header("Authorization")
        seen["body"] = json.loads(request.data.decode("utf-8"))
        seen["timeout"] = timeout
        return _reply('```json\n{"account_no":"24608","official_amount":"57,344",'
                      '"issue_date":"2024-03-15"}\n```')

    monkeypatch.setattr(ai_scanner.urllib.request, "urlopen", fake_urlopen)
    cfg = AiScanConfig(mode=MODE_CUSTOM, url="https://api.example.com/v1",
                       api_key="secret", model="vision-x", timeout=45)
    result = AiScanner.scan(_image(tmp_path), cfg)

    assert seen["url"] == "https://api.example.com/v1/chat/completions"
    assert seen["auth"] == "Bearer secret"
    assert seen["timeout"] == 45
    assert seen["body"]["model"] == "vision-x"
    assert seen["body"]["temperature"] == 0
    user_parts = seen["body"]["messages"][1]["content"]
    assert user_parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert result.engine == "ai-custom"
    assert result.fields["official_amount"].value == "57344"
    assert result.fields["issue_date"].value == "20240315"
    assert {t.digits for t in result.tokens} >= {"24608", "57344"}


def test_scan_reports_http_errors(monkeypatch, tmp_path):
    def unauthorized(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url, 401, "Unauthorized", {},
            io.BytesIO(b'{"error":{"message":"invalid key"}}'))

    monkeypatch.setattr(ai_scanner.urllib.request, "urlopen", unauthorized)
    cfg = AiScanConfig(mode=MODE_CUSTOM, url="https://api.example.com", api_key="bad")
    with pytest.raises(OcrUnavailableError) as info:
        AiScanner.scan(_image(tmp_path), cfg)
    assert "401" in str(info.value) and "invalid key" in str(info.value)


def test_custom_mode_requires_a_url(tmp_path):
    with pytest.raises(OcrUnavailableError):
        scan_invoice(_image(tmp_path), AiScanConfig(mode=MODE_CUSTOM, url=""))


def test_auto_mode_without_key_falls_back_to_local_reader(monkeypatch, tmp_path):
    monkeypatch.setattr(InvoiceOcr, "is_available", classmethod(lambda cls: True))
    monkeypatch.setattr(
        InvoiceOcr, "extract",
        classmethod(lambda cls, path: ExtractedInvoice(engine="tesseract")))
    monkeypatch.setattr(
        ai_scanner.urllib.request, "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("network must not be used")))

    result = scan_invoice(_image(tmp_path), AiScanConfig(mode=MODE_AUTO, api_key=""))
    assert result.engine == "tesseract-fallback"


def test_auto_mode_without_key_and_without_local_reader_reports_the_key(monkeypatch, tmp_path):
    monkeypatch.setattr(InvoiceOcr, "is_available", classmethod(lambda cls: False))
    with pytest.raises(OcrUnavailableError) as info:
        scan_invoice(_image(tmp_path), AiScanConfig(mode=MODE_AUTO, api_key=""))
    assert "free API key" in str(info.value)


def test_auto_mode_with_key_uses_the_builtin_endpoint(monkeypatch, tmp_path):
    seen = {}

    def fake_urlopen(request, timeout=None):
        seen["url"] = request.full_url
        seen["body"] = json.loads(request.data.decode("utf-8"))
        return _reply('{"account_no": "1", "consumption_kwh": "12"}')

    monkeypatch.setattr(ai_scanner.urllib.request, "urlopen", fake_urlopen)
    result = scan_invoice(
        _image(tmp_path), AiScanConfig(mode=MODE_AUTO, api_key="free-key"))
    assert seen["url"] == AUTO_ENDPOINT
    assert seen["body"]["model"] == AUTO_MODEL
    assert result.engine == "ai-auto"
    assert result.fields["consumption_kwh"].value == "12"


def test_ping_verifies_the_endpoint_with_an_image(monkeypatch):
    seen = {}

    def fake_urlopen(request, timeout=None):
        seen["body"] = json.loads(request.data.decode("utf-8"))
        return _reply("7")

    monkeypatch.setattr(ai_scanner.urllib.request, "urlopen", fake_urlopen)
    assert AiScanner.ping(AiScanConfig(mode=MODE_CUSTOM, url="https://host/v1",
                                       api_key="k")) == "7"
    parts = seen["body"]["messages"][1]["content"]
    assert parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_ai_labels_exist_in_every_language():
    from kse.presentation import i18n

    keys = set(i18n._AI_STRINGS["en"])
    for lang in i18n.LANGS:
        missing = keys - set(i18n._STRINGS[lang])
        assert not missing, (lang, missing)
        for mode in (MODE_AUTO, MODE_CUSTOM, MODE_LOCAL):
            assert AiScanConfig(mode=mode).engine_key() in i18n._STRINGS[lang], (lang, mode)
