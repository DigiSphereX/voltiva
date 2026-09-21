from __future__ import annotations

from decimal import Decimal

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from . import theme


class StatCard(QFrame):
    """KPI card: accent icon chip, label, large value, optional subtitle."""

    def __init__(self, title: str, *, icon: str = "", accent: str = "",
                 subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("StatCard")
        self.setMinimumHeight(92)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        c = theme.colors()
        self._accent = accent or c["accent"]
        self.icon_lbl = QLabel(icon)
        self.icon_lbl.setObjectName("KpiIcon")
        self.icon_lbl.setFixedSize(38, 38)
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("StatLabel")
        self.lbl_title.setMinimumWidth(0)
        self.lbl_title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.lbl_value = QLabel("0")
        self.lbl_value.setObjectName("StatValue")
        self.lbl_value.setMinimumWidth(0)
        self.lbl_value.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.lbl_sub = QLabel(subtitle)
        self.lbl_sub.setObjectName("StatSub")
        self.lbl_sub.setMinimumWidth(0)
        self.lbl_sub.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.lbl_sub.setVisible(bool(subtitle))

        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        text_col.addWidget(self.lbl_title)
        text_col.addWidget(self.lbl_value)
        text_col.addWidget(self.lbl_sub)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)
        layout.addWidget(self.icon_lbl)
        layout.addLayout(text_col, 1)
        self._apply_accent()

    def _apply_accent(self) -> None:
        rgba = theme._rgba(self._accent, 26)
        self.icon_lbl.setStyleSheet(
            f"background-color: {rgba}; color: {self._accent};"
            "border-radius: 10px; font-size: 18px;")

    def set_accent(self, color: str) -> None:
        self._accent = color
        self._apply_accent()

    def set_value(self, text: str) -> None:
        self.lbl_value.setText(text)

    def set_sub(self, text: str) -> None:
        self.lbl_sub.setText(text)
        self.lbl_sub.setVisible(bool(text))


class BarChart(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._labels: list[str] = []
        self._values: list[float] = []
        self._secondary: list[float] | None = None
        self._caption = ""
        self._hover: int | None = None
        self.setMinimumHeight(250)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, labels: list[str], values: list[float], caption: str = "",
                 secondary: list[float] | None = None) -> None:
        self._labels = labels
        self._values = values
        self._secondary = secondary
        self._caption = caption
        self._hover = None
        self.repaint()

    def _plot_margins(self) -> tuple[int, int, int, int]:
        """Left (y-axis labels), right, top, bottom. Bottom grows when a caption band is used."""
        cap_h = 18 if self._caption else 0
        return 8, 8, 16, 36 + cap_h

    def _bar_index_at(self, x: float) -> int | None:
        w, h = self.width(), self.height()
        margin_l, margin_r, margin_t, margin_b = self._plot_margins()
        cw = w - margin_l - 44 - margin_r
        n = len(self._values)
        if cw <= 0 or n == 0:
            return None
        gap = 10
        bw = (cw - gap * (n - 1)) / n if n > 1 else cw
        for i in range(n):
            bx = margin_l + 44 + i * (bw + gap)
            if bx <= x <= bx + bw:
                return i
        return None

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        idx = self._bar_index_at(event.position().x())
        if idx != self._hover:
            self._hover = idx
            self.repaint()

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._hover is not None:
            self._hover = None
            self.repaint()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = theme.colors()
        surface, muted, accent, accent_hi, accent_lo, success, danger = (
            c["surface"], c["muted"], c["accent"], c["accent_hi"], c["accent_lo"],
            c["success"], c["danger"])
        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, QColor(surface))

        if not self._values:
            painter.setPen(QColor(muted))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._caption or "")
            return

        margin_l, margin_r, margin_t, margin_b = self._plot_margins()
        cap_h = 18 if self._caption else 0
        max_v = max([max(self._values)] + ([max(self._secondary or [0.0])] if self._secondary else [0.0]))
        if max_v <= 0:
            max_v = 1

        # y labels first, so the plot can borrow left width from them
        fm = painter.fontMetrics()
        label_w = 0
        for i in range(4):
            y = margin_t + (self.height() - margin_t - margin_b) - ((self.height() - margin_t - margin_b) * i / 3)
            val = max_v * i / 3
            label_w = max(label_w, painter.fontMetrics().horizontalAdvance(f"{val:,.0f}"))
        margin_l = 8 + 12 + label_w
        cw = w - margin_l - margin_r
        ch = h - margin_t - margin_b
        if cw <= 0 or ch <= 0:
            return

        painter.setPen(QPen(QColor(c["border"]), 1))
        for i in range(4):
            y = int(margin_t + ch - (ch * i / 3))
            painter.drawLine(margin_l, y, w - margin_r, y)
        painter.setPen(QColor(muted))
        for i in range(4):
            y = int(margin_t + ch - (ch * i / 3))
            val = max_v * i / 3
            painter.drawText(0, y + 4, margin_l - 8, 16,
                             Qt.AlignmentFlag.AlignRight, f"{val:,.0f}")

        n = len(self._values)
        gap = 10
        bw = (cw - gap * (n - 1)) / n if n > 1 else cw
        baseline = margin_t + ch
        label_band_top = baseline + 4
        label_band_h = margin_b - cap_h - 4
        rotate_labels = n > 10 or any(len(lbl) > 8 for lbl in self._labels[:n])
        for i in range(n):
            value = self._values[i]
            sec = self._secondary[i] if self._secondary else 0
            label = self._labels[i] if i < len(self._labels) else ""
            bx = margin_l + i * (bw + gap)
            bar_w = max(int(bw), 4)

            # secondary (paid) portion at bottom in green
            if sec > 0:
                sh = ch * (sec / max_v)
                grad = QLinearGradient(0, baseline - sh, 0, baseline)
                grad.setColorAt(0, QColor(success).lighter(112))
                grad.setColorAt(1, QColor(success))
                painter.setBrush(grad)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(QRectF(bx, baseline - sh, bar_w, sh), 4, 4)
            remainder_h = ch * ((value - sec) / max_v) if self._secondary else ch * (value / max_v)
            top = baseline - remainder_h
            if remainder_h > 0:
                use_accent = not bool(self._secondary)
                color_top = accent_hi if use_accent else accent_lo
                color_bottom = accent if use_accent else danger
                grad = QLinearGradient(0, top, 0, baseline)
                grad.setColorAt(0, QColor(color_top))
                grad.setColorAt(1, QColor(color_bottom))
                painter.setBrush(grad)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(QRectF(bx, top, bar_w, remainder_h), 4, 4)

            # hover highlight
            if self._hover == i:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor(muted), 1, Qt.PenStyle.DashLine))
                painter.drawRect(QRectF(bx, margin_t - 6, bar_w, ch + 6))

        # x labels in their own band (anti-overlap: rotated when dense, clipped to band)
        painter.setClipRect(QRectF(margin_l, label_band_top, cw, label_band_h))
        painter.setPen(QColor(muted))
        for i in range(n):
            label = self._labels[i] if i < len(self._labels) else ""
            if not label:
                continue
            bx = margin_l + i * (bw + gap)
            rect = QRectF(bx, label_band_top, bar_w, label_band_h)
            elided = fm.elidedText(label, Qt.TextElideMode.ElideMiddle,
                                   int(bar_w + 60) if rotate_labels else int(max(bar_w, 30)))
            if rotate_labels:
                painter.save()
                painter.translate(rect.center().x(), label_band_top)
                painter.rotate(-40)
                painter.drawText(QRectF(0, 2, 140, label_band_h - 4),
                                 Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, elided)
                painter.restore()
            else:
                painter.drawText(rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, elided)
        painter.setClipping(False)

        # caption in its own reserved band
        if self._caption:
            painter.setPen(QColor(muted))
            painter.drawText(QRectF(margin_l, margin_t + ch + label_band_h + 2, cw, cap_h - 2),
                             Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter, self._caption)

        # hover value bubble
        if self._hover is not None and 0 <= self._hover < n:
            i = self._hover
            value = self._values[i]
            bx = margin_l + i * (bw + gap)
            top = margin_t + ch - ch * (value / max_v)
            text = f"{value:,.0f}"
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(text) + 14
            th = fm.height() + 6
            bubble_x = bx + bar_w / 2 - tw / 2
            bubble_x = max(margin_l, min(bubble_x, w - margin_r - tw))
            bubble_y = max(4, top - th - 4)
            painter.setBrush(QColor(c["surface_3"]))
            painter.setPen(QPen(QColor(c["border"]), 1))
            painter.drawRoundedRect(QRectF(bubble_x, bubble_y, tw, th), 6, 6)
            painter.setPen(QColor(c["text"]))
            painter.drawText(QRectF(bubble_x, bubble_y, tw, th),
                             Qt.AlignmentFlag.AlignCenter, text)
