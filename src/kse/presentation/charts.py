from __future__ import annotations

from decimal import Decimal

from dataclasses import dataclass

from PyQt6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import (
    QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen,
)
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from . import theme
from .chart_math import (
    compact_number, donut_spans, label_step, nice_ticks, slot_at, slot_layout, visible_label_indices,
)


def _dot(p: QPainter, x: float, y: float, r: float, color: QColor) -> None:
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    p.drawEllipse(QPointF(x, y), r, r)
    p.restore()


def _polyline(p: QPainter, *points: tuple[float, float]) -> None:
    path = QPainterPath(QPointF(*points[0]))
    for x, y in points[1:]:
        path.lineTo(x, y)
    p.drawPath(path)


def _draw_document(p: QPainter, color: QColor) -> None:
    p.drawRoundedRect(QRectF(5, 3, 14, 18), 2, 2)
    _polyline(p, (8.5, 8), (15.5, 8))
    _polyline(p, (8.5, 12), (15.5, 12))
    _polyline(p, (8.5, 16), (12.5, 16))


def _draw_bolt(p: QPainter, color: QColor) -> None:
    path = QPainterPath(QPointF(13.5, 2.5))
    for x, y in ((5.5, 13.5), (11, 13.5), (10.5, 21.5), (18.5, 10.5), (13, 10.5)):
        path.lineTo(x, y)
    path.closeSubpath()
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    p.drawPath(path)
    p.restore()


def _draw_coins(p: QPainter, color: QColor) -> None:
    p.drawRoundedRect(QRectF(3, 6, 18, 12), 2.5, 2.5)
    p.drawEllipse(QPointF(12, 12), 3.2, 3.2)


def _draw_check(p: QPainter, color: QColor) -> None:
    p.drawEllipse(QPointF(12, 12), 9, 9)
    _polyline(p, (7.8, 12.3), (10.8, 15.3), (16.4, 9))


def _draw_alert(p: QPainter, color: QColor) -> None:
    p.drawEllipse(QPointF(12, 12), 9, 9)
    _polyline(p, (12, 7.4), (12, 13.2))
    _dot(p, 12, 16.6, 1.2, color)


def _draw_clock(p: QPainter, color: QColor) -> None:
    p.drawEllipse(QPointF(12, 12), 9, 9)
    _polyline(p, (12, 7), (12, 12.2), (15.4, 14))


def _draw_bars(p: QPainter, color: QColor) -> None:
    p.save()
    pen = p.pen()
    pen.setWidthF(2.8)
    p.setPen(pen)
    _polyline(p, (7, 18), (7, 12.5))
    _polyline(p, (12, 18), (12, 9))
    _polyline(p, (17, 18), (17, 5.5))
    p.restore()


def _draw_gauge(p: QPainter, color: QColor) -> None:
    p.drawArc(QRectF(3.5, 6, 17, 17), 200 * 16, 140 * 16)
    _polyline(p, (12, 14), (16.6, 9.4))
    _dot(p, 12, 14, 1.4, color)


def _draw_percent(p: QPainter, color: QColor) -> None:
    _polyline(p, (6.5, 17.5), (17.5, 6.5))
    p.drawEllipse(QPointF(8.6, 8.6), 2.6, 2.6)
    p.drawEllipse(QPointF(15.4, 15.4), 2.6, 2.6)


def _draw_trend(p: QPainter, color: QColor) -> None:
    _polyline(p, (4, 17), (9, 12), (13, 15.5), (20, 7.5))
    _polyline(p, (15.8, 7.5), (20, 7.5), (20, 11.7))


def _draw_wave(p: QPainter, color: QColor) -> None:
    path = QPainterPath(QPointF(3.5, 15))
    path.cubicTo(6, 8, 9, 8, 12, 12)
    path.cubicTo(15, 16, 18, 16, 20.5, 9)
    p.drawPath(path)


def _draw_arrow_up(p: QPainter, color: QColor) -> None:
    _polyline(p, (12, 19), (12, 5.5))
    _polyline(p, (6.5, 11), (12, 5.5), (17.5, 11))


def _draw_pulse(p: QPainter, color: QColor) -> None:
    _polyline(p, (3, 13), (7, 13), (9.5, 7.5), (12.5, 18), (15, 10.5), (16.5, 13), (21, 13))


def _draw_diff(p: QPainter, color: QColor) -> None:
    _polyline(p, (5, 9), (18.5, 9))
    _polyline(p, (15, 5.5), (18.5, 9), (15, 12.5))
    _polyline(p, (19, 15), (5.5, 15))
    _polyline(p, (9, 11.5), (5.5, 15), (9, 18.5))


def _draw_warning(p: QPainter, color: QColor) -> None:
    path = QPainterPath(QPointF(12, 3.5))
    path.lineTo(21.5, 20)
    path.lineTo(2.5, 20)
    path.closeSubpath()
    p.drawPath(path)
    _polyline(p, (12, 9), (12, 14))
    _dot(p, 12, 17.2, 1.2, color)


def _draw_seal(p: QPainter, color: QColor) -> None:
    p.drawEllipse(QPointF(12, 12), 9, 9)
    p.drawEllipse(QPointF(12, 12), 4.6, 4.6)


def _draw_sigma(p: QPainter, color: QColor) -> None:
    _polyline(p, (17, 6), (8, 6), (12.8, 12), (8, 18), (17, 18))


def _draw_diamond(p: QPainter, color: QColor) -> None:
    path = QPainterPath(QPointF(12, 3))
    for x, y in ((21, 12), (12, 21), (3, 12)):
        path.lineTo(x, y)
    path.closeSubpath()
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    p.drawPath(path)
    p.restore()


def _draw_divide(p: QPainter, color: QColor) -> None:
    _polyline(p, (5, 12), (19, 12))
    _dot(p, 12, 6.3, 1.4, color)
    _dot(p, 12, 17.7, 1.4, color)


_ICON_DRAWERS = {
    "document": _draw_document,
    "bolt": _draw_bolt,
    "coins": _draw_coins,
    "check": _draw_check,
    "alert": _draw_alert,
    "clock": _draw_clock,
    "bars": _draw_bars,
    "gauge": _draw_gauge,
    "percent": _draw_percent,
    "trend": _draw_trend,
    "wave": _draw_wave,
    "arrow-up": _draw_arrow_up,
    "pulse": _draw_pulse,
    "diff": _draw_diff,
    "warning": _draw_warning,
    "seal": _draw_seal,
    "sigma": _draw_sigma,
    "diamond": _draw_diamond,
    "divide": _draw_divide,
}


class KpiIcon(QWidget):
    """Vector icon chip for KPI cards.

    Dingbat glyphs (◈ ◉ ◐ …) come from unpredictable fallback fonts and render at
    inconsistent weights; painting the shapes keeps every card crisp and on-brand.
    """

    def __init__(self, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._name = name
        self._color = "#4F46E5"
        self.setObjectName("KpiIcon")
        self.setFixedSize(38, 38)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    def icon_name(self) -> str:
        return self._name

    def set_icon(self, name: str) -> None:
        self._name = name
        self.update()

    def set_color(self, color: str) -> None:
        self._color = color
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor(self._color)
        pen = QPen(color, 1.7)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        # 24-unit design grid → 20px inside the 38px chip
        painter.translate(9, 9)
        painter.scale(20 / 24, 20 / 24)
        _ICON_DRAWERS.get(self._name, _draw_document)(painter, color)


class StatCard(QFrame):
    """KPI card: accent icon chip, label, large value, optional subtitle."""

    def __init__(self, title: str, *, icon: str = "", accent: str = "",
                 subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("StatCard")
        self.setMinimumHeight(96)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        c = theme.colors()
        self._accent = accent or c["accent"]
        self.icon_lbl = KpiIcon(icon)
        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("StatLabel")
        self.lbl_title.setMinimumWidth(0)
        self.lbl_title.setWordWrap(True)
        self.lbl_title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)
        self.lbl_value = QLabel("0")
        self.lbl_value.setObjectName("StatValue")
        self.lbl_value.setMinimumWidth(0)
        self.lbl_value.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.lbl_sub = QLabel(subtitle)
        self.lbl_sub.setObjectName("StatSub")
        self.lbl_sub.setMinimumWidth(0)
        self.lbl_sub.setWordWrap(True)
        self.lbl_sub.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)
        self.lbl_sub.setVisible(bool(subtitle))

        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        text_col.addWidget(self.lbl_title)
        text_col.addWidget(self.lbl_value)
        text_col.addWidget(self.lbl_sub)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)
        layout.addWidget(self.icon_lbl, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(text_col, 1)
        self._apply_accent()

    def _apply_accent(self) -> None:
        rgba = theme._rgba(self._accent, 26)
        self.icon_lbl.setStyleSheet(
            f"background-color: {rgba}; border-radius: 10px;")
        self.icon_lbl.set_color(self._accent)

    def set_accent(self, color: str) -> None:
        self._accent = color
        self._apply_accent()

    def set_value(self, text: str) -> None:
        self.lbl_value.setText(text)
        self.lbl_value.setToolTip(text)

    def set_sub(self, text: str) -> None:
        self.lbl_sub.setText(text)
        self.lbl_sub.setToolTip(text)
        self.lbl_sub.setVisible(bool(text))


def _axis_font(widget: QWidget) -> QFont:
    """Slightly smaller copy of the widget font. Handles both pixel-sized fonts (set by the
    style sheet: ``font-size: 13px``) and point-sized ones."""
    f = QFont(widget.font())
    if f.pixelSize() > 0:
        f.setPixelSize(max(10, f.pixelSize() - 1))
    elif f.pointSizeF() > 0:
        f.setPointSizeF(max(8.0, f.pointSizeF() - 1.0))
    return f


def _fmt(value: float) -> str:
    """Compact axis / value-label text (e.g. 3.2K)."""
    return compact_number(value)


def _value_label(value: float, max_width: float, fm: QFontMetrics) -> str:
    """The exact figure (3,210) when it fits above the bar, otherwise the compact form (3.2K)."""
    full = f"{value:,.0f}"
    return full if fm.horizontalAdvance(full) <= max_width else _fmt(value)


def _is_rtl(widget: QWidget) -> bool:
    return widget.layoutDirection() == Qt.LayoutDirection.RightToLeft


@dataclass
class _Geo:
    plot: QRectF
    slots: list
    ticks: list
    axis_max: float
    tick_labels: list
    rtl: bool
    label_h: int
    cap_h: int


class BarChart(QWidget):
    """Bar chart with round axis ticks, capped bar width, animated growth, hover tooltip,
    an optional stacked "paid / remaining" mode and RTL support.

    ``secondary`` (when given) is the PAID part of each bar; the rest is "remaining".
    All geometry comes from :mod:`chart_math`, shared by painting and hit-testing.
    When ``keys`` are supplied (e.g. "2024-03") a click on a bar emits ``barClicked(key)``.
    """

    barClicked = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._labels: list[str] = []
        self._values: list[float] = []
        self._secondary: list[float] | None = None
        self._caption = ""
        self._legend: tuple[str, str] | None = None
        self._integer = False
        self._keys: list[str] = []
        self._hover: int | None = None
        self._progress = 1.0
        self.setMinimumHeight(260)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(380)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)

    # ------------------------------------------------------------ data
    def set_data(self, labels: list[str], values: list[float], caption: str = "",
                 secondary: list[float] | None = None, *, integer: bool = False,
                 legend: tuple[str, str] | None = None, keys: list[str] | None = None) -> None:
        new_state = (tuple(labels), tuple(values), tuple(secondary) if secondary else None)
        changed = new_state != (tuple(self._labels), tuple(self._values),
                                tuple(self._secondary) if self._secondary else None)
        self._labels = list(labels)
        self._values = [max(0.0, float(v)) for v in values]
        self._secondary = [max(0.0, float(v)) for v in secondary] if secondary else None
        self._caption = caption
        self._integer = integer
        self._keys = list(keys) if keys else []
        self._legend = legend if secondary else None
        self._hover = None
        self._anim.stop()
        if changed and self._values and self.isVisible():
            self._progress = 0.0
            self._anim.start()
        else:
            self._progress = 1.0
            self.update()

    def _on_anim(self, value) -> None:
        self._progress = float(value)
        self.update()

    # -------------------------------------------------------- geometry
    def _geometry(self) -> _Geo:
        fm = QFontMetrics(_axis_font(self))
        w, h = self.width(), self.height()
        n = len(self._values)
        ticks, axis_max = nice_ticks(max(self._values + [0.0]), integer=self._integer)
        tick_labels = [_fmt(t) for t in ticks]
        label_w = max(fm.horizontalAdvance(s) for s in tick_labels)
        rtl = _is_rtl(self)
        axis_w = label_w + 18
        top = 22 + (18 if self._legend else 0)   # room for value labels above the tallest bar
        label_h = fm.height() + 8
        cap_h = 20 if self._caption else 0
        bottom = label_h + cap_h + 6
        left, right = (10, axis_w) if rtl else (axis_w, 10)
        plot = QRectF(left, top, max(1.0, w - left - right), max(1.0, h - top - bottom))
        return _Geo(plot, slot_layout(n, plot.left(), plot.width(), rtl=rtl), ticks, axis_max,
                    tick_labels, rtl, label_h, cap_h)

    # ----------------------------------------------------------- mouse
    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        idx = slot_at(self._geometry().slots, event.position().x()) if self._values else None
        if idx != self._hover:
            self._hover = idx
            self.setCursor(Qt.CursorShape.PointingHandCursor if idx is not None and self._keys
                           else Qt.CursorShape.ArrowCursor)
            self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if (event.button() == Qt.MouseButton.LeftButton and self._hover is not None
                and self._hover < len(self._keys)):
            self.barClicked.emit(self._keys[self._hover])
        super().mousePressEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._hover is not None:
            self._hover = None
            self.update()
        super().leaveEvent(event)

    # ----------------------------------------------------------- paint
    @staticmethod
    def _draw_bar(p: QPainter, x: float, y: float, w: float, h: float, color: str,
                  round_top: bool) -> None:
        if h <= 0.4:
            return
        top_c = QColor(color).lighter(108)
        grad = QLinearGradient(0, y, 0, y + h)
        grad.setColorAt(0, top_c)
        grad.setColorAt(1, QColor(color))
        p.setBrush(grad)
        p.setPen(Qt.PenStyle.NoPen)
        r = min(6.0, w / 2, h)
        if round_top:
            p.drawRoundedRect(QRectF(x, y, w, h), r, r)
            if h > r:                     # square off the bottom corners
                p.drawRect(QRectF(x, y + h - r, w, r))
        else:
            p.drawRect(QRectF(x, y, w, h))

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setFont(_axis_font(self))
        c = theme.colors()
        # transparent background: the surrounding Card provides the surface + rounded corners
        if not self._values:
            p.setPen(QColor(c["muted"]))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._caption or "")
            return

        g = self._geometry()
        plot, n = g.plot, len(self._values)
        fm = p.fontMetrics()
        stacked = self._secondary is not None

        # ---- grid + y labels
        for t, text in zip(g.ticks, g.tick_labels):
            y = plot.bottom() - plot.height() * t / g.axis_max
            pen = QPen(QColor(c["grid"]), 1)
            if t > 0:
                pen.setStyle(Qt.PenStyle.DashLine)
                pen.setDashPattern([3.0, 4.0])
            p.setPen(pen)
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(QColor(c["muted"]))
            if g.rtl:
                p.drawText(QRectF(plot.right() + 8, y - 9, self.width() - plot.right() - 8, 18),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
            else:
                p.drawText(QRectF(0, y - 9, plot.left() - 8, 18),
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, text)

        # ---- hover column
        if self._hover is not None:
            s = g.slots[self._hover]
            hl = QColor(c["accent"])
            hl.setAlpha(40)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(hl)
            p.drawRoundedRect(QRectF(s.x + 2, plot.top() - 6, s.width - 4, plot.height() + 6), 6, 6)

        # ---- bars
        series0 = c["series"][0]
        for i, s in enumerate(g.slots):
            total = self._values[i]
            bar_h = plot.height() * total / g.axis_max * self._progress
            if total > 0:
                bar_h = max(bar_h, 3.0)
            base = plot.bottom()
            if stacked:
                paid = min(self._secondary[i], total)
                paid_h = bar_h * (paid / total) if total > 0 else 0.0
                rem_h = bar_h - paid_h
                self._draw_bar(p, s.bar_x, base - paid_h, s.bar_w, paid_h, c["success"], rem_h <= 0.4)
                self._draw_bar(p, s.bar_x, base - bar_h, s.bar_w, rem_h, c["danger"], True)
            else:
                self._draw_bar(p, s.bar_x, base - bar_h, s.bar_w, bar_h, series0, True)

        # ---- static value labels (only when they fit comfortably)
        if n <= 12 and g.slots and g.slots[0].width >= 44 and self._progress >= 0.999:
            p.setPen(QColor(c["text"]))
            for i, s in enumerate(g.slots):
                if i == self._hover or self._values[i] <= 0:
                    continue
                y = plot.bottom() - plot.height() * self._values[i] / g.axis_max
                p.drawText(QRectF(s.x - 6, y - 20, s.width + 12, 16),
                           Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                           _value_label(self._values[i], s.width - 4, fm))

        # ---- x labels: every k-th label so they never overlap; the newest is always shown
        max_lw = max((fm.horizontalAdvance(t) for t in self._labels), default=0)
        slot_w = g.slots[0].width if g.slots else 1.0
        step = label_step(slot_w, max_lw, gap=6.0)
        p.setPen(QColor(c["muted"]))
        for i in visible_label_indices(n, step):
            if i >= len(self._labels) or not self._labels[i]:
                continue
            s = g.slots[i]
            cx = s.x + s.width / 2
            p.drawText(QRectF(cx - slot_w * step / 2, plot.bottom() + 6, slot_w * step, g.label_h),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, self._labels[i])

        # ---- caption
        if self._caption:
            p.setPen(QColor(c["muted"]))
            p.drawText(QRectF(plot.left(), self.height() - g.cap_h, plot.width(), g.cap_h),
                       Qt.AlignmentFlag.AlignCenter, self._caption)

        # ---- legend (stacked mode)
        if self._legend:
            items = ((self._legend[0], c["success"]), (self._legend[1], c["danger"]))
            widths = [fm.horizontalAdvance(t) + 22 for t, _ in items]
            x = plot.right() - sum(widths) if g.rtl else plot.left()
            for (text, color), wd in zip(items, widths):
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(color))
                p.drawEllipse(QRectF(x, 8, 9, 9))
                p.setPen(QColor(c["muted"]))
                p.drawText(QRectF(x + 15, 2, wd, 20),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
                x += wd + 6

        # ---- hover tooltip bubble
        if self._hover is not None:
            self._draw_bubble(p, g, fm, c)

    def _draw_bubble(self, p: QPainter, g: _Geo, fm: QFontMetrics, c: dict) -> None:
        i = self._hover
        s = g.slots[i]
        total = self._values[i]
        lines = [self._labels[i] if i < len(self._labels) else "", f"{total:,.0f}"]
        if self._secondary is not None and self._legend:
            paid = min(self._secondary[i], total)
            lines.append(f"{self._legend[0]}: {paid:,.0f}")
            lines.append(f"{self._legend[1]}: {total - paid:,.0f}")
        tw = max(fm.horizontalAdvance(t) for t in lines) + 20
        th = fm.height() * len(lines) + 12
        top_y = g.plot.bottom() - g.plot.height() * total / g.axis_max
        bx = min(max(4.0, s.x + s.width / 2 - tw / 2), self.width() - tw - 4)
        by = max(4.0, top_y - th - 10)
        p.setBrush(QColor(c["surface_3"]))
        p.setPen(QPen(QColor(c["border"]), 1))
        p.drawRoundedRect(QRectF(bx, by, tw, th), 8, 8)
        for k, text in enumerate(lines):
            p.setPen(QColor(c["muted"] if k == 0 else c["text"]))
            p.drawText(QRectF(bx, by + 6 + k * fm.height(), tw, fm.height()),
                       Qt.AlignmentFlag.AlignCenter, text)


class DonutChart(QWidget):
    """Ring chart with a centre total and a two-line legend (label / detail).

    ``items`` = [(label, value, color, detail_text), ...]; ring size follows ``value``.
    ``color`` is a hex string OR a theme token name (``"success"``, ``"warn"`` ...). Tokens are
    resolved on every paint, so a light/dark switch recolours the chart without new data.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: list[tuple[str, float, str, str]] = []
        self._center = ""
        self._center_sub = ""
        self.setMinimumHeight(170)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def set_data(self, items: list[tuple[str, float, str, str]], center: str = "",
                 center_sub: str = "") -> None:
        self._items = list(items)
        self._center = center
        self._center_sub = center_sub
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = theme.colors()
        w, h = self.width(), self.height()
        rtl = _is_rtl(self)
        d = max(90.0, min(h - 12.0, w * 0.46, 190.0))
        thick = d * 0.16
        x0 = (w - d - 4) if rtl else 4.0
        y0 = (h - d) / 2
        arc_rect = QRectF(x0 + thick / 2, y0 + thick / 2, d - thick, d - thick)

        # track
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(c["grid"]), thick))
        p.drawEllipse(arc_rect)
        # slices (clockwise from 12 o'clock; Qt angles are counter-clockwise from 3 o'clock)
        spans = donut_spans([max(0.0, it[1]) for it in self._items])
        for (label, value, color, detail), (start, span) in zip(self._items, spans):
            if span <= 0:
                continue
            pen = QPen(QColor(c.get(color, color)), thick)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            p.setPen(pen)
            p.drawArc(arc_rect, int((90 - start) * 16), int(-span * 16))

        # centre text
        big = QFont(self.font())
        if big.pixelSize() > 0:
            big.setPixelSize(int(big.pixelSize() * 1.7))
        elif big.pointSizeF() > 0:
            big.setPointSizeF(big.pointSizeF() * 1.7)
        big.setBold(True)
        p.setFont(big)
        p.setPen(QColor(c["text"]))
        inner = QRectF(x0 + thick, y0 + thick, d - 2 * thick, d - 2 * thick)
        p.drawText(inner.adjusted(0, 0, 0, -10 if self._center_sub else 0),
                   Qt.AlignmentFlag.AlignCenter, self._center)
        if self._center_sub:
            p.setFont(_axis_font(self))
            p.setPen(QColor(c["muted"]))
            p.drawText(inner.adjusted(0, inner.height() * 0.30, 0, 0),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                       self._center_sub)

        # legend
        p.setFont(self.font())
        fm = p.fontMetrics()
        small = QFontMetrics(_axis_font(self))
        row_h = fm.height() + small.height() + 10
        block_h = row_h * len(self._items)
        ly = (h - block_h) / 2
        area_l = x0 + d + 22 if not rtl else 4.0
        area_r = w - 4.0 if not rtl else x0 - 22
        avail = max(20.0, area_r - area_l)
        align = Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft
        for label, value, color, detail in self._items:
            dot_x = area_r - 10 if rtl else area_l
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(c.get(color, color)))
            p.drawEllipse(QRectF(dot_x, ly + 5, 10, 10))
            text_l = area_l if rtl else area_l + 18
            text_w = avail - 18
            p.setFont(self.font())
            p.setPen(QColor(c["text"]))
            p.drawText(QRectF(text_l, ly, text_w, fm.height() + 2), align | Qt.AlignmentFlag.AlignVCenter,
                       fm.elidedText(label, Qt.TextElideMode.ElideRight, int(text_w)))
            p.setFont(_axis_font(self))
            p.setPen(QColor(c["muted"]))
            p.drawText(QRectF(text_l, ly + fm.height() + 2, text_w, small.height() + 2),
                       align | Qt.AlignmentFlag.AlignVCenter,
                       small.elidedText(detail, Qt.TextElideMode.ElideRight, int(text_w)))
            ly += row_h
