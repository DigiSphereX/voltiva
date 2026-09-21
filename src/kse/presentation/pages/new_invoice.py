from __future__ import annotations

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (
    QComboBox, QDateEdit, QHBoxLayout, QHeaderView, QLabel, QScrollArea,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ...application.services import CalculateInvoiceRequest
from ...domain.enums import MeterScenario, ServiceZone, SubscriberType
from ...domain.money import Money
from ...domain.models import InvoiceCharge
from ..app_context import default_issue_dates
from ..widgets import (
    FormRow, MoneyEdit, ReadingEdit, Section, primary_button, error_label, success_label, money_display,
    error_text, digits, currency_label,
)


class NewInvoicePage(QWidget):
    def __init__(self, app, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.tr = app.tr
        self._calc = None
        self._schedule = None
        self._subscriber = None

        title = QLabel(self.tr("ni_title"))
        title.setObjectName("PageTitle")

        self.acct_edit = ReadingEdit()
        self.acct_edit.setToolTip(self.tr("tt_ni_account"))
        self.acct_edit.setPlaceholderText("1201234567")
        self.find_btn = primary_button(self.tr("ni_find_subscriber"))
        self.find_btn.setToolTip(self.tr("tt_ni_find"))
        acct_widget = QWidget()
        acct_layout = QHBoxLayout(acct_widget)
        acct_layout.setContentsMargins(0, 0, 0, 0)
        acct_layout.addWidget(self.acct_edit, 1)
        acct_layout.addWidget(self.find_btn, 0)

        self.sub_name_lbl = QLabel("—")

        self.type_combo = QComboBox()
        self.type_combo.setToolTip(self.tr("tt_ni_type"))
        for t in SubscriberType:
            self.type_combo.addItem(app.i18n.enum_label(t), t)

        self.zone_combo = QComboBox()
        self.zone_combo.setToolTip(self.tr("tt_ni_zone"))
        for z in ServiceZone:
            self.zone_combo.addItem(app.i18n.enum_label(z), z)

        self.scenario_combo = QComboBox()
        self.scenario_combo.setToolTip(self.tr("tt_ni_scenario"))
        for s in MeterScenario:
            self.scenario_combo.addItem(app.i18n.enum_label(s), s)

        prev_date, curr_date = default_issue_dates()
        self.prev_date = QDateEdit(QDate(prev_date.year, prev_date.month, prev_date.day))
        self.prev_date.setToolTip(self.tr("tt_ni_prev_date"))
        self.prev_date.setCalendarPopup(True)
        self.curr_date = QDateEdit(QDate(curr_date.year, curr_date.month, curr_date.day))
        self.curr_date.setToolTip(self.tr("tt_ni_curr_date"))
        self.curr_date.setCalendarPopup(True)
        self.prev_reading = ReadingEdit()
        self.prev_reading.setToolTip(self.tr("tt_ni_prev_reading"))
        self.curr_reading = ReadingEdit()
        self.curr_reading.setToolTip(self.tr("tt_ni_curr_reading"))
        self.multiplier = ReadingEdit()
        self.multiplier.setToolTip(self.tr("tt_ni_multiplier"))
        self.multiplier.setText("1")
        self.prev_debt = MoneyEdit()
        self.prev_debt.setToolTip(self.tr("tt_ni_prev_debt"))
        self.official_amount = MoneyEdit()
        self.official_amount.setToolTip(self.tr("tt_ni_official"))

        self.err_lbl = error_label()
        self.success_lbl = success_label()

        self.calc_btn = primary_button(self.tr("ni_calculate"))
        self.calc_btn.setToolTip(self.tr("tt_ni_calc"))
        self.save_btn = primary_button(self.tr("ni_save"))
        self.save_btn.setToolTip(self.tr("tt_ni_save"))
        self.save_btn.setEnabled(False)
        buttons = QWidget()
        btn_layout = QHBoxLayout(buttons)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.addWidget(self.calc_btn)
        btn_layout.addWidget(self.save_btn)

        steps_card = Section(self.tr("ni_result"))
        self.steps_table = QTableWidget()
        self.steps_table.setToolTip(self.tr("tt_ni_steps"))
        self.steps_table.setColumnCount(2)
        self.steps_table.setHorizontalHeaderLabels([self.tr("reading_step"), ""])
        self.steps_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.steps_table.verticalHeader().setDefaultSectionSize(34)
        self.steps_table.verticalHeader().setVisible(False)
        steps_card.add_widget(self.steps_table)

        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(24, 16, 24, 16)
        outer.setSpacing(12)
        outer.addWidget(title)
        outer.addWidget(FormRow(self.tr("ni_account_no"), acct_widget))
        outer.addWidget(FormRow(self.tr("ni_subscriber_name"), self.sub_name_lbl))
        outer.addWidget(FormRow(self.tr("ni_subscriber_type"), self.type_combo))
        outer.addWidget(FormRow(self.tr("ni_service_zone"), self.zone_combo))
        outer.addWidget(FormRow(self.tr("ni_scenario"), self.scenario_combo))
        outer.addWidget(FormRow(self.tr("ni_prev_reading"), self.prev_reading))
        outer.addWidget(FormRow(self.tr("ni_curr_reading"), self.curr_reading))
        outer.addWidget(FormRow(self.tr("ni_prev_date"), self.prev_date))
        outer.addWidget(FormRow(self.tr("ni_curr_date"), self.curr_date))
        outer.addWidget(FormRow(self.tr("ni_multiplier"), self.multiplier))
        outer.addWidget(FormRow(self.tr("ni_prev_debt"), self.prev_debt))
        outer.addWidget(FormRow(self.tr("ni_official_amount"), self.official_amount))
        outer.addWidget(self.err_lbl)
        outer.addWidget(self.success_lbl)
        outer.addWidget(buttons)
        outer.addWidget(steps_card)
        outer.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(container)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

        self.find_btn.clicked.connect(self._find_subscriber)
        self.calc_btn.clicked.connect(self._do_calculate)
        self.save_btn.clicked.connect(self._do_save)

    def refresh(self) -> None:
        pass

    def _find_subscriber(self) -> None:
        acct = self.acct_edit.text().strip()
        if not acct:
            return
        sub = self.app.subscribers.find_or_create(acct)
        self._subscriber = sub
        self.sub_name_lbl.setText(sub.name)
        for i in range(self.type_combo.count()):
            if self.type_combo.itemData(i) == sub.subscriber_type:
                self.type_combo.setCurrentIndex(i)
                break

    def _do_calculate(self) -> None:
        self.err_lbl.setVisible(False)
        self.success_lbl.setVisible(False)
        self.steps_table.setRowCount(0)
        self.save_btn.setEnabled(False)
        try:
            prev_dt = self.prev_date.date().toPyDate()
            curr_dt = self.curr_date.date().toPyDate()
            req = CalculateInvoiceRequest(
                subscriber_type=self.type_combo.currentData(),
                service_zone=self.zone_combo.currentData(),
                previous_reading=self.prev_reading.reading(),
                current_reading=self.curr_reading.reading(),
                previous_read_date=prev_dt,
                current_read_date=curr_dt,
                meter_multiplier=self.multiplier.reading(),
                scenario=self.scenario_combo.currentData(),
                previous_debt=self.prev_debt.money(),
                official_amount=self.official_amount.money(),
            )
            calc, schedule = self.app.invoices.calculate(req)
            self._calc = calc
            self._schedule = schedule
            self._display_steps(calc)
            self.success_lbl.setText(self.tr("ni_result") + f": {money_display(calc.total_due)}")
            self.success_lbl.setVisible(True)
            self.save_btn.setEnabled(True)
        except Exception as exc:
            self.err_lbl.setText(error_text(self.app, exc))
            self.err_lbl.setVisible(True)

    def _display_steps(self, calc) -> None:
        rows = []
        if calc.reading:
            rows.append((self.tr("reading_step"),
                         f"{digits(calc.reading.previous_reading)} → {digits(calc.reading.current_reading)} = "
                         f"{digits(calc.reading.consumption_kwh)} {self.tr('unit_kwh')}"))
        rows.append((self.tr("tariff_step"), money_display(calc.energy_cost)))
        use_ar = self.app.current_digits() == "arabic"
        for step in calc.steps:
            label = self.app.i18n.step_label(step.label_ar)
            value = step.value_display
            if use_ar:
                value = digits(value)
            else:
                value = value.replace(" د.ع", f" {currency_label()}").replace(" يوماً", " days")
            rows.append((label, value))
        if calc.comparison and calc.comparison.status.value != "NOT_COMPARED":
            rows.append((self.tr("vk_official"), money_display(calc.comparison.official_amount)))
            rows.append((self.tr("vk_calculated"), money_display(calc.comparison.calculated_amount)))
            rows.append((self.tr("vk_diff"), money_display(calc.comparison.diff)))
            status_key = "status_" + calc.comparison.status.value.lower()
            rows.append((self.tr("vk_status"), self.tr(status_key)))

        self.steps_table.setRowCount(len(rows))
        for i, (label, value) in enumerate(rows):
            self.steps_table.setItem(i, 0, QTableWidgetItem(str(label)))
            self.steps_table.setItem(i, 1, QTableWidgetItem(str(value)))

    def _do_save(self) -> None:
        if not self._calc or not self._schedule:
            return
        try:
            invoice = self.app.invoices.save_calculation(
                self._calc,
                self._schedule,
                self._subscriber,
                issue_date=self.curr_date.date().toPyDate(),
                previous_read_date=self.prev_date.date().toPyDate(),
                current_read_date=self.curr_date.date().toPyDate(),
                official_amount=self.official_amount.money(),
                scenario=self.scenario_combo.currentData(),
            )
            self.success_lbl.setText(
                f"{self.tr('success')}: {invoice.invoice_no} — {money_display(invoice.total_due)}")
            self.success_lbl.setVisible(True)
            self.save_btn.setEnabled(False)
        except Exception as exc:
            self.err_lbl.setText(error_text(self.app, exc))
            self.err_lbl.setVisible(True)