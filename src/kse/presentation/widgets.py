from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from ..domain.money import Money, fmt_quantity

_MONEY_LANG = "en"


def set_money_lang(lang: str) -> None:
    """Switch number/currency formatting style.

    "ar" → Arabic-Indic digits + "د.ع"; anything else → Western digits + ISO code.
    """
    global _MONEY_LANG
    _MONEY_LANG = "ar" if lang == "ar" else "en"


def is_arabic_money() -> bool:
    """True when Arabic-Indic digits + "د.ع" are currently active."""
    return _MONEY_LANG == "ar"


def digits(text) -> str:
    """Render a numeric string per the active digit style (Arabic-Indic vs Western)."""
    if _MONEY_LANG != "ar":
        return str(text)
    from ..domain.money import arabic_digits
    return arabic_digits(str(text))


def currency_label() -> str:
    """The display symbol: Arabic "د.ع" in Arabic style, else the ISO code (e.g. IQD)."""
    if _MONEY_LANG == "ar":
        from ..domain.money import CURRENCY_AR
        return CURRENCY_AR
    from .currencies import get_currency_code
    return get_currency_code()


def qty_display(value, unit: str = "") -> str:
    """Format a quantity with grouping, in the active digit style."""
    rendered = digits(fmt_quantity(value))
    return f"{rendered} {unit}".strip()


def caption(label: str) -> QLabel:
    lbl = QLabel(label)
    lbl.setObjectName("StepTitle")
    return lbl


def muted(label: str) -> QLabel:
    lbl = QLabel(label)
    lbl.setObjectName("Muted")
    return lbl


def error_label() -> QLabel:
    lbl = QLabel("")
    lbl.setObjectName("Error")
    lbl.setVisible(False)
    lbl.setWordWrap(True)
    return lbl


def success_label() -> QLabel:
    lbl = QLabel("")
    lbl.setObjectName("Success")
    lbl.setVisible(False)
    lbl.setWordWrap(True)
    return lbl


def primary_button(text: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("Primary")
    return btn


def danger_button(text: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("Danger")
    return btn


def ghost_button(text: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("Ghost")
    return btn


def small_button(text: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("Small")
    return btn


def danger_small_button(text: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("DangerSmall")
    return btn


class Section(QFrame):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.title_lbl = QLabel(title)
        self.title_lbl.setObjectName("CardTitle")
        self.body = QVBoxLayout()
        self.body.setContentsMargins(16, 16, 16, 16)
        self.body.setSpacing(10)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.title_lbl)
        outer.addSpacing(8)
        outer.addLayout(self.body)

    def add_layout(self, layout) -> None:
        self.body.addLayout(layout)

    def add_widget(self, widget: QWidget) -> None:
        self.body.addWidget(widget)

    def add_spacing(self, px: int) -> None:
        self.body.addSpacing(px)


def field_row(label: str, widget: QWidget, label_width: int = 180) -> QHBoxLayout:
    row = QHBoxLayout()
    lbl = QLabel(label)
    lbl.setMinimumWidth(label_width)
    row.addWidget(lbl, 0, Qt.AlignmentFlag.AlignLeft)
    row.addWidget(widget, 1)
    return row


def money_display(value: Money) -> str:
    if _MONEY_LANG == "ar":
        return value.display_ar()
    from .currencies import get_currency_code
    return f"{value.display()} {get_currency_code()}"


def error_text(app, exc: Exception) -> str:
    """Human-readable error: localizes validation/domain issues, else falls back to str()."""
    from ..domain.errors import (
        DebtUnavailableError,
        NoTariffFoundError,
        TariffConflictError,
        ValidationFailedError,
    )

    if isinstance(exc, ValidationFailedError):
        return ", ".join(i.localized(app.tr) for i in exc.issues)
    if isinstance(exc, NoTariffFoundError):
        return app.tr("err_no_tariff", type=exc.subscriber_type, date=str(exc.effective_date))
    if isinstance(exc, TariffConflictError):
        return app.tr("err_tariff_conflict", names=", ".join(exc.schedule_names))
    if isinstance(exc, DebtUnavailableError):
        return app.tr("err_debt_unavailable")
    return str(exc)


def kwh_display(value) -> str:
    return qty_display(value, "kWh")


class MoneyEdit(QLineEdit):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText("0")

    def money(self) -> Money | None:
        text = self.text().strip()
        if not text:
            return None
        return Money.parse_iqd_input(text)

    def set_money(self, value: Money | None) -> None:
        self.setText(value.display() if value else "0")


class ReadingEdit(QLineEdit):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText("0")

    def reading(self) -> str:
        return self.text().strip() or "0"


class FormRow(QWidget):
    def __init__(self, label: str, widget: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        lbl = QLabel(label)
        lbl.setMinimumWidth(170)
        layout.addWidget(lbl, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(widget, 1)


class PageHeader(QWidget):
    """Consistent page title block: big title + subtitle, optional trailing actions."""

    def __init__(self, title: str, subtitle: str = "",
                 actions: list[QWidget] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title_lbl = QLabel(title)
        self.title_lbl.setObjectName("PageTitle")
        self.sub_lbl = QLabel(subtitle)
        self.sub_lbl.setObjectName("PageSub")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        text_col.addWidget(self.title_lbl)
        text_col.addWidget(self.sub_lbl)
        layout.addLayout(text_col)
        layout.addStretch(1)
        for widget in actions or []:
            layout.addWidget(widget)

    def set_title(self, title: str, subtitle: str = "") -> None:
        self.title_lbl.setText(title)
        if subtitle:
            self.sub_lbl.setText(subtitle)


def status_chip(text: str, color: str) -> QLabel:
    """Compact pill label used for status/emphasis inside tables and cards."""
    from . import theme

    chip = QLabel(text)
    chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
    chip.setStyleSheet(
        f"background-color: {theme._rgba(color, 16)}; color: {color};"
        "border-radius: 8px; padding: 2px 10px; font-size: 11px; font-weight: 700;")
    return chip