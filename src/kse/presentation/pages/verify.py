from __future__ import annotations

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (
    QComboBox, QDateEdit, QHBoxLayout, QHeaderView, QLabel, QScrollArea,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ...application.services import CalculateInvoiceRequest
from ...domain.enums import MeterScenario, SubscriberType
from ...domain.money import Money
from ..app_context import default_issue_dates
from ..widgets import (
    FormRow, MoneyEdit, ReadingEdit, primary_button, money_display, error_label, success_label,
    error_text,
)


class VerifyPage(QWidget):
    def __init__(self, app, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.tr = app.tr

        title = QLabel(self.tr("vk_title"))
        title.setObjectName("PageTitle")

        self.type_combo = QComboBox()
        for t in SubscriberType:
            self.type_combo.addItem(app.i18n.enum_label(t), t)
        self.scenario_combo = QComboBox()
        for s in MeterScenario:
            self.scenario_combo.addItem(app.i18n.enum_label(s), s)

        prev_date, curr_date = default_issue_dates()
        self.prev_date = QDateEdit(QDate(prev_date.year, prev_date.month, prev_date.day))
        self.prev_date.setCalendarPopup(True)
        self.curr_date = QDateEdit(QDate(curr_date.year, curr_date.month, curr_date.day))
        self.curr_date.setCalendarPopup(True)
        self.prev_reading = ReadingEdit()
        self.curr_reading = ReadingEdit()
        self.official_amount = MoneyEdit()

        verify_btn = primary_button(self.tr("vk_btn_verify"))
        verify_btn.setToolTip(self.tr("tt_vk_verify"))

        self.err_lbl = error_label()
        self.result_table = QTableWidget()
        self.result_table.setToolTip(self.tr("tt_vk_table"))
        self.result_table.setColumnCount(2)
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.result_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(24, 16, 24, 16)
        outer.setSpacing(12)
        outer.addWidget(title)
        outer.addWidget(FormRow(self.tr("ni_subscriber_type"), self.type_combo))
        outer.addWidget(FormRow(self.tr("ni_scenario"), self.scenario_combo))
        outer.addWidget(FormRow(self.tr("ni_prev_reading"), self.prev_reading))
        outer.addWidget(FormRow(self.tr("ni_curr_reading"), self.curr_reading))
        outer.addWidget(FormRow(self.tr("ni_prev_date"), self.prev_date))
        outer.addWidget(FormRow(self.tr("ni_curr_date"), self.curr_date))
        outer.addWidget(FormRow(self.tr("vk_official"), self.official_amount))
        outer.addWidget(self.err_lbl)
        outer.addWidget(verify_btn)
        outer.addWidget(self.result_table)
        outer.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(container)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

        verify_btn.clicked.connect(self._verify)

    def refresh(self) -> None:
        pass

    def _verify(self) -> None:
        self.err_lbl.setVisible(False)
        self.result_table.setRowCount(0)
        try:
            prev_dt = self.prev_date.date().toPyDate()
            curr_dt = self.curr_date.date().toPyDate()
            req = CalculateInvoiceRequest(
                subscriber_type=self.type_combo.currentData(),
                previous_reading=self.prev_reading.reading(),
                current_reading=self.curr_reading.reading(),
                previous_read_date=prev_dt,
                current_read_date=curr_dt,
                scenario=self.scenario_combo.currentData(),
                official_amount=self.official_amount.money(),
            )
            result = self.app.invoices.verify(req)
            if result.report.issues:
                messages = ", ".join(i.localized(self.tr) for i in result.report.issues)
                self.err_lbl.setText(messages)
                self.err_lbl.setVisible(True)
                return
            calc = result.calc
            if calc is None:
                self.err_lbl.setText(self.tr("no_data"))
                self.err_lbl.setVisible(True)
                return

            rows = [
                (self.tr("vk_calculated"), money_display(calc.total_due)),
            ]
            if calc.comparison:
                cmp = calc.comparison
                rows += [
                    (self.tr("vk_official"), money_display(cmp.official_amount)),
                    (self.tr("vk_diff"), money_display(cmp.diff)),
                    (self.tr("vk_ratio"), f"{cmp.ratio_pct:.1f}%"),
                    (self.tr("vk_status"), self.tr("status_" + cmp.status.value.lower())),
                ]
                for cause in cmp.possible_causes:
                    rows.append(("", cause))
            self.result_table.setRowCount(len(rows))
            for i, (label, value) in enumerate(rows):
                self.result_table.setItem(i, 0, QTableWidgetItem(str(label)))
                self.result_table.setItem(i, 1, QTableWidgetItem(str(value)))
        except Exception as exc:
            self.err_lbl.setText(error_text(self.app, exc))
            self.err_lbl.setVisible(True)