from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QScrollArea, QTableWidgetItem,
    QVBoxLayout, QWidget, QFileDialog, QMessageBox,
)

from .. import theme
from ..charts import BarChart, DonutChart, StatCard
from ..currencies import get_currency_code
from ..widgets import (
    CardGrid, DataTable, PageHeader, chip_cell, configure_table,
    error_text, ghost_button, money_display,
)
from ...domain.money import Money, fmt_quantity


class AnalyticsPage(QWidget):
    def __init__(self, app, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.tr = app.tr

        header = PageHeader(self.tr("an_title"), self.tr("an_subtitle"))

        self.metric_combo = QComboBox()
        self.metric_combo.setToolTip(self.tr("tt_an_metric"))
        self.metric_combo.addItem(self.tr("an_metric_kwh"), "kwh")
        self.metric_combo.addItem(f"{self.tr('an_metric_amount')} ({get_currency_code()})", "amount")
        self.metric_combo.addItem(self.tr("an_metric_count"), "count")

        self.range_combo = QComboBox()
        self.range_combo.setToolTip(self.tr("tt_an_range"))
        for label, months in ((self.tr("an_range_3"), 3), (self.tr("an_range_6"), 6),
                              (self.tr("an_range_12"), 12), (self.tr("an_range_24"), 24),
                              (self.tr("an_range_all"), 0)):
            self.range_combo.addItem(label, months)

        c = theme.colors()
        self.cards = [
            StatCard(self.tr("dash_total_invoices"), icon="document", accent=c["accent"]),
            StatCard(self.tr("dash_total_kwh"), icon="bolt", accent=c["success"]),
            StatCard(self.tr("dash_total_amount"), icon="coins", accent=c["gold"]),
            StatCard(self.tr("dash_paid_amount"), icon="check", accent=c["success"]),
            StatCard(self.tr("dash_unpaid_amount"), icon="alert", accent=c["danger"]),
            StatCard(self.tr("dash_collection_rate"), icon="percent", accent=c["violet"]),
            StatCard(self.tr("dash_avg_invoice"), icon="bars", accent=c["teal"]),
            StatCard(self.tr("dash_cost_per_kwh"), icon="gauge", accent=c["orange"]),
            StatCard(self.tr("an_forecast_amount"), icon="trend", accent=c["violet"]),
            StatCard(self.tr("an_forecast_kwh"), icon="wave", accent=c["teal"]),
            StatCard(self.tr("an_highest_invoice"), icon="arrow-up", accent=c["danger"]),
            StatCard(self.tr("an_health_score"), icon="pulse", accent=c["accent_hi"]),
        ]
        _kpi_tt = {
            0: "tt_kpi_invoices",
            1: "tt_kpi_kwh",
            2: "tt_kpi_amount",
            3: "tt_kpi_paid_amount",
            4: "tt_kpi_unpaid_amount",
            6: "tt_kpi_avg_invoice",
            7: "tt_kpi_cost_kwh",
        }
        for i, card in enumerate(self.cards):
            if i in _kpi_tt:
                card.setToolTip(self.tr(_kpi_tt[i]))
        self.chart = BarChart()
        self.chart.setToolTip(self.tr("tt_an_chart"))
        self.trend_lbl = QLabel("")
        self.trend_lbl.setObjectName("Muted")
        self.legend_lbl = QLabel("")
        self.legend_lbl.setObjectName("Muted")
        self.alerts_lbl = QLabel("")
        self.alerts_lbl.setObjectName("Error")
        self.alerts_lbl.setWordWrap(True)
        self.alerts_lbl.setVisible(False)

        grid = CardGrid(self.cards, min_card_width=200, max_columns=4)

        top = QHBoxLayout()
        top.setSpacing(10)
        metric_lbl = QLabel(self.tr("an_metric"))
        metric_lbl.setObjectName("FieldLabel")
        range_lbl = QLabel(self.tr("an_range"))
        range_lbl.setObjectName("FieldLabel")
        self.metric_combo.setMinimumWidth(180)
        self.range_combo.setMinimumWidth(150)
        top.addWidget(metric_lbl)
        top.addWidget(self.metric_combo)
        top.addSpacing(12)
        top.addWidget(range_lbl)
        top.addWidget(self.range_combo)
        top.addStretch(1)
        self.save_img_btn = ghost_button(self.tr("an_save_image"))
        self.save_img_btn.setObjectName("Small")
        self.save_img_btn.clicked.connect(self._save_image)
        top.addWidget(self.save_img_btn)

        details = QHBoxLayout()
        details.setSpacing(12)
        details.addWidget(self._build_payment_panel(), 1)
        details.addWidget(self._build_leaders_panel(), 2)

        self.month_table = DataTable()
        self.month_table.setColumnCount(7)
        self.month_table.setHorizontalHeaderLabels([
            self.tr("an_col_month"), self.tr("an_col_count"), self.tr("an_col_kwh"),
            self.tr("an_col_amount"), self.tr("an_col_paid"), self.tr("an_col_remaining"),
            self.tr("an_col_rate"),
        ])
        configure_table(
            self.month_table,
            aligns=(Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignRight,
                    Qt.AlignmentFlag.AlignRight, Qt.AlignmentFlag.AlignRight,
                    Qt.AlignmentFlag.AlignRight, Qt.AlignmentFlag.AlignRight,
                    Qt.AlignmentFlag.AlignRight),
            widths={0: 110, 1: 92, 2: 150, 6: 132},
            stretch=(3, 4, 5),
            row_height=theme.Metrics.ROW_H, header_height=theme.Metrics.HEADER_H)
        self.month_table.set_empty_text(self.tr("an_no_data"))
        self.month_table.setMinimumHeight(190)

        month_card = QFrame()
        month_card.setObjectName("Card")
        month_layout = QVBoxLayout(month_card)
        month_layout.setContentsMargins(16, 14, 16, 16)
        month_layout.setSpacing(10)
        month_head = QHBoxLayout()
        month_title = QLabel(self.tr("an_monthly_table"))
        month_title.setObjectName("CardTitle")
        self.export_month_btn = ghost_button(self.tr("an_export_table"))
        self.export_month_btn.setToolTip(self.tr("tt_an_export_table"))
        self.export_month_btn.clicked.connect(self._export_monthly_table)
        month_head.addWidget(month_title)
        month_head.addStretch(1)
        month_head.addWidget(self.export_month_btn)
        month_layout.addLayout(month_head)
        month_layout.addWidget(self.month_table)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(
            theme.Metrics.PAGE_MARGIN, 18, theme.Metrics.PAGE_MARGIN, 18)
        layout.setSpacing(12)
        layout.addWidget(header)
        layout.addWidget(grid)
        layout.addSpacing(6)
        layout.addLayout(top)
        self.chart_card = chart_card = QFrame()
        chart_card.setObjectName("Card")
        chart_layout = QVBoxLayout(chart_card)
        chart_layout.setContentsMargins(18, 14, 18, 14)
        chart_layout.addWidget(self.chart)
        self.chart.setMinimumHeight(300)
        layout.addWidget(chart_card)
        layout.addLayout(details)
        layout.addWidget(month_card)
        layout.addWidget(self.alerts_lbl)
        layout.addWidget(self.trend_lbl)
        layout.addWidget(self.legend_lbl)
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

        self.metric_combo.currentIndexChanged.connect(self.refresh)
        self.chart.barClicked.connect(self._open_month)
        self.month_table.itemDoubleClicked.connect(self._open_month_from_table)
        self.range_combo.currentIndexChanged.connect(self.refresh)

    def _build_payment_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Card")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        title = QLabel(self.tr("an_payment_mix"))
        title.setObjectName("CardTitle")
        layout.addWidget(title)
        self.payment_donut = DonutChart()
        layout.addWidget(self.payment_donut, 1)
        return panel

    def _build_leaders_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Card")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        title = QLabel(self.tr("an_top_subscribers"))
        title.setObjectName("CardTitle")
        layout.addWidget(title)
        self.leaders_table = DataTable()
        self.leaders_table.setColumnCount(5)
        self.leaders_table.setHorizontalHeaderLabels([
            self.tr("sb_name"), self.tr("sb_account_no"), self.tr("an_col_count"),
            self.tr("an_col_amount"), self.tr("an_col_remaining"),
        ])
        configure_table(
            self.leaders_table,
            aligns=(Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignLeft,
                    Qt.AlignmentFlag.AlignRight, Qt.AlignmentFlag.AlignRight,
                    Qt.AlignmentFlag.AlignRight),
            widths={1: 122, 2: 86, 3: 132, 4: 122}, stretch=(0,),
            row_height=theme.Metrics.ROW_H, header_height=theme.Metrics.HEADER_H)
        self.leaders_table.set_empty_text(self.tr("an_no_data"))
        self.leaders_table.setMinimumHeight(170)
        layout.addWidget(self.leaders_table)
        return panel

    def refresh(self) -> None:
        invoices_all = self.app.repos["invoices"].active_snapshot()
        last_n = self.range_combo.currentData()
        invoices = self.app.analytics.filter_recent_months(invoices_all, last_n or 0)
        self._show_alerts(invoices)
        for card in self.cards:
            card.set_value("0")
            card.set_sub("")
        if not invoices:
            self.chart.set_data([], [], self.tr("an_no_data"))
            self.trend_lbl.setText("")
            self.legend_lbl.setText("")
            self.month_table.setRowCount(0)
            self.leaders_table.setRowCount(0)
            self._fill_payment_mix({})
            return

        series = self.app.analytics.series_for_months(invoices, last_n=last_n or 1000)
        metric = self.metric_combo.currentData()
        labels = [str(m[5:] + "/" + m[:4]) for m in series["labels"]]
        legend = None
        integer = False
        if metric == "kwh":
            values = series["kwh"]
            caption = self.tr("an_caption_kwh")
            secondary = None
        elif metric == "amount":
            values = series["amount"]
            secondary = series["paid"]
            caption = self.tr("an_caption_amount")
            legend = (self.tr("status_paid"), self.tr("status_unpaid"))
        else:
            values = [float(v) for v in series["count"]]
            caption = self.tr("an_caption_count")
            secondary = None
            integer = True
        self.chart.set_data(labels, values, caption, secondary, integer=integer, legend=legend,
                            keys=list(series["labels"]))
        self.trend_lbl.setText(self.tr("an_trend") + ": " + self.tr(
            {"insufficient": "an_trend_insufficient", "up": "an_trend_up",
             "down": "an_trend_down", "flat": "an_trend_flat"}.get(
                self.app.analytics.kwh_trend(invoices), "an_trend_insufficient")))

        stats = self.app.analytics.compute_stats(invoices)
        self.cards[0].set_value(str(stats["total_invoices"]))
        self.cards[1].set_value(f"{fmt_quantity(stats['total_kwh'])} {self.tr('unit_kwh')}")
        self.cards[2].set_value(money_display(stats["total_amount"]))
        self.cards[3].set_value(money_display(stats["total_paid"]))
        self.cards[4].set_value(money_display(stats["total_unpaid"]))
        rate = f"{float(stats['collection_rate']):.1f}"
        self.cards[5].set_value(f"{rate}%")
        self.cards[6].set_value(money_display(stats["avg_invoice"]))
        self.cards[7].set_value(f"{str(stats['cost_per_kwh'])} / {self.tr('unit_kwh')}")
        forecast = self.app.analytics.forecast_next_month(invoices)
        self.cards[8].set_value(money_display(forecast["amount"]))
        self.cards[8].set_sub(self.tr("an_confidence_" + forecast["confidence"]))
        self.cards[9].set_value(f"{fmt_quantity(forecast['kwh'])} {self.tr('unit_kwh')}")
        self.cards[9].set_sub(self.tr("an_next_month"))
        self.cards[10].set_value(money_display(stats["max_invoice"]))
        self.cards[11].set_value(self._health_score(stats))
        self.cards[11].set_sub(self.tr("an_health_hint"))
        self.legend_lbl.setText(self.tr("an_legend").format(
            avg=f"{fmt_quantity(stats['avg_kwh'])} {self.tr('unit_kwh')}",
            max=fmt_quantity(stats['max_kwh']),
            min=fmt_quantity(stats['min_kwh']),
            paid=str(stats["paid_count"]),
            unpaid=str(stats["unpaid_count"])))
        self._fill_payment_mix(self.app.analytics.payment_breakdown(invoices))
        self._fill_leaders(self.app.analytics.subscriber_leaders(invoices))
        self._fill_month_table(self.app.analytics.monthly_table(invoices, last_n or 0))

    def _show_alerts(self, invoices) -> None:
        alerts = self.app.analytics.anomalies(invoices)
        if alerts:
            lines = []
            for a in alerts:
                if a["type"] == "rate":
                    lines.append("— " + self.tr("an_anomaly_rate",
                                                 m=str(a["month"]), rate=str(a["rate"]),
                                                 avg=str(a["avg"])))
                else:
                    lines.append("— " + self.tr("an_anomaly_consumption",
                                                 m=str(a["month"]), kwh=str(a["kwh"]),
                                                 avg=str(a["avg"])))
            self.alerts_lbl.setText(self.tr("an_alerts") + "\n" + "\n".join(lines))
            self.alerts_lbl.setVisible(True)
        else:
            self.alerts_lbl.setText("")
            self.alerts_lbl.setVisible(False)

    def _health_score(self, stats: dict) -> str:
        total = max(int(stats["total_invoices"]), 1)
        unpaid_ratio = float(stats["unpaid_count"]) / total
        collection = float(stats["collection_rate"])
        score = max(0, min(100, int(collection - unpaid_ratio * 20)))
        return f"{score}/100"

    def _open_month(self, month_key: str) -> None:
        """A click on a bar opens the invoices of that month (the invoices page reads this)."""
        if month_key:
            self.app.pending_invoice_filter = {"month": month_key}
            self.app.navigate("invoices")

    def _open_month_from_table(self, item: QTableWidgetItem) -> None:
        row = item.row()
        m_item = self.month_table.item(row, 0)
        if m_item is not None:
            key = m_item.data(Qt.ItemDataRole.UserRole) or ""
            if key:
                self._open_month(key)

    def _export_monthly_table(self) -> None:
        rows = getattr(self, "_last_monthly_rows", None)
        if not rows:
            return
        from pathlib import Path
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("an_export_table"), "voltiva-monthly.xlsx",
            "Excel (*.xlsx);;CSV (*.csv)")
        if not path:
            return
        try:
            if path.lower().endswith(".csv"):
                from ...infrastructure.export.exporters import csv_export_monthly
                csv_export_monthly(rows, path)
            else:
                from ...infrastructure.export.exporters import excel_export_monthly
                if not path.lower().endswith(".xlsx"):
                    path += ".xlsx"
                excel_export_monthly(rows, path)
            QMessageBox.information(
                self, self.tr("success"),
                self.tr("il_export_success", path=Path(path).name))
        except Exception as exc:
            QMessageBox.warning(self, self.tr("error"), error_text(self.app, exc))

    def _save_image(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, self.tr("an_save_image"), "voltiva-chart.png", "PNG (*.png)")
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        if not self.chart_card.grab().save(path):
            QMessageBox.warning(self, self.tr("error"), self.tr("an_save_failed"))

    def _fill_payment_mix(self, breakdown: dict) -> None:
        spec = (("PAID", "status_paid", "success"),      # theme tokens: resolved when painting
                ("PARTIAL", "status_partial", "warn"),
                ("UNPAID", "status_unpaid", "danger"))
        items, total = [], 0
        for key, label_key, color in spec:
            data = breakdown.get(key, {"count": 0, "amount": None})
            count = int(data.get("count", 0) or 0)
            total += count
            amount = money_display(data["amount"]) if data.get("amount") is not None \
                else money_display(Money.zero())
            items.append((self.tr(label_key), float(count), color, f"{str(count)} — {amount}"))
        self.payment_donut.set_data(items, str(total), self.tr("dash_total_invoices"))

    def _fill_leaders(self, rows: list[dict]) -> None:
        self.leaders_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            values = [
                row["name"], row["account"], str(row["count"]),
                money_display(row["amount"]), money_display(row["unpaid"]),
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | (
                    Qt.AlignmentFlag.AlignRight if c >= 2 else Qt.AlignmentFlag.AlignLeft))
                self.leaders_table.setItem(r, c, item)

    def _fill_month_table(self, rows: list[dict]) -> None:
        self._last_monthly_rows = rows
        self.month_table.setRowCount(len(rows))
        c = theme.colors()
        for r, row in enumerate(rows):
            remaining = row["remaining"].raw
            values = [
                str(row["month"]),
                str(row["count"]),
                f"{fmt_quantity(row['kwh'])} {self.tr('unit_kwh')}",
                money_display(row["amount"]),
                money_display(row["paid"]),
                money_display(row["remaining"]),
                f"{str(row['avg_rate'])} / {self.tr('unit_kwh')}",
            ]
            for col, value in enumerate(values):
                # The chip widget paints the remaining amount; keeping the item text too
                # would draw the number twice, offset, inside the same cell.
                text = "" if col == 5 and remaining > 0 else str(value)
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | (
                    Qt.AlignmentFlag.AlignRight if col else Qt.AlignmentFlag.AlignLeft))
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row["month"])
                self.month_table.setItem(r, col, item)
            if remaining > 0:
                self.month_table.setCellWidget(r, 5, chip_cell(money_display(row["remaining"]), c["danger"]))
            else:
                # a re-refresh may keep the row but drop the chip (e.g. the month got paid)
                self.month_table.removeCellWidget(r, 5)
