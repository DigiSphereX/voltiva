from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .. import theme
from ..charts import BarChart, StatCard
from ..widgets import PageHeader, money_display, digits, currency_label, status_chip
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
        self.metric_combo.addItem(f"{self.tr('an_metric_amount')} ({currency_label()})", "amount")
        self.metric_combo.addItem(self.tr("an_metric_count"), "count")

        self.range_combo = QComboBox()
        self.range_combo.setToolTip(self.tr("tt_an_range"))
        for label, months in ((self.tr("an_range_3"), 3), (self.tr("an_range_6"), 6),
                              (self.tr("an_range_12"), 12), (self.tr("an_range_24"), 24),
                              (self.tr("an_range_all"), 0)):
            self.range_combo.addItem(label, months)

        c = theme.colors()
        self.cards = [
            StatCard(self.tr("dash_total_invoices"), icon="◈", accent=c["accent"]),
            StatCard(self.tr("dash_total_kwh"), icon="⚡", accent=c["success"]),
            StatCard(self.tr("dash_total_amount"), icon="◉", accent=c["warn"]),
            StatCard(self.tr("dash_paid_amount"), icon="✓", accent=c["success"]),
            StatCard(self.tr("dash_unpaid_amount"), icon="◌", accent=c["danger"]),
            StatCard(self.tr("dash_collection_rate"), icon="◐", accent="#8B5CF6"),
            StatCard(self.tr("dash_avg_invoice"), icon="÷", accent="#2DD4BF"),
            StatCard(self.tr("dash_cost_per_kwh"), icon="◇", accent="#F2944C"),
            StatCard(self.tr("an_forecast_amount"), icon="↗", accent="#6366F1"),
            StatCard(self.tr("an_forecast_kwh"), icon="≈", accent="#14B8A6"),
            StatCard(self.tr("an_highest_invoice"), icon="▲", accent=c["danger"]),
            StatCard(self.tr("an_health_score"), icon="◆", accent=c["accent_hi"]),
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

        grid = QGridLayout()
        grid.setSpacing(12)
        for i, card in enumerate(self.cards):
            grid.addWidget(card, i // 4, i % 4)

        top = QHBoxLayout()
        top.addWidget(QLabel(self.tr("an_metric")))
        top.addWidget(self.metric_combo)
        top.addSpacing(16)
        top.addWidget(QLabel(self.tr("an_range")))
        top.addWidget(self.range_combo)
        top.addStretch(1)

        details = QHBoxLayout()
        details.setSpacing(12)
        details.addWidget(self._build_payment_panel(), 1)
        details.addWidget(self._build_leaders_panel(), 2)

        self.month_table = QTableWidget()
        self.month_table.setColumnCount(7)
        self.month_table.setHorizontalHeaderLabels([
            self.tr("an_col_month"), self.tr("an_col_count"), self.tr("an_col_kwh"),
            self.tr("an_col_amount"), self.tr("an_col_paid"), self.tr("an_col_remaining"),
            self.tr("an_col_rate"),
        ])
        self.month_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.month_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.month_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.month_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.month_table.setAlternatingRowColors(True)
        self.month_table.verticalHeader().setVisible(False)
        self.month_table.verticalHeader().setDefaultSectionSize(38)
        self.month_table.setMinimumHeight(190)

        month_card = QFrame()
        month_card.setObjectName("Card")
        month_layout = QVBoxLayout(month_card)
        month_layout.setContentsMargins(16, 14, 16, 16)
        month_layout.setSpacing(10)
        month_title = QLabel(self.tr("an_monthly_table"))
        month_title.setObjectName("CardTitle")
        month_layout.addWidget(month_title)
        month_layout.addWidget(self.month_table)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(12)
        layout.addWidget(header)
        layout.addLayout(grid)
        layout.addSpacing(8)
        layout.addLayout(top)
        layout.addWidget(self.chart, 1)
        layout.addLayout(details)
        layout.addWidget(month_card)
        layout.addWidget(self.alerts_lbl)
        layout.addWidget(self.trend_lbl)
        layout.addWidget(self.legend_lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

        self.metric_combo.currentIndexChanged.connect(self.refresh)
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
        self.payment_rows: dict[str, QLabel] = {}
        for key in ("PAID", "PARTIAL", "UNPAID"):
            row = QHBoxLayout()
            label = QLabel(self.tr({
                "PAID": "status_paid",
                "PARTIAL": "status_partial",
                "UNPAID": "status_unpaid",
            }[key]))
            value = QLabel("0")
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            value.setObjectName("Muted")
            row.addWidget(label)
            row.addStretch(1)
            row.addWidget(value)
            layout.addLayout(row)
            self.payment_rows[key] = value
        layout.addStretch(1)
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
        self.leaders_table = QTableWidget()
        self.leaders_table.setColumnCount(5)
        self.leaders_table.setHorizontalHeaderLabels([
            self.tr("sb_name"), self.tr("sb_account_no"), self.tr("an_col_count"),
            self.tr("an_col_amount"), self.tr("an_col_remaining"),
        ])
        self.leaders_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.leaders_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.leaders_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.leaders_table.setAlternatingRowColors(True)
        self.leaders_table.verticalHeader().setVisible(False)
        self.leaders_table.verticalHeader().setDefaultSectionSize(36)
        self.leaders_table.setMinimumHeight(170)
        layout.addWidget(self.leaders_table)
        return panel

    def refresh(self) -> None:
        invoices_all = self.app.repos["invoices"].search(limit=100_000)
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
        labels = [m[5:] + "/" + m[:4] for m in series["labels"]]
        if metric == "kwh":
            values = series["kwh"]
            caption = self.tr("an_caption_kwh")
            secondary = None
        elif metric == "amount":
            values = series["amount"]
            secondary = series["paid"]
            caption = self.tr("an_caption_amount")
        else:
            values = [float(v) for v in series["count"]]
            caption = self.tr("an_caption_count")
            secondary = None
        self.chart.set_data(labels, values, caption, secondary)
        self.trend_lbl.setText(self.tr("an_trend") + ": " + self.tr(
            {"insufficient": "an_trend_insufficient", "up": "an_trend_up",
             "down": "an_trend_down", "flat": "an_trend_flat"}.get(
                self.app.analytics.kwh_trend(invoices), "an_trend_insufficient")))

        stats = self.app.analytics.compute_stats(invoices)
        self.cards[0].set_value(str(stats["total_invoices"]))
        self.cards[1].set_value(f"{digits(fmt_quantity(stats['total_kwh']))} {self.tr('unit_kwh')}")
        self.cards[2].set_value(money_display(stats["total_amount"]))
        self.cards[3].set_value(money_display(stats["total_paid"]))
        self.cards[4].set_value(money_display(stats["total_unpaid"]))
        rate = digits(f"{float(stats['collection_rate']):.1f}")
        self.cards[5].set_value(f"{rate}%")
        self.cards[6].set_value(money_display(stats["avg_invoice"]))
        self.cards[7].set_value(f"{digits(stats['cost_per_kwh'])} / {self.tr('unit_kwh')}")
        forecast = self.app.analytics.forecast_next_month(invoices)
        self.cards[8].set_value(money_display(forecast["amount"]))
        self.cards[8].set_sub(self.tr("an_confidence_" + forecast["confidence"]))
        self.cards[9].set_value(f"{digits(fmt_quantity(forecast['kwh']))} {self.tr('unit_kwh')}")
        self.cards[9].set_sub(self.tr("an_next_month"))
        self.cards[10].set_value(money_display(stats["max_invoice"]))
        self.cards[11].set_value(self._health_score(stats))
        self.cards[11].set_sub(self.tr("an_health_hint"))
        self.legend_lbl.setText(self.tr("an_legend").format(
            avg=f"{digits(fmt_quantity(stats['avg_kwh']))} {self.tr('unit_kwh')}",
            max=digits(fmt_quantity(stats['max_kwh'])),
            min=digits(fmt_quantity(stats['min_kwh'])),
            paid=digits(stats["paid_count"]),
            unpaid=digits(stats["unpaid_count"])))
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
                                                 m=a["month"], rate=a["rate"], avg=a["avg"]))
                else:
                    lines.append("— " + self.tr("an_anomaly_consumption",
                                                 m=a["month"], kwh=a["kwh"], avg=a["avg"]))
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
        return f"{digits(score)}/100"

    def _fill_payment_mix(self, breakdown: dict) -> None:
        for key, lbl in self.payment_rows.items():
            data = breakdown.get(key, {"count": 0, "amount": None})
            amount = money_display(data["amount"]) if data.get("amount") is not None else money_display(Money.zero())
            lbl.setText(f"{digits(data.get('count', 0))} — {amount}")

    def _fill_leaders(self, rows: list[dict]) -> None:
        self.leaders_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            values = [
                row["name"], row["account"], digits(row["count"]),
                money_display(row["amount"]), money_display(row["unpaid"]),
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | (
                    Qt.AlignmentFlag.AlignRight if c >= 2 else Qt.AlignmentFlag.AlignLeft))
                self.leaders_table.setItem(r, c, item)

    def _fill_month_table(self, rows: list[dict]) -> None:
        self.month_table.setRowCount(len(rows))
        c = theme.colors()
        for r, row in enumerate(rows):
            values = [
                row["month"],
                digits(row["count"]),
                f"{digits(fmt_quantity(row['kwh']))} {self.tr('unit_kwh')}",
                money_display(row["amount"]),
                money_display(row["paid"]),
                money_display(row["remaining"]),
                f"{digits(row['avg_rate'])} / {self.tr('unit_kwh')}",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | (
                    Qt.AlignmentFlag.AlignRight if col else Qt.AlignmentFlag.AlignLeft))
                self.month_table.setItem(r, col, item)
            remaining = row["remaining"].raw
            if remaining > 0:
                chip = status_chip(money_display(row["remaining"]), c["danger"])
                self.month_table.setCellWidget(r, 5, chip)
