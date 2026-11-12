from __future__ import annotations

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QComboBox, QGridLayout, QHBoxLayout, QLabel, QScrollArea,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ...application.services import CalculateInvoiceRequest
from ...domain.enums import MeterScenario, ServiceZone, SubscriberType
from ...domain.money import fmt_quantity, latin_digits
from .. import theme
from ..app_context import default_issue_dates
from ..widgets import (
    DataTable, FormRow, MoneyEdit, PageHeader, ReadingEdit, Section, configure_table,
    date_edit, error_label, error_text, ghost_button,
    money_display, muted, primary_button, success_label,
)

_STACK_BELOW = 900        # below this page width the result panel moves under the form


class NewInvoicePage(QWidget):
    def __init__(self, app, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.tr = app.tr
        self._calc = None
        self._schedule = None
        self._subscriber = None

        header = PageHeader(self.tr("ni_title"), self.tr("ni_subtitle"))

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
        self.prev_date = date_edit(QDate(prev_date.year, prev_date.month, prev_date.day))
        self.prev_date.setToolTip(self.tr("tt_ni_prev_date"))
        self.curr_date = date_edit(QDate(curr_date.year, curr_date.month, curr_date.day))
        self.curr_date.setToolTip(self.tr("tt_ni_curr_date"))
        self.prev_reading = ReadingEdit()
        self.prev_reading.setToolTip(self.tr("tt_ni_prev_reading"))
        self.curr_reading = ReadingEdit()
        self.curr_reading.setToolTip(self.tr("tt_ni_curr_reading"))
        self.multiplier = ReadingEdit()
        self.multiplier.setToolTip(self.tr("tt_ni_multiplier"))
        self.multiplier.setText("1")
        self.prev_debt = MoneyEdit()
        self.prev_debt.setToolTip(self.tr("tt_ni_prev_debt"))
        self.debt_hint = muted("")
        self.debt_hint.setWordWrap(True)
        self.debt_hint.setVisible(False)
        self._debt_autofilled = False       # True while the field still holds the suggested balance
        self.prev_debt.textEdited.connect(self._debt_edited)
        self.official_amount = MoneyEdit()
        self.official_amount.setToolTip(self.tr("tt_ni_official"))

        self.err_lbl = error_label()
        self.success_lbl = success_label()

        self.calc_btn = primary_button(self.tr("ni_calculate"))
        self.calc_btn.setToolTip(self.tr("tt_ni_calc"))
        self.save_btn = primary_button(self.tr("ni_save"))
        self.save_btn.setToolTip(self.tr("tt_ni_save"))
        self.save_btn.setEnabled(False)
        self.reset_btn = ghost_button(self.tr("ni_btn_reset"))
        self.reset_btn.setToolTip(self.tr("tt_ni_reset"))
        steps_card = Section(self.tr("ni_result"))
        self.steps_table = DataTable()
        self.steps_table.setToolTip(self.tr("tt_ni_steps"))
        self.steps_table.setColumnCount(2)
        self.steps_table.setHorizontalHeaderLabels([self.tr("col_item"), self.tr("col_value")])
        configure_table(self.steps_table, widths={0: 190}, stretch=(1,),
                        row_height=theme.Metrics.ROW_H, header_height=theme.Metrics.HEADER_H)
        self.steps_table.set_empty_text(self.tr("ni_empty_steps"))
        self.steps_table.setFixedHeight(theme.Metrics.HEADER_H + theme.Metrics.ROW_H * 4)
        steps_card.body.addWidget(self.steps_table)

        # Two columns: the form (grouped in cards) on one side, the calculation result next to it,
        # so the result is visible without scrolling past twelve full-width rows.
        sec_sub = Section(self.tr("ni_sec_subscriber"))
        for label, widget in ((self.tr("ni_account_no"), acct_widget),
                              (self.tr("ni_subscriber_name"), self.sub_name_lbl),
                              (self.tr("ni_subscriber_type"), self.type_combo),
                              (self.tr("ni_service_zone"), self.zone_combo)):
            sec_sub.add_widget(FormRow(label, widget))
        sec_read = Section(self.tr("ni_sec_reading"))
        for label, widget in ((self.tr("ni_scenario"), self.scenario_combo),
                              (self.tr("ni_prev_reading"), self.prev_reading),
                              (self.tr("ni_curr_reading"), self.curr_reading),
                              (self.tr("ni_prev_date"), self.prev_date),
                              (self.tr("ni_curr_date"), self.curr_date),
                              (self.tr("ni_multiplier"), self.multiplier)):
            sec_read.add_widget(FormRow(label, widget))
        sec_bill = Section(self.tr("ni_sec_billing"))
        sec_bill.add_widget(FormRow(self.tr("ni_prev_debt"), self.prev_debt))
        sec_bill.add_widget(self.debt_hint)
        sec_bill.add_widget(FormRow(self.tr("ni_official_amount"), self.official_amount))

        form_col = QVBoxLayout()
        form_col.setContentsMargins(0, 0, 0, 0)
        form_col.setSpacing(theme.Metrics.PAGE_SPACING)
        form_col.addWidget(sec_sub)
        form_col.addWidget(sec_read)
        form_col.addWidget(self.err_lbl)
        form_col.addWidget(self.success_lbl)
        form_col.addStretch(1)
        self.form_panel = QWidget()
        self.form_panel.setLayout(form_col)

        self.result_panel = QWidget()
        result_col = QVBoxLayout(self.result_panel)
        result_col.setContentsMargins(0, 0, 0, 0)
        result_col.setSpacing(theme.Metrics.PAGE_SPACING)
        result_col.addWidget(steps_card)
        result_col.addWidget(sec_bill)     # keeps the tall form column inside the fold
        result_col.addStretch(1)

        self._columns = QGridLayout()
        self._columns.setContentsMargins(0, 0, 0, 0)
        self._columns.setSpacing(theme.Metrics.PAGE_SPACING)
        self._columns.addWidget(self.form_panel, 0, 0)
        self._columns.addWidget(self.result_panel, 0, 1)
        self._columns.setColumnStretch(0, 5)
        self._columns.setColumnStretch(1, 4)
        self._stacked = False

        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(
            theme.Metrics.PAGE_MARGIN, 18, theme.Metrics.PAGE_MARGIN, 18)
        outer.setSpacing(theme.Metrics.PAGE_SPACING)
        outer.addWidget(header)
        outer.addLayout(self._columns)
        outer.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(container)

        # the actions stay outside the scroll area so Calculate/Save never hide below the fold
        action_bar = QWidget()
        action_bar.setObjectName("ActionBar")
        bar_layout = QHBoxLayout(action_bar)
        bar_layout.setContentsMargins(
            theme.Metrics.PAGE_MARGIN, 10, theme.Metrics.PAGE_MARGIN, 10)
        bar_layout.setSpacing(10)
        bar_layout.addStretch(1)
        bar_layout.addWidget(self.reset_btn)
        bar_layout.addWidget(self.calc_btn)
        bar_layout.addWidget(self.save_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(scroll, 1)
        layout.addWidget(action_bar)

        self.find_btn.clicked.connect(self._find_subscriber)
        self.acct_edit.returnPressed.connect(self._find_subscriber)
        for field in (self.prev_reading, self.curr_reading, self.multiplier,
                      self.prev_debt, self.official_amount):
            field.returnPressed.connect(self._do_calculate)   # Enter anywhere in the form calculates
        self.calc_btn.clicked.connect(self._do_calculate)
        self.save_btn.clicked.connect(self._do_save)
        self.reset_btn.clicked.connect(self._reset_form)

        # Creation order puts the two dates before the reading fields; tab must follow the eye.
        tab_chain = (self.acct_edit, self.find_btn, self.type_combo, self.zone_combo,
                     self.scenario_combo, self.prev_reading, self.curr_reading,
                     self.prev_date, self.curr_date, self.multiplier,
                     self.prev_debt, self.official_amount,
                     self.calc_btn, self.save_btn, self.reset_btn)
        for first, second in zip(tab_chain, tab_chain[1:]):
            self.setTabOrder(first, second)

    def refresh(self) -> None:
        pass

    def _reset_form(self) -> None:
        self.acct_edit.clear()
        self.sub_name_lbl.setText("—")
        self._subscriber = None
        self._calc = None
        self._schedule = None
        self.type_combo.setCurrentIndex(0)
        self.zone_combo.setCurrentIndex(0)
        self.scenario_combo.setCurrentIndex(0)
        prev_date, curr_date = default_issue_dates()
        self.prev_date.setDate(QDate(prev_date.year, prev_date.month, prev_date.day))
        self.curr_date.setDate(QDate(curr_date.year, curr_date.month, curr_date.day))
        self.prev_reading.clear()
        self.curr_reading.clear()
        self.multiplier.setText("1")
        self.prev_debt.clear()
        self.debt_hint.setVisible(False)
        self._debt_autofilled = False
        self.official_amount.clear()
        self.err_lbl.setVisible(False)
        self.success_lbl.setVisible(False)
        self.steps_table.clearContents()
        self.steps_table.setRowCount(0)
        self.steps_table.setFixedHeight(theme.Metrics.HEADER_H + theme.Metrics.ROW_H * 4)
        self.save_btn.setEnabled(False)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        stacked = self.width() < _STACK_BELOW
        if stacked == self._stacked:
            return
        self._stacked = stacked
        for panel in (self.form_panel, self.result_panel):
            self._columns.removeWidget(panel)
        if stacked:
            self._columns.addWidget(self.form_panel, 0, 0)
            self._columns.addWidget(self.result_panel, 1, 0)
            self._columns.setColumnStretch(0, 1)
            self._columns.setColumnStretch(1, 0)
        else:
            self._columns.addWidget(self.form_panel, 0, 0)
            self._columns.addWidget(self.result_panel, 0, 1)
            self._columns.setColumnStretch(0, 5)
            self._columns.setColumnStretch(1, 4)

    def _find_subscriber(self) -> None:
        acct = latin_digits(self.acct_edit.text().strip())
        if not acct:
            return
        try:
            sub = self.app.subscribers.find_or_create(acct)
            self._subscriber = sub
            self.sub_name_lbl.setText(sub.name)
            for i in range(self.type_combo.count()):
                if self.type_combo.itemData(i) == sub.subscriber_type:
                    self.type_combo.setCurrentIndex(i)
                    break
            self._suggest_debt(sub)
        except Exception as exc:  # noqa: BLE001
            self._subscriber = None
            self.err_lbl.setText(error_text(self.app, exc))
            self.err_lbl.setVisible(True)

    def _suggest_debt(self, sub) -> None:
        """Pre-fill the previous debt with the subscriber's unpaid balance (still editable).

        A value the user typed is never overwritten; a value WE filled for a previous
        subscriber is replaced.
        """
        if self.prev_debt.text().strip() and not self._debt_autofilled:
            return
        suggested = self.app.invoices.suggested_previous_debt(sub.id) if sub.id else None
        if suggested is not None and suggested.raw > 0:
            self.prev_debt.set_money(suggested)
            self._debt_autofilled = True
            self.debt_hint.setText(self.tr("ni_debt_prefilled", amount=money_display(suggested)))
            self.debt_hint.setVisible(True)
        else:
            if self._debt_autofilled:
                self.prev_debt.clear()
            self._debt_autofilled = False
            self.debt_hint.setVisible(False)

    def _debt_edited(self, _text: str) -> None:
        self._debt_autofilled = False
        self.debt_hint.setVisible(False)

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
                         f"{fmt_quantity(calc.reading.previous_reading)} → {fmt_quantity(calc.reading.current_reading)} = "
                         f"{fmt_quantity(calc.reading.consumption_kwh)} {self.tr('unit_kwh')}"))
        rows.append((self.tr("tariff_step"), money_display(calc.energy_cost)))
        for step in calc.steps:
            label = self.app.i18n.step_label(step.label)
            value = step.value_display
            if step.label == "Status" and calc.reading is not None:
                # the scenario is an enum: show it through the active language
                value = self.app.i18n.enum_label(calc.reading.scenario)
            else:
                # The domain emits English unit words; swap them for the active language.
                value = value.replace(" days", f" {self.tr('unit_days')}")
            rows.append((label, value))
        if calc.comparison and calc.comparison.status.value != "NOT_COMPARED":
            rows.append((self.tr("vk_official"), money_display(calc.comparison.official_amount)))
            rows.append((self.tr("vk_calculated"), money_display(calc.comparison.calculated_amount)))
            rows.append((self.tr("vk_diff"), money_display(calc.comparison.diff)))
            status_key = "status_" + calc.comparison.status.value.lower()
            rows.append((self.tr("vk_status"), self.tr(status_key)))

        self.steps_table.setRowCount(len(rows))
        for i, (label, value) in enumerate(rows):
            label_item = QTableWidgetItem(str(label))
            label_item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            value_item = QTableWidgetItem(str(value))
            value_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.steps_table.setItem(i, 0, label_item)
            self.steps_table.setItem(i, 1, value_item)
        self.steps_table.setFixedHeight(
            theme.Metrics.HEADER_H + max(len(rows), 1) * theme.Metrics.ROW_H + 2)

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