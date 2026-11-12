from __future__ import annotations

from html import escape

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from .. import theme
from ..charts import StatCard
from ..widgets import CardGrid, DataTable, chip_cell, configure_table, money_display
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
        tc = theme.colors()  # theme tokens: correct contrast in BOTH light and dark
        self.cards = [
            StatCard(self.tr("dash_total_invoices"), icon="document", accent=tc["accent"]),
            StatCard(self.tr("dash_total_kwh"), icon="bolt", accent=tc["success"]),
            StatCard(self.tr("dash_total_amount"), icon="coins", accent=tc["gold"]),
            StatCard(self.tr("dash_paid_amount"), icon="check", accent=tc["success"]),
            StatCard(self.tr("dash_unpaid_amount"), icon="alert", accent=tc["danger"]),
            StatCard(self.tr("dash_unpaid_count"), icon="clock", accent=tc["orange"]),
            StatCard(self.tr("dash_avg_invoice"), icon="bars", accent=tc["violet"]),
            StatCard(self.tr("dash_cost_per_kwh"), icon="gauge", accent=tc["teal"]),
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
        self.card_grid = CardGrid(self.cards, min_card_width=200, max_columns=4)

        # recent invoices
        recent = QFrame()
        recent.setObjectName("Card")
        recent_layout = QVBoxLayout(recent)
        recent_layout.setContentsMargins(18, 15, 18, 18)
        recent_layout.setSpacing(12)

        recent_head = QHBoxLayout()
        recent_head.setSpacing(10)
        recent_title = QLabel(self.tr("dash_recent"))
        recent_title.setObjectName("CardTitle")
        view_all = QPushButton(self.tr("dash_recent_view_all"))
        view_all.setObjectName("Small")
        view_all.setToolTip(self.tr("tt_dash_view_all"))
        view_all.clicked.connect(lambda: app.navigate("invoices"))
        recent_head.addWidget(recent_title)
        recent_head.addStretch(1)
        recent_head.addWidget(view_all)

        self.recent_table = DataTable()
        self.recent_table.setToolTip(self.tr("tt_dash_recent"))
        self.recent_table.setColumnCount(5)
        self.recent_table.setHorizontalHeaderLabels([
            self.tr("dash_recent_no"), self.tr("dash_recent_date"),
            self.tr("dash_recent_name"), self.tr("dash_recent_amount"),
            self.tr("dash_recent_status"),
        ])
        configure_table(
            self.recent_table,
            aligns=(Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignLeft,
                    Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignRight,
                    Qt.AlignmentFlag.AlignHCenter),
            widths={0: 152, 1: 112, 3: 148, 4: 112}, stretch=(2,),
            row_height=theme.Metrics.ROW_H, header_height=theme.Metrics.HEADER_H)
        self.recent_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.recent_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.recent_table.set_empty_text(self.tr("il_none"))
        self.recent_table.doubleClicked.connect(self._open_recent)
        self.recent_table.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

        recent_layout.addLayout(recent_head)
        recent_layout.addWidget(self.recent_table)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(
            theme.Metrics.PAGE_MARGIN, 18, theme.Metrics.PAGE_MARGIN, 18)
        layout.setSpacing(theme.Metrics.PAGE_SPACING)
        layout.addWidget(hero)
        layout.addWidget(self.card_grid)
        layout.addWidget(recent)
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

    def refresh(self) -> None:
        stats = self.app.analytics.dashboard()
        self.cards[0].set_value(str(stats["total_invoices"]))
        self.cards[1].set_value(f"{fmt_quantity(stats['total_kwh'])} {self.tr('unit_kwh')}")
        self.cards[2].set_value(money_display(stats["total_amount"]))
        self.cards[3].set_value(money_display(stats["total_paid"]))
        self.cards[4].set_value(money_display(stats["total_unpaid"]))
        self.cards[5].set_value(str(stats["unpaid_count"]))
        self.cards[6].set_value(money_display(stats["avg_invoice"]))
        self.cards[7].set_value(f"{str(stats['cost_per_kwh'])} / {self.tr('unit_kwh')}")

        c = self.app.repos["invoices"].list_recent(limit=5)
        # Text was red/green on the blue-purple hero (contrast 1.1-2.3:1, unreadable).
        # Now: white text on the QSS dark overlay, with the status colour as a pale dot.
        rate = f"{float(stats['collection_rate']):.1f}"
        self._set_hero_chip(
            self.unpaid_chip, "#FFB4B2",
            f"{self.tr('dash_unpaid_count')}: {str(stats['unpaid_count'])} — {money_display(stats['total_unpaid'])}")
        self._set_hero_chip(self.rate_chip, "#8DF0C8", f"{self.tr('dash_collection_rate')}: {rate}%")

        self._fill_recent(c)

    @staticmethod
    def _set_hero_chip(label: QLabel, dot_color: str, text: str) -> None:
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setText(f'<span style="color:{dot_color}">●</span>&nbsp;&nbsp;{escape(text)}')

    def _fill_recent(self, invoices) -> None:
        c = theme.colors()
        self.recent_table.setRowCount(len(invoices))
        right = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        left = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        for row, inv in enumerate(invoices):
            paid = inv.payment_status
            if paid == PaymentStatus.PAID:
                chip_text, chip_color = self.tr("status_paid"), c["success"]
            elif paid == PaymentStatus.PARTIAL:
                chip_text, chip_color = self.tr("status_partial"), c["warn"]
            else:
                chip_text, chip_color = self.tr("status_unpaid"), c["danger"]
            cells = [
                (inv.invoice_no or "—", left),
                (inv.issue_date.strftime("%d/%m/%Y"), left),
                (inv.subscriber_name or inv.account_no, left),
                (money_display(inv.total_due), right),
            ]
            for col, (text, align) in enumerate(cells):
                item = QTableWidgetItem(str(text))
                item.setTextAlignment(align)
                item.setForeground(QColor(c["text"]))
                if col == 0:
                    font = QFont(item.font())
                    font.setWeight(QFont.Weight.DemiBold)
                    item.setFont(font)
                self.recent_table.setItem(row, col, item)
            self.recent_table.setCellWidget(row, 4, chip_cell(chip_text, chip_color))
            self.recent_table.setRowHeight(row, theme.Metrics.ROW_H)
        rows = max(len(invoices), 1)
        visible_height = theme.Metrics.HEADER_H + rows * theme.Metrics.ROW_H + 2
        self.recent_table.setFixedHeight(visible_height if invoices else max(visible_height, 150))

    def _open_recent(self, index) -> None:
        inv = self.app.repos["invoices"].list_recent(limit=5)
        if 0 <= index.row() < len(inv) and inv[index.row()].id is not None:
            self.app.open_invoice_detail(inv[index.row()].id)