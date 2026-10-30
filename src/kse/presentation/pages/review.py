from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .. import theme
from ..charts import StatCard
from ..widgets import (
    CardGrid, DataTable, PageHeader, chip_cell, configure_table, digits, money_display,
)
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
        self.card_diff = StatCard(self.tr("rv_card_diff"), icon="diff", accent=accent)
        self.card_over = StatCard(self.tr("rv_card_over"), icon="warning", accent=danger)
        self.card_official = StatCard(self.tr("rv_card_official"), icon="seal", accent=warn)
        self.card_computed = StatCard(self.tr("rv_card_computed"), icon="sigma", accent=success)

        cards = CardGrid(
            [self.card_diff, self.card_over, self.card_official, self.card_computed],
            min_card_width=200, max_columns=4)

        self.hint_lbl = QLabel(self.tr("rv_hint"))
        self.hint_lbl.setObjectName("Muted")
        self.hint_lbl.setWordWrap(True)

        self.table = DataTable()
        self.table.setToolTip(self.tr("tt_rv_table"))
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            self.tr("rv_col_month"), self.tr("rv_col_no"), self.tr("rv_col_kwh"),
            self.tr("rv_col_computed"), self.tr("rv_col_official"),
            self.tr("rv_col_diff"), self.tr("rv_col_status"),
        ])
        configure_table(
            self.table,
            aligns=(Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignRight,
                    Qt.AlignmentFlag.AlignRight, Qt.AlignmentFlag.AlignRight,
                    Qt.AlignmentFlag.AlignRight, Qt.AlignmentFlag.AlignRight,
                    Qt.AlignmentFlag.AlignHCenter),
            widths={0: 106, 1: 88, 2: 140, 3: 152, 4: 152, 5: 152},
            stretch=(6,),
            row_height=theme.Metrics.ROW_H, header_height=theme.Metrics.HEADER_H)
        self.table.set_empty_text(self.tr("il_none"))
        self.table.setSortingEnabled(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            theme.Metrics.PAGE_MARGIN, 18, theme.Metrics.PAGE_MARGIN, 18)
        layout.setSpacing(12)
        layout.addWidget(header)
        layout.addWidget(self.hint_lbl)
        layout.addWidget(cards)
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
                status, detail = self.tr("rv_no_official"), ""
                status_color = colors["muted"]
            elif diff.raw > 0:
                status, detail = self.tr("rv_status_over"), self.tr("rv_over_by").format(diff=money_display(diff))
                status_color = colors["danger"]
            elif diff.raw < 0:
                status, detail = self.tr("rv_status_under"), self.tr("rv_under_by").format(diff=money_display(diff))
                status_color = colors["warn"]
            else:
                status, detail = self.tr("rv_match"), ""
                status_color = colors["success"]

            items = [
                (digits(row["month"]), None),
                (digits(str(row["count"])), None),
                (digits(fmt_quantity(row["kwh"])), None),
                (money_display(row["computed"]), None),
                (money_display(row["official"]) if has_official else "—", None),
                (money_display(diff) if has_official else "—", status_color if diff.raw else None),
                ("", None),                            # the chip widget paints the status itself
            ]
            for col, (text, color) in enumerate(items):
                item = QTableWidgetItem(str(text))
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignVCenter
                    | (Qt.AlignmentFlag.AlignLeft if col in (0, 6) else Qt.AlignmentFlag.AlignRight))
                if color is not None:
                    item.setForeground(QColor(color))
                if col == 6:
                    item.setToolTip(detail or status)
                self.table.setItem(i, col, item)
            self.table.setCellWidget(i, 6, chip_cell(status, status_color))
            self.table.cellWidget(i, 6).setToolTip(detail or status)
        self.table.setSortingEnabled(True)

        diff = totals["diff"]
        self.card_diff.set_value(money_display(diff))
        self.card_diff.lbl_value.setStyleSheet(
            f"color: {colors['danger'] if diff.raw > 0 else colors['success'] if diff.raw < 0 else colors['text']};")
        self.card_over.set_value(digits(str(totals["overcharge_months"])))
        self.card_official.set_value(money_display(totals["official"]))
        self.card_computed.set_value(money_display(totals["computed"]))
