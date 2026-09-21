from __future__ import annotations

import datetime as dt
from decimal import Decimal

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton,
    QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ...domain.enums import ChargeCategory, DataSource, ServiceZone, SubscriberType, TariffMethod
from ...domain.models import TariffFee, TariffSchedule, TariffTier
from ...domain.money import Money
from ..widgets import MoneyEdit, danger_small_button, primary_button, small_button, error_text


class TariffDialog(QDialog):
    def __init__(self, app, schedule: TariffSchedule | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.tr = app.tr
        self._schedule = schedule
        self.setWindowTitle(self.tr("tf_save"))
        self.setMinimumWidth(620)

        self.name_ar = QLineEdit(schedule.name_ar if schedule else "")
        self.name_ar.setToolTip(self.tr("tt_tf_name_ar"))
        self.name_en = QLineEdit(schedule.name_en if schedule else "")
        self.name_en.setToolTip(self.tr("tt_tf_name_en"))
        self.type_combo = QComboBox()
        self.type_combo.setToolTip(self.tr("tt_tf_type"))
        for t in SubscriberType:
            self.type_combo.addItem(app.i18n.enum_label(t), t)
        self.method_combo = QComboBox()
        self.method_combo.setToolTip(self.tr("tt_tf_method"))
        for m in TariffMethod:
            self.method_combo.addItem(app.i18n.enum_label(m), m)
        self.zone_combo = QComboBox()
        self.zone_combo.setToolTip(self.tr("tt_tf_zone"))
        for z in ServiceZone:
            self.zone_combo.addItem(app.i18n.enum_label(z), z)
        if schedule:
            self.type_combo.setCurrentIndex(self.type_combo.findData(schedule.subscriber_type))
            self.method_combo.setCurrentIndex(self.method_combo.findData(schedule.method))
            self.zone_combo.setCurrentIndex(self.zone_combo.findData(schedule.service_zone))
        self.version = QLineEdit(schedule.version if schedule else "1")
        self.version.setToolTip(self.tr("tt_tf_version"))
        eff_from = schedule.effective_from if schedule else dt.date.today()
        self.effective_from = QDateEdit(QDate(eff_from.year, eff_from.month, eff_from.day))
        self.effective_from.setToolTip(self.tr("tt_tf_eff_from"))
        self.effective_from.setCalendarPopup(True)
        self.effective_to = QDateEdit(QDate(2099, 12, 31))
        self.is_active = QCheckBox()
        self.is_active.setToolTip(self.tr("tt_tf_active"))
        self.is_active.setChecked(schedule.is_active if schedule else True)
        self.source_combo = QComboBox()
        self.source_combo.setToolTip(self.tr("tt_tf_source"))
        for s in DataSource:
            self.source_combo.addItem(app.i18n.enum_label(s), s)
        if schedule:
            self.source_combo.setCurrentIndex(self.source_combo.findData(schedule.source))
        self.source_detail = QLineEdit(schedule.source_detail if schedule else "")
        self.source_detail.setToolTip(self.tr("tt_tf_source_detail"))

        self.tiers_table = QTableWidget()
        self.tiers_table.setToolTip(self.tr("tt_tf_tiers"))
        self.tiers_table.setColumnCount(3)
        self.tiers_table.setHorizontalHeaderLabels([
            self.tr("tf_col_from"), self.tr("tf_col_to"), self.tr("tf_col_rate")])
        self.tiers_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tiers_table.verticalHeader().setDefaultSectionSize(36)
        self.tiers_table.setMinimumHeight(180)
        self.tiers_table.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.add_tier_btn = small_button(self.tr("tf_add_tier"))
        self.add_tier_btn.setToolTip(self.tr("tt_tf_add_tier"))
        self.remove_tier_btn = small_button(self.tr("tf_remove_row"))
        self.remove_tier_btn.setToolTip(self.tr("tt_tf_remove_row"))

        self.fees_table = QTableWidget()
        self.fees_table.setToolTip(self.tr("tt_tf_fees"))
        self.fees_table.setColumnCount(3)
        self.fees_table.setHorizontalHeaderLabels([
            self.tr("iv_col_name"), self.tr("iv_col_type"), self.tr("iv_col_amount")])
        self.fees_table.setMinimumHeight(140)
        self.fees_table.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.add_fee_btn = small_button(self.tr("tf_add_fee"))
        self.add_fee_btn.setToolTip(self.tr("tt_tf_add_fee"))
        self.remove_fee_btn = small_button(self.tr("tf_remove_row"))
        self.remove_fee_btn.setToolTip(self.tr("tt_tf_remove_row"))

        buttons = QDialogButtonBox()
        save_btn = buttons.addButton(self.tr("tf_save"), QDialogButtonBox.ButtonRole.AcceptRole)
        save_btn.setToolTip(self.tr("tt_tf_save"))
        buttons.addButton(self.tr("cancel"), QDialogButtonBox.ButtonRole.RejectRole)
        save_btn.clicked.connect(self._save)
        buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow(self.tr("tf_name_ar"), self.name_ar)
        form.addRow(self.tr("tf_name_en"), self.name_en)
        form.addRow(self.tr("tf_type"), self.type_combo)
        form.addRow(self.tr("tf_method"), self.method_combo)
        form.addRow(self.tr("tf_service_zone"), self.zone_combo)
        form.addRow(self.tr("tf_version"), self.version)
        form.addRow(self.tr("tf_effective_from"), self.effective_from)
        form.addRow(self.tr("tf_source"), self.source_combo)
        form.addRow(self.tr("tf_source_detail"), self.source_detail)
        form.addRow(self.tr("tf_is_active"), self.is_active)

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addLayout(form)
        layout.addWidget(QLabel(self.tr("tf_rate_per_kwh")))
        layout.addWidget(self.tiers_table)
        layout.addWidget(self.add_tier_btn)
        layout.addWidget(self.remove_tier_btn)
        layout.addWidget(QLabel(self.tr("tf_fixed_fees")))
        layout.addWidget(self.fees_table)
        layout.addWidget(self.add_fee_btn)
        layout.addWidget(self.remove_fee_btn)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        scroll.setMinimumHeight(560)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)
        root.addWidget(buttons)

        self.add_tier_btn.clicked.connect(self._add_tier_row)
        self.add_fee_btn.clicked.connect(self._add_fee_row)
        self.remove_tier_btn.clicked.connect(lambda: self._remove_selected_rows(self.tiers_table))
        self.remove_fee_btn.clicked.connect(lambda: self._remove_selected_rows(self.fees_table))

        if schedule:
            for tier in schedule.tiers:
                self._add_tier_row(str(tier.from_kwh), str(tier.to_kwh) if tier.to_kwh is not None else "", str(tier.rate_per_kwh))
            for fee in schedule.fixed_fees:
                self._add_fee_row(fee.name_ar, fee.category.value, str(fee.amount.raw))
        else:
            self._add_tier_row("0", "", "10")

    def _add_tier_row(self, from_kwh: str = "", to_kwh: str = "", rate: str = "") -> None:
        self.tiers_table.insertRow(self.tiers_table.rowCount())
        for col, value in ((0, from_kwh), (1, to_kwh), (2, rate)):
            self.tiers_table.setItem(self.tiers_table.rowCount() - 1, col, QTableWidgetItem(value))

    def _add_fee_row(self, name: str = "", category: str = "FIXED_FEE", amount: str = "") -> None:
        self.fees_table.insertRow(self.fees_table.rowCount())
        self.fees_table.setItem(self.fees_table.rowCount() - 1, 0, QTableWidgetItem(name))
        cat = next((x for x in ChargeCategory if x.value == category), None)
        combo = QComboBox()
        for c in ChargeCategory:
            combo.addItem(self.app.i18n.enum_label(c), c)
        idx = combo.findData(cat) if cat is not None else -1
        if idx >= 0:
            combo.setCurrentIndex(idx)
        self.fees_table.setCellWidget(self.fees_table.rowCount() - 1, 1, combo)
        self.fees_table.setItem(self.fees_table.rowCount() - 1, 2, QTableWidgetItem(amount))

    def _remove_selected_rows(self, table: QTableWidget) -> None:
        rows = sorted({i.row() for i in table.selectedIndexes()}, reverse=True)
        for row in rows:
            table.removeRow(row)

    def _collect_tiers(self) -> list[TariffTier]:
        tiers = []
        for r in range(self.tiers_table.rowCount()):
            from_item = self.tiers_table.item(r, 0)
            to_item = self.tiers_table.item(r, 1)
            rate_item = self.tiers_table.item(r, 2)
            if not from_item or not rate_item:
                continue
            try:
                from_kwh = Decimal(from_item.text().strip() or "0")
                rate = Decimal(rate_item.text().strip() or "0")
            except Exception:
                continue
            to_text = to_item.text().strip() if to_item else ""
            to_kwh = Decimal(to_text) if to_text else None
            if to_kwh is not None and to_kwh <= from_kwh:
                continue
            tiers.append(TariffTier(tier_no=len(tiers) + 1, from_kwh=from_kwh, to_kwh=to_kwh, rate_per_kwh=rate))
        return tiers

    def _collect_fees(self) -> list[TariffFee]:
        fees = []
        for r in range(self.fees_table.rowCount()):
            name_item = self.fees_table.item(r, 0)
            amount_item = self.fees_table.item(r, 2)
            combo = self.fees_table.cellWidget(r, 1)
            if not name_item or not amount_item or not hasattr(combo, "currentData"):
                continue
            name = name_item.text().strip()
            amount = amount_item.text().strip()
            if not name or not amount:
                continue
            try:
                money = Money.parse_iqd_input(amount)
            except Exception:
                continue
            fees.append(TariffFee(
                name_ar=name,
                category=combo.currentData() or ChargeCategory.FIXED_FEE,
                amount=money,
                reason=self.tr("audit_tariff_reason"),
            ))
        return fees

    def _save(self) -> None:
        try:
            schedule = self._schedule or TariffSchedule()
            schedule.name_ar = self.name_ar.text().strip() or "تعريفة"
            schedule.name_en = self.name_en.text().strip()
            schedule.subscriber_type = self.type_combo.currentData()
            schedule.method = self.method_combo.currentData()
            schedule.service_zone = self.zone_combo.currentData()
            schedule.version = self.version.text().strip() or "1"
            schedule.effective_from = self.effective_from.date().toPyDate()
            schedule.is_active = self.is_active.isChecked()
            schedule.source = self.source_combo.currentData()
            schedule.source_detail = self.source_detail.text().strip()
            schedule.tiers = self._collect_tiers()
            schedule.fixed_fees = self._collect_fees()
            if schedule.method == TariffMethod.FLAT and not schedule.tiers:
                schedule.tiers = [TariffTier(tier_no=1, from_kwh=Decimal("0"), to_kwh=None, rate_per_kwh=Decimal("0"))]
            self.app.tariffs.save(schedule)
            self.accept()
        except Exception as exc:
            QMessageBox.warning(self, self.tr("error"), error_text(self.app, exc))


class TariffsPage(QWidget):
    def __init__(self, app, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.tr = app.tr
        self._last: TariffSchedule | None = None

        title = QLabel(self.tr("tf_title"))
        title.setObjectName("PageTitle")
        new_btn = primary_button(self.tr("tf_new_btn"))
        new_btn.setToolTip(self.tr("tt_tf_new"))

        self.table = QTableWidget()
        self.table.setToolTip(self.tr("tt_tf_table"))
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            self.tr("tf_col_name"), self.tr("tf_col_type"), self.tr("tf_col_method"),
            self.tr("tf_col_version"), self.tr("tf_effective_from"),
            self.tr("tf_col_source_status"), self.tr("tf_actions"),
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(6, 132)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(46)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(new_btn)
        layout.addWidget(self.table)

        new_btn.clicked.connect(lambda: self._edit(None))
        self.table.itemDoubleClicked.connect(self._edit_selected)

    def refresh(self) -> None:
        schedules = self.app.tariffs.list(include_inactive=True)
        self.table.setRowCount(len(schedules))
        for r, s in enumerate(schedules):
            self.table.setItem(r, 0, QTableWidgetItem(s.name_ar))
            self.table.setItem(r, 1, QTableWidgetItem(self.app.i18n.enum_label(s.subscriber_type)))
            self.table.setItem(r, 2, QTableWidgetItem(self.app.i18n.enum_label(s.method)))
            self.table.setItem(r, 3, QTableWidgetItem(s.version))
            self.table.setItem(r, 4, QTableWidgetItem(s.effective_from.isoformat()))
            source = self.app.i18n.enum_label(s.source)
            zone = "" if s.service_zone == ServiceZone.TRADITIONAL else f" | {self.app.i18n.enum_label(s.service_zone)}"
            status = self.tr("tf_active_suffix") if s.is_active else self.tr("tf_inactive_suffix")
            self.table.setItem(r, 5, QTableWidgetItem(source + zone + status))
            for c in range(self.table.columnCount()):
                item = self.table.item(r, c)
                if item:
                    item.setData(Qt.ItemDataRole.UserRole, s.id)
            self.table.setCellWidget(r, 6, self._actions_cell(s.id))

    def _actions_cell(self, schedule_id: int) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)
        edit_btn = small_button(self.tr("edit"))
        delete_btn = danger_small_button(self.tr("delete"))
        edit_btn.clicked.connect(lambda: self._edit_schedule(schedule_id))
        delete_btn.clicked.connect(lambda: self._delete_schedule(schedule_id))
        layout.addStretch(1)
        layout.addWidget(edit_btn)
        layout.addWidget(delete_btn)
        layout.addStretch(1)
        return widget

    def _edit_schedule(self, schedule_id: int) -> None:
        schedule = self.app.tariffs.get(schedule_id)
        if schedule:
            self._edit(schedule)

    def _delete_schedule(self, schedule_id: int) -> None:
        answer = QMessageBox.question(
            self, self.tr("delete"), self.tr("delete_generic_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.app.tariffs.delete(schedule_id)
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, self.tr("error"), error_text(self.app, exc))

    def _edit_selected(self, item: QTableWidgetItem) -> None:
        schedule_id = item.data(Qt.ItemDataRole.UserRole)
        if schedule_id is not None:
            schedule = self.app.tariffs.get(schedule_id)
            if schedule:
                self._edit(schedule)

    def _edit(self, schedule: TariffSchedule | None) -> None:
        dialog = TariffDialog(self.app, schedule, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()