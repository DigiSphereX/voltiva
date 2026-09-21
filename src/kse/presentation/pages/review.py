from __future__ import annotations

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QHBoxLayout, QHeaderView, QLabel, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from .. import theme
from ..charts import StatCard
from ..widgets import PageHeader, money_display, digits
from ...domain.money import fmt_quantity


class ReviewPage(QWidget):
    """Monthly settlement review — official (collector slip) vs computed amounts."""

    def __init__(self, app, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.tr = app.tr

        header = PageHeader(
            self.tr("rv_title"),
            self.tr("rv_subtitle"))

        accent = theme.colors()["accent"]
        danger = theme.colors()["danger"]
        warn = theme.colors()["warn"]
        success = theme.colors()["success"]
        self.card_diff = StatCard(self.tr("rv_card_diff"), icon="◔", accent=accent)
        self.card_over = StatCard(self.tr("rv_card_over"), icon="⚠", accent=danger)
        self.card_official = StatCard(self.tr("rv_card_official"), icon="◉", accent=warn)
        self.card_computed = StatCard(self.tr("rv_card_computed"), icon="Σ", accent=success)

        cards = QHBoxLayout()
        cards.setSpacing(12)
        cards.addWidget(self.card_diff)
        cards.addWidget(self.card_over)
        cards.addWidget(self.card_official)
        cards.addWidget(self.card_computed)

        self.hint_lbl = QLabel(self.tr("rv_hint"))
        self.hint_lbl.setObjectName("Muted")
        self.hint_lbl.setWordWrap(True)

        self.table = QTableWidget()
        self.table.setToolTip(self.tr("tt_rv_table"))
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            self.tr("rv_col_month"), self.tr("rv_col_no"), self.tr("rv_col_kwh"),
            self.tr("rv_col_computed"), self.tr("rv_col_official"),
            self.tr("rv_col_diff"), self.tr("rv_col_status"),
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setSortingEnabled(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(12)
        layout.addWidget(header)
        layout.addWidget(self.hint_lbl)
        layout.addLayout(cards)
        layout.addSpacing(4)
        layout.addWidget(self.table, 1)

    def refresh(self) -> None:
        review = self.app.analytics.monthly_review()
        rows = review["rows"]
        totals = review["totals"]
        colors = theme.colors()

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            diff = row["diff"]
            has_official = row["official_count"] > 0
            if not has_official:
                status = self.tr("rv_no_official")
                status_color = colors["muted"]
            elif diff.raw > 0:
                status = self.tr("rv_over_by").format(diff=money_display(diff))
                status_color = colors["danger"]
            elif diff.raw < 0:
                status = self.tr("rv_under_by").format(diff=money_display(diff))
                status_color = colors["warn"]
            else:
                status = self.tr("rv_match")
                status_color = colors["success"]

            items = [
                (row["month"], None),
                (digits(str(row["count"])), None),
                (digits(fmt_quantity(row["kwh"])), None),
                (money_display(row["computed"]), None),
                (money_display(row["official"]) if has_official else "—", None),
                (money_display(diff) if has_official else "—", status_color),
                (status, status_color),
            ]
            for col, (text, color) in enumerate(items):
                item = QTableWidgetItem(str(text))
                if color is not None:
                    item.setForeground(QColor(color))
                    item.setFont(self.table.font())
                if col in (1, 2):
                    item.setTextAlignment(0x0002)  # AlignCenter
                self.table.setItem(i, col, item)
        self.table.setSortingEnabled(True)

        diff = totals["diff"]
        self.card_diff.set_value(money_display(diff))
        self.card_diff.lbl_value.setStyleSheet(
            f"color: {colors['danger'] if diff.raw > 0 else colors['success'] if diff.raw < 0 else colors['text']};")
        self.card_over.set_value(str(totals["overcharge_months"]))
        self.card_official.set_value(money_display(totals["official"]))
        self.card_computed.set_value(money_display(totals["computed"]))
