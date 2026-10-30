from __future__ import annotations

from PyQt6.QtCore import QDate, QLocale, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPalette, QTextCharFormat
from PyQt6.QtWidgets import (
    QCalendarWidget, QDateEdit, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QSizePolicy, QStyle, QStyledItemDelegate, QTableWidget, QToolButton, QVBoxLayout,
    QWidget,
)

from ..domain.money import Money, fmt_quantity, set_arabic_display
from . import theme

_MONEY_LANG = "en"
_UI_LANG = "en"


def set_ui_lang(lang: str) -> None:
    """Language used by widgets created afterwards (e.g. calendar month names)."""
    global _UI_LANG
    _UI_LANG = lang or "en"


def rtl_active() -> bool:
    from .i18n import RTL_LANGS

    return _UI_LANG in RTL_LANGS


def set_money_lang(lang: str) -> None:
    """Switch number/currency formatting style.

    "ar" → Arabic-Indic digits + "د.ع"; anything else → Western digits + ISO code.
    """
    global _MONEY_LANG
    _MONEY_LANG = "ar" if lang == "ar" else "en"
    set_arabic_display(_MONEY_LANG == "ar")


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


class DateEdit(QDateEdit):
    """QDateEdit with the shared control height.

    Qt adds 3px of popup-button slack to QDateEdit's content hint, which made date
    fields taller than text fields; the style sheet pins the content box and this
    hint keeps layouts reserving the same height as every other input.
    """

    def sizeHint(self) -> QSize:  # noqa: N802
        hint = super().sizeHint()
        hint.setHeight(theme.Metrics.CONTROL_H + theme.Metrics.CONTROL_CHROME)
        return hint

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        # the style sheet's RTL alignment never reaches the spin box's internal editor
        rtl = self.layoutDirection() == Qt.LayoutDirection.RightToLeft
        align = Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft
        self.setAlignment(align | Qt.AlignmentFlag.AlignVCenter)


def date_edit(date: QDate | None = None) -> DateEdit:
    """Calendar picker with the app's day-first format (QDateEdit's locale default varies)."""
    widget = DateEdit(QDate.currentDate() if date is None else date)
    widget.setCalendarPopup(True)
    widget.setDisplayFormat("dd/MM/yyyy")

    cal = widget.calendarWidget()
    locale = QLocale(_UI_LANG)
    cal.setLocale(locale)
    cal.setFirstDayOfWeek(locale.firstDayOfWeek())
    cal.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
    cal.setMinimumSize(360, 280)

    colors = theme.colors()
    header_fmt = QTextCharFormat()
    header_fmt.setForeground(QColor(colors["muted"]))
    header_fmt.setFontPointSize(9.0)
    header_fmt.setFontWeight(QFont.Weight.DemiBold)
    cal.setHeaderTextFormat(header_fmt)

    weekend = (Qt.DayOfWeek.Friday, Qt.DayOfWeek.Saturday) if _UI_LANG == "ar" \
        else (Qt.DayOfWeek.Saturday, Qt.DayOfWeek.Sunday)
    day_fmt = QTextCharFormat()
    day_fmt.setForeground(QColor(colors["text"]))
    weekend_fmt = QTextCharFormat()
    weekend_fmt.setForeground(QColor(colors["danger"]))
    for day in (Qt.DayOfWeek.Monday, Qt.DayOfWeek.Tuesday, Qt.DayOfWeek.Wednesday,
                Qt.DayOfWeek.Thursday, Qt.DayOfWeek.Friday,
                Qt.DayOfWeek.Saturday, Qt.DayOfWeek.Sunday):
        cal.setWeekdayTextFormat(day, weekend_fmt if day in weekend else day_fmt)

    # Qt keeps these two buttons at the physical left/right edges even in RTL,
    # so the icons stay positional: left edge = previous, right edge = next.
    for object_name, icon_name in (("qt_calendar_prevmonth", "chevron-left"),
                                   ("qt_calendar_nextmonth", "chevron-right")):
        button = cal.findChild(QToolButton, object_name)
        icon_path = theme.icon_file(icon_name)
        if button is not None and icon_path:
            button.setIcon(QIcon(icon_path))
            button.setIconSize(QSize(12, 12))
    return widget


class Section(QFrame):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.title_lbl = QLabel(title)
        self.title_lbl.setObjectName("CardTitle")
        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(10)
        outer = QVBoxLayout(self)
        # the title lives INSIDE the card: without padding it was painted on the border
        outer.setContentsMargins(18, 15, 18, 18)
        outer.setSpacing(0)
        outer.addWidget(self.title_lbl)
        outer.addSpacing(10)
        outer.addLayout(self.body)

    def add_layout(self, layout) -> None:
        self.body.addLayout(layout)

    def add_widget(self, widget: QWidget) -> None:
        self.body.addWidget(widget)

    def add_spacing(self, px: int) -> None:
        self.body.addSpacing(px)

    def add_stretch(self, stretch: int = 1) -> None:
        """Absorb extra card height instead of letting labels drift apart."""
        self.body.addStretch(stretch)


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
        DuplicateInvoiceNumberError,
        InvoiceStateError,
        NoTariffFoundError,
        PaymentError,
        TariffConflictError,
        ValidationFailedError,
    )

    if isinstance(exc, ValidationFailedError):
        return ", ".join(i.localized(app.tr) for i in exc.issues)
    if isinstance(exc, NoTariffFoundError):
        i18n = getattr(app, "i18n", None)
        kind = i18n.enum_label(exc.subscriber_type) if i18n else exc.subscriber_type
        return app.tr("err_no_tariff", type=kind, date=str(exc.effective_date))
    if isinstance(exc, TariffConflictError):
        return app.tr("err_tariff_conflict", names=", ".join(exc.schedule_names))
    if isinstance(exc, DebtUnavailableError):
        return app.tr("err_debt_unavailable")
    if isinstance(exc, InvoiceStateError):
        return app.tr("err_invoice_" + exc.reason)
    if isinstance(exc, DuplicateInvoiceNumberError):
        return app.tr("err_duplicate_invoice_no", no=exc.invoice_no)
    if isinstance(exc, PaymentError):
        return app.tr("err_payment_" + exc.reason)
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


def form_label(text: str, width: int = 148) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("FieldLabel")
    lbl.setMinimumWidth(width)
    lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    return lbl


class FormRow(QWidget):
    def __init__(self, label: str, widget: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # rows must keep their natural height, otherwise a tall card spreads the form
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 1, 0, 1)
        layout.setSpacing(14)
        layout.addWidget(form_label(label), 0)
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
        self.sub_lbl.setWordWrap(True)
        self.sub_lbl.setVisible(bool(subtitle))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        text_col = QVBoxLayout()
        text_col.setSpacing(3)
        text_col.addWidget(self.title_lbl)
        text_col.addWidget(self.sub_lbl)
        layout.addLayout(text_col, 1)
        for widget in actions or []:
            layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignTop)

    def set_title(self, title: str, subtitle: str = "") -> None:
        self.title_lbl.setText(title)
        if subtitle:
            self.sub_lbl.setText(subtitle)
            self.sub_lbl.setVisible(True)


class RtlAlignDelegate(QStyledItemDelegate):
    """Right-align every RTL cell.

    Qt mirrors left/right alignments per item, which makes an Arabic table look ragged
    (text hugging one edge, numbers the other). Pinning all content to the right edge —
    chips stay centred — gives the single clean edge Arabic tables are read along.
    """

    _VERTICAL = (
        Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignVCenter
        | Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignBaseline
    )

    def initStyleOption(self, option, index) -> None:  # noqa: N802
        super().initStyleOption(option, index)
        # A foreground set on the item (status colours, muted inactive rows) overrides
        # the style sheet's selected colour and left e.g. red text on the amber accent
        # at ~1:1 contrast. Selected rows read in on_accent no matter what the data role says.
        if option.state & QStyle.StateFlag.State_Selected:
            on_accent = QColor(theme.colors()["on_accent"])
            option.palette.setColor(QPalette.ColorRole.Text, on_accent)
            option.palette.setColor(QPalette.ColorRole.HighlightedText, on_accent)
        if option.direction != Qt.LayoutDirection.RightToLeft:
            return
        current = option.displayAlignment
        if current & Qt.AlignmentFlag.AlignHCenter:
            vertical = current & self._VERTICAL
            option.displayAlignment = (vertical or Qt.AlignmentFlag.AlignVCenter) | \
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignAbsolute
            return
        vertical = current & self._VERTICAL
        option.displayAlignment = (vertical or Qt.AlignmentFlag.AlignVCenter) | \
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute


class DataTable(QTableWidget):
    """Read-only table with the application's shared table look.

    Also paints an empty-state message in the body, so a fresh database never shows a
    large unexplained white rectangle.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # must exist before configure_table/rows so headers and cells share one alignment
        self.setItemDelegate(RtlAlignDelegate(self))
        self._empty_text = ""
        self.setShowGrid(True)
        self.setWordWrap(False)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.setCornerButtonEnabled(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(theme.Metrics.ROW_H)
        header = self.horizontalHeader()
        header.setFixedHeight(theme.Metrics.HEADER_H)
        header.setHighlightSections(False)
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(60)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    def set_empty_text(self, text: str) -> None:
        self._empty_text = text
        self.viewport().update()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if not self._empty_text or self.model().rowCount():
            return
        painter = QPainter(self.viewport())
        painter.setPen(QColor(theme.colors()["muted"]))
        font = QFont(self.font())
        font.setItalic(True)
        painter.setFont(font)
        painter.drawText(self.viewport().rect(), Qt.AlignmentFlag.AlignCenter, self._empty_text)


def configure_table(
    table: QTableWidget,
    *,
    aligns: tuple[Qt.AlignmentFlag | None, ...] | None = None,
    widths: dict[int, int] | None = None,
    contents: tuple[int, ...] = (),
    stretch: tuple[int, ...] = (),
    row_height: int | None = None,
    header_height: int | None = None,
) -> None:
    """Apply the shared table geometry: column rules + header and row heights.

    ``aligns`` is applied to BOTH the header cells and the column logic used by the page;
    ``widths`` pins columns, ``contents`` fits a column to its content and ``stretch``
    lets a column absorb the remaining width (normally the name/title column).
    """
    header = table.horizontalHeader()
    header.setMinimumSectionSize(60)
    header.setStretchLastSection(False)
    header.setHighlightSections(False)
    if header_height:
        header.setFixedHeight(header_height)
    if row_height:
        table.verticalHeader().setDefaultSectionSize(row_height)
    table.verticalHeader().setVisible(False)
    table.setWordWrap(False)
    for col in range(table.columnCount()):
        header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
    for col in contents:
        header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
    for col, width in (widths or {}).items():
        header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(col, width)
    for col in stretch:
        header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
    if aligns:
        rtl = table.layoutDirection() == Qt.LayoutDirection.RightToLeft
        for col, align in enumerate(aligns):
            item = table.horizontalHeaderItem(col)
            if item is None or align is None:
                continue
            if rtl and not (align & Qt.AlignmentFlag.AlignHCenter):
                # keep headers on the same (right) edge as RtlAlignDelegate cells
                effective = Qt.AlignmentFlag.AlignRight
            else:
                effective = align
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignVCenter | effective | Qt.AlignmentFlag.AlignAbsolute)


def action_cell(*buttons: QPushButton, spacing: int = 6) -> QWidget:
    """Row-action buttons laid out for ``setCellWidget`` (centred, no dead flex)."""
    holder = QWidget()
    holder.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    layout = QHBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(spacing)
    layout.addStretch(1)
    for button in buttons:
        layout.addWidget(button)
    layout.addStretch(1)
    return holder


def fit_action_column(table: QTableWidget, col: int, cell: QWidget) -> None:
    """Widen ``col`` when the action cell's buttons would spill over the cell.

    The QSS insets cell widgets by 12px on each side, and a QHBoxLayout cannot shrink
    below its buttons' minimum widths, so a fixed column silently overlaps its neighbour.
    """
    cell.ensurePolished()
    needed = cell.sizeHint().width() + 32
    if table.columnWidth(col) < needed:
        table.setColumnWidth(col, needed)


class CardGrid(QWidget):
    """Responsive grid of KPI cards: 4 columns when there is room, fewer when there is not."""

    def __init__(self, cards: list[QWidget], *, min_card_width: int = 220,
                 max_columns: int = 4, spacing: int = 12, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cards = list(cards)
        self._min_width = min_card_width
        self._max_columns = max_columns
        self._spacing = spacing
        self._columns = 0
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(spacing)
        self._relayout(1)

    def _relayout(self, columns: int) -> None:
        if columns == self._columns:
            return
        self._columns = columns
        while self._grid.count():
            self._grid.takeAt(0)
        for index, card in enumerate(self._cards):
            self._grid.addWidget(card, index // columns, index % columns)
        for col in range(self._max_columns):
            self._grid.setColumnStretch(col, 1 if col < columns else 0)

    def resizeEvent(self, event) -> None:  # noqa: N802
        step = self._min_width + self._spacing
        columns = max(1, min(self._max_columns, (self.width() + self._spacing) // step))
        self._relayout(columns)
        super().resizeEvent(event)


def status_chip(text: str, color: str) -> QLabel:
    """Compact pill label used for status/emphasis inside tables and cards."""
    chip = QLabel(text)
    chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
    # 16/255 tint mixed onto the surface: opaque, so a selected/hovered row's accent
    # cannot bleed through and turn the status text into red-on-orange.
    background = theme.blend_hex(color, theme.colors()["surface"], 16 / 255)
    chip.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    chip.setStyleSheet(
        f"background-color: {background}; color: {color};"
        "border-radius: 9px; padding: 3px 10px; font-size: 11px; font-weight: 700;")
    return chip


def style_table(table, *, row_height: int | None = None) -> None:
    """Backwards-compatible one-liner for tables that only need the common look."""
    configure_table(table, row_height=row_height or theme.Metrics.ROW_H,
                     header_height=theme.Metrics.HEADER_H)


def chip_cell(text: str, color: str) -> QWidget:
    """A status chip for ``QTableWidget.setCellWidget``.

    A bare chip is stretched to the whole cell (a wide coloured box); wrapping it in a
    transparent container keeps it pill-sized, centred, and lets the row's alternating /
    selection colours show through.
    """
    holder = QWidget()
    holder.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    holder.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    holder.setStyleSheet("background: transparent;")
    lay = QHBoxLayout(holder)
    lay.setContentsMargins(6, 6, 6, 6)
    lay.addStretch(1)
    lay.addWidget(status_chip(text, color))
    lay.addStretch(1)
    return holder