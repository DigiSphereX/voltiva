from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .. import theme
from ..charts import StatCard
from ..widgets import money_display, status_chip, digits
from ...domain.enums import PaymentStatus
from ...domain.money import fmt_quantity


class DashboardPage(QWidget):
    def __init__(self, app, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.tr = app.tr

        # hero banner
        hero = QFrame()
        hero.setObjectName("Hero")
        hero.setMinimumHeight(140)
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(26, 20, 26, 20)
        hero_layout.setSpacing(18)

        text_col = QVBoxLayout()
        text_col.setSpacing(4)
        self.hero_title = QLabel(self.tr("dash_hero_greet"))
        self.hero_title.setObjectName("HeroTitle")
        self.hero_sub = QLabel(self.tr("dash_hero_sub"))
        self.hero_sub.setObjectName("HeroSub")
        self.hero_sub.setWordWrap(True)
        actions = QHBoxLayout()
        actions.setSpacing(10)
        new_btn = QPushButton(self.tr("dash_new_invoice"))
        new_btn.setObjectName("Primary")
        new_btn.setToolTip(self.tr("tt_dash_new"))
        new_btn.clicked.connect(lambda: app.navigate("new_invoice"))
        review_btn = QPushButton(self.tr("dash_monthly_review"))
        review_btn.setObjectName("GhostOnHero")
        review_btn.setToolTip(self.tr("tt_dash_review"))
        review_btn.clicked.connect(lambda: app.navigate("review"))
        actions.addWidget(new_btn)
        actions.addWidget(review_btn)
        actions.addStretch(1)
        text_col.addWidget(self.hero_title)
        text_col.addWidget(self.hero_sub)
        text_col.addSpacing(8)
        text_col.addLayout(actions)

        self.unpaid_chip = QLabel("")
        self.unpaid_chip.setObjectName("HeroChip")
        self.unpaid_chip.setToolTip(self.tr("tt_dash_unpaid_chip"))
        self.rate_chip = QLabel("")
        self.rate_chip.setObjectName("HeroChip")
        self.rate_chip.setToolTip(self.tr("tt_dash_rate_chip"))
        chips_col = QVBoxLayout()
        chips_col.setSpacing(10)
        chips_col.addWidget(self.unpaid_chip)
        chips_col.addWidget(self.rate_chip)
        chips_col.addStretch(1)

        hero_layout.addLayout(text_col, 1)
        hero_layout.addLayout(chips_col)

        # KPI cards
        self.cards = [
            StatCard(self.tr("dash_total_invoices"), icon="◈",
                     accent="#3D6CFF"),
            StatCard(self.tr("dash_total_kwh"), icon="⚡",
                     accent="#2FC290"),
            StatCard(self.tr("dash_total_amount"), icon="◉",
                     accent="#F2B04C"),
            StatCard(self.tr("dash_paid_amount"), icon="✓",
                     accent="#27C08A"),
            StatCard(self.tr("dash_unpaid_amount"), icon="◌",
                     accent="#F0524F"),
            StatCard(self.tr("dash_unpaid_count"), icon="◐",
                     accent="#F2944C"),
            StatCard(self.tr("dash_avg_invoice"), icon="◐",
                     accent="#8B5CF6"),
            StatCard(self.tr("dash_cost_per_kwh"), icon="÷",
                     accent="#2DD4BF"),
        ]
        _kpi_tt = {
            0: "tt_kpi_invoices",
            1: "tt_kpi_kwh",
            2: "tt_kpi_amount",
            3: "tt_kpi_paid_amount",
            4: "tt_kpi_unpaid_amount",
            5: "tt_kpi_unpaid_count",
            6: "tt_kpi_avg_invoice",
            7: "tt_kpi_cost_kwh",
        }
        for i, card in enumerate(self.cards):
            card.setToolTip(self.tr(_kpi_tt[i]))
        grid = QGridLayout()
        grid.setSpacing(12)
        for i, card in enumerate(self.cards):
            grid.addWidget(card, i // 4, i % 4)

        # recent invoices
        recent = QFrame()
        recent.setObjectName("Card")
        recent_layout = QVBoxLayout(recent)
        recent_layout.setContentsMargins(16, 14, 16, 16)
        recent_layout.setSpacing(12)

        recent_head = QHBoxLayout()
        recent_title = QLabel(self.tr("dash_recent"))
        recent_title.setObjectName("CardTitle")
        view_all = QPushButton(self.tr("dash_recent_view_all"))
        view_all.setObjectName("Small")
        view_all.setToolTip(self.tr("tt_dash_view_all"))
        view_all.clicked.connect(lambda: app.navigate("invoices"))
        recent_head.addWidget(recent_title)
        recent_head.addStretch(1)
        recent_head.addWidget(view_all)

        self.recent_table = QTableWidget()
        self.recent_table.setToolTip(self.tr("tt_dash_recent"))
        self.recent_table.setColumnCount(5)
        self.recent_table.setHorizontalHeaderLabels([
            self.tr("dash_recent_no"), self.tr("dash_recent_date"),
            self.tr("dash_recent_name"), self.tr("dash_recent_amount"),
            self.tr("dash_recent_status"),
        ])
        self.recent_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch)
        self.recent_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.recent_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.recent_table.setAlternatingRowColors(True)
        self.recent_table.verticalHeader().setVisible(False)
        self.recent_table.verticalHeader().setDefaultSectionSize(40)
        self.recent_table.setMinimumHeight(220)
        self.recent_table.doubleClicked.connect(self._open_recent)
        self.recent_table.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

        recent_layout.addLayout(recent_head)
        recent_layout.addWidget(self.recent_table, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(14)
        layout.addWidget(hero)
        layout.addLayout(grid)
        layout.addWidget(recent, 1)

    def refresh(self) -> None:
        stats = self.app.analytics.dashboard()
        self.cards[0].set_value(str(stats["total_invoices"]))
        self.cards[1].set_value(f"{digits(fmt_quantity(stats['total_kwh']))} {self.tr('unit_kwh')}")
        self.cards[2].set_value(money_display(stats["total_amount"]))
        self.cards[3].set_value(money_display(stats["total_paid"]))
        self.cards[4].set_value(money_display(stats["total_unpaid"]))
        self.cards[5].set_value(str(stats["unpaid_count"]))
        self.cards[6].set_value(money_display(stats["avg_invoice"]))
        self.cards[7].set_value(f"{digits(stats['cost_per_kwh'])} / {self.tr('unit_kwh')}")

        c = self.app.repos["invoices"].list_recent(limit=5)
        tc = theme.colors()
        self.unpaid_chip.setText(
            f"{self.tr('dash_unpaid_count')}: {stats['unpaid_count']} — {money_display(stats['total_unpaid'])}")
        self.unpaid_chip.setStyleSheet(
            f"background-color: {tc['danger_rgba']}; color: {tc['danger']};"
            "border-radius: 8px; padding: 6px 12px; font-size: 12px; font-weight: 700;")
        rate = digits(f"{float(stats['collection_rate']):.1f}")
        self.rate_chip.setText(f"{self.tr('dash_collection_rate')}: {rate}%")
        self.rate_chip.setStyleSheet(
            f"background-color: {tc['success_rgba']}; color: {tc['success']};"
            "border-radius: 8px; padding: 6px 12px; font-size: 12px; font-weight: 700;")

        self._fill_recent(c)

    def _fill_recent(self, invoices) -> None:
        from .. import theme

        c = theme.colors()
        self.recent_table.setRowCount(len(invoices))
        for row, inv in enumerate(invoices):
            paid = inv.payment_status
            if paid == PaymentStatus.PAID:
                chip_text, chip_color = self.tr("status_paid"), c["success"]
            elif paid == PaymentStatus.PARTIAL:
                chip_text, chip_color = self.tr("status_partial"), c["warn"]
            else:
                chip_text, chip_color = self.tr("status_unpaid"), c["danger"]
            items = [
                inv.invoice_no or "—",
                inv.issue_date.strftime("%d/%m/%Y"),
                inv.subscriber_name or inv.account_no,
                money_display(inv.total_due),
            ]
            for col, text in enumerate(items):
                item = QTableWidgetItem(str(text))
                item.setForeground(__import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(c["text"]))
                self.recent_table.setItem(row, col, item)
            chip = status_chip(chip_text, chip_color)
            self.recent_table.setCellWidget(row, 4, chip)
            self.recent_table.setRowHeight(row, 38)

    def _open_recent(self, index) -> None:
        inv = self.app.repos["invoices"].list_recent(limit=5)
        if 0 <= index.row() < len(inv) and inv[index.row()].id is not None:
            self.app.open_invoice_detail(inv[index.row()].id)