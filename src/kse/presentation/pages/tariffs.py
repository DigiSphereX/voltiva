from __future__ import annotations

import datetime as dt
from decimal import Decimal

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QLineEdit, QMessageBox, QScrollArea, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ...domain.enums import ChargeCategory, DataSource, ServiceZone, SubscriberType, TariffMethod
from ...domain.models import TariffFee, TariffSchedule, TariffTier
from ...domain.money import Money
from .. import theme
from ..widgets import (
    DataTable, PageHeader, RtlAlignDelegate, Section, action_cell, chip_cell, configure_table,
    date_edit, danger_small_button, error_text, fit_action_column, form_label, muted,
    primary_button, small_button,
)

_HEADER_ALIGNS = (
    Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignLeft,
    Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignHCenter,
    Qt.AlignmentFlag.AlignHCenter,
)


class _CellEditorDelegate(RtlAlignDelegate):
    """Inline editors copy the cell's alignment, so typing matches the shown value."""

    def createEditor(self, parent, option, index):  # noqa: N802
        editor = super().createEditor(parent, option, index)
        if isinstance(editor, QLineEdit):
            align = index.data(Qt.ItemDataRole.TextAlignmentRole)
            if align:
                editor.setAlignment(Qt.AlignmentFlag(align) | Qt.AlignmentFlag.AlignAbsolute)
        return editor


_ENTRY_ROW_H = 34


def _fit_entry_table(table: QTableWidget) -> None:
    """Height follows the rows so the table never shows an empty, table-shaped void."""
    rows = max(table.rowCount(), 2)
    table.setFixedHeight(theme.Metrics.HEADER_H + rows * _ENTRY_ROW_H + 2)


def _entry_table(columns: list[str], widths: dict[int, int], stretch: tuple[int, ...],
                 aligns: tuple[Qt.AlignmentFlag, ...]) -> QTableWidget:
    """Small editable table used inside the tariff dialog (tiers / fees)."""
    table = QTableWidget()
    table.setColumnCount(len(columns))
    table.setHorizontalHeaderLabels(columns)
    table.setShowGrid(True)
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setEditTriggers(
        QTableWidget.EditTrigger.DoubleClicked
        | QTableWidget.EditTrigger.EditKeyPressed
        | QTableWidget.EditTrigger.AnyKeyPressed)
    table.viewport().setCursor(Qt.CursorShape.IBeamCursor)   # cells are text fields
    table.setItemDelegate(_CellEditorDelegate(table))
    table.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
    table.setCornerButtonEnabled(False)
    configure_table(table, widths=widths, stretch=stretch, aligns=aligns,
                    row_height=_ENTRY_ROW_H, header_height=theme.Metrics.HEADER_H)
    _fit_entry_table(table)
    return table


class TariffDialog(QDialog):
    def __init__(self, app, schedule: TariffSchedule | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.tr = app.tr
        self._schedule = schedule
        self.setWindowTitle(self.tr("tf_save") if schedule else self.tr("tf_new_btn"))
        self.setMinimumWidth(660)

        self.name = QLineEdit(schedule.name if schedule else "")
        self.name.setToolTip(self.tr("tt_tf_name"))
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
        self.effective_from = date_edit(QDate(eff_from.year, eff_from.month, eff_from.day))
        self.effective_from.setToolTip(self.tr("tt_tf_eff_from"))
        self.effective_to = date_edit(QDate(2099, 12, 31))
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

        self.tiers_table = _entry_table(
            [self.tr("tf_col_from"), self.tr("tf_col_to"), self.tr("tf_col_rate")],
            widths={0: 150, 1: 150}, stretch=(2,),
            aligns=(Qt.AlignmentFlag.AlignRight,) * 3)
        self.tiers_table.setToolTip(self.tr("tt_tf_tiers"))
        self.add_tier_btn = small_button(self.tr("tf_add_tier"))
        self.add_tier_btn.setToolTip(self.tr("tt_tf_add_tier"))
        self.remove_tier_btn = small_button(self.tr("tf_remove_row"))
        self.remove_tier_btn.setToolTip(self.tr("tt_tf_remove_row"))

        self.fees_table = _entry_table(
            [self.tr("iv_col_name"), self.tr("iv_col_type"), self.tr("iv_col_amount")],
            widths={1: 190, 2: 170}, stretch=(0,),
            aligns=(Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignHCenter,
                    Qt.AlignmentFlag.AlignRight))
        self.fees_table.setToolTip(self.tr("tt_tf_fees"))
        self.add_fee_btn = small_button(self.tr("tf_add_fee"))
        self.add_fee_btn.setToolTip(self.tr("tt_tf_add_fee"))
        self.remove_fee_btn = small_button(self.tr("tf_remove_row"))
        self.remove_fee_btn.setToolTip(self.tr("tt_tf_remove_row"))

        details = Section(self.tr("tf_details"))
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for label, widget in (
            (self.tr("tf_name"), self.name),
            (self.tr("tf_type"), self.type_combo),
            (self.tr("tf_method"), self.method_combo),
            (self.tr("tf_service_zone"), self.zone_combo),
            (self.tr("tf_version"), self.version),
            (self.tr("tf_effective_from"), self.effective_from),
            (self.tr("tf_source"), self.source_combo),
            (self.tr("tf_source_detail"), self.source_detail),
            (self.tr("tf_is_active"), self.is_active),
        ):
            form.addRow(form_label(label, 140), widget)
        details.add_layout(form)

        tiers_card = Section(self.tr("tf_rate_per_kwh"))
        tiers_actions = QHBoxLayout()
        tiers_actions.setSpacing(8)
        tiers_actions.addStretch(1)
        tiers_actions.addWidget(self.add_tier_btn)
        tiers_actions.addWidget(self.remove_tier_btn)
        tiers_card.body.addWidget(self.tiers_table, 1)
        tiers_card.body.addWidget(muted(self.tr("tf_edit_hint")))
        tiers_card.add_layout(tiers_actions)

        fees_card = Section(self.tr("tf_fixed_fees"))
        fees_actions = QHBoxLayout()
        fees_actions.setSpacing(8)
        fees_actions.addStretch(1)
        fees_actions.addWidget(self.add_fee_btn)
        fees_actions.addWidget(self.remove_fee_btn)
        fees_card.body.addWidget(self.fees_table, 1)
        fees_card.body.addWidget(muted(self.tr("tf_edit_hint")))
        fees_card.add_layout(fees_actions)

        buttons = QDialogButtonBox()
        save_btn = buttons.addButton(self.tr("tf_save"), QDialogButtonBox.ButtonRole.AcceptRole)
        save_btn.setObjectName("Primary")
        save_btn.setToolTip(self.tr("tt_tf_save"))
        cancel_btn = buttons.addButton(self.tr("cancel"), QDialogButtonBox.ButtonRole.RejectRole)
        cancel_btn.setObjectName("Ghost")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save)
        buttons.rejected.connect(self.reject)

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.Metrics.PAGE_SPACING)
        layout.addWidget(details)
        layout.addWidget(tiers_card)
        layout.addWidget(fees_card)
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(body)
        scroll.setMinimumHeight(520)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)
        root.addWidget(scroll, 1)
        root.addWidget(buttons)

        self.add_tier_btn.clicked.connect(self._add_tier_row)
        self.add_fee_btn.clicked.connect(self._add_fee_row)
        self.remove_tier_btn.clicked.connect(lambda: self._remove_selected_rows(self.tiers_table))
        self.remove_fee_btn.clicked.connect(lambda: self._remove_selected_rows(self.fees_table))

        if schedule:
            for tier in schedule.tiers:
                self._add_tier_row(str(tier.from_kwh), str(tier.to_kwh) if tier.to_kwh is not None else "", str(tier.rate_per_kwh))
            for fee in schedule.fixed_fees:
                self._add_fee_row(fee.name, fee.category.value, str(fee.amount.raw))
        else:
            self._add_tier_row("0", "", "10")

    def _add_tier_row(self, from_kwh: str = "", to_kwh: str = "", rate: str = "") -> None:
        row = self.tiers_table.rowCount()
        self.tiers_table.insertRow(row)
        for col, value in ((0, from_kwh), (1, to_kwh), (2, rate)):
            item = QTableWidgetItem(value)
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tiers_table.setItem(row, col, item)
        _fit_entry_table(self.tiers_table)

    def _add_fee_row(self, name: str = "", category: str = "FIXED_FEE", amount: str = "") -> None:
        row = self.fees_table.rowCount()
        self.fees_table.insertRow(row)
        name_item = QTableWidgetItem(name)
        name_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.fees_table.setItem(row, 0, name_item)
        cat = next((x for x in ChargeCategory if x.value == category), None)
        combo = QComboBox()
        for c in ChargeCategory:
            combo.addItem(self.app.i18n.enum_label(c), c)
        idx = combo.findData(cat) if cat is not None else -1
        if idx >= 0:
            combo.setCurrentIndex(idx)
        self.fees_table.setCellWidget(row, 1, combo)
        amount_item = QTableWidgetItem(amount)
        amount_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.fees_table.setItem(row, 2, amount_item)
        _fit_entry_table(self.fees_table)

    def _remove_selected_rows(self, table: QTableWidget) -> None:
        rows = sorted({i.row() for i in table.selectedIndexes()}, reverse=True)
        for row in rows:
            table.removeRow(row)
        _fit_entry_table(table)

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
                name=name,
                category=combo.currentData() or ChargeCategory.FIXED_FEE,
                amount=money,
                reason=self.tr("audit_tariff_reason"),
            ))
        return fees

    def _save(self) -> None:
        try:
            schedule = self._schedule or TariffSchedule()
            schedule.name = self.name.text().strip() or "Tariff"
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

        new_btn = primary_button("+ " + self.tr("tf_new_btn"))
        new_btn.setToolTip(self.tr("tt_tf_new"))
        header = PageHeader(self.tr("tf_title"), self.tr("tf_subtitle"), actions=[new_btn])

        self.table = DataTable()
        self.table.setToolTip(self.tr("tt_tf_table"))
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            self.tr("tf_col_name"), self.tr("tf_col_type"), self.tr("tf_col_method"),
            self.tr("tf_col_zone"), self.tr("tf_effective_from"),
            self.tr("tf_col_status"), self.tr("tf_actions"),
        ])
        configure_table(
            self.table, aligns=_HEADER_ALIGNS, stretch=(0,),
            widths={1: 124, 2: 112, 3: 118, 4: 116, 5: 110, 6: 150},
            row_height=theme.Metrics.ROW_H, header_height=theme.Metrics.HEADER_H)
        self.table.set_empty_text(self.tr("tf_none"))

        self.count_lbl = muted("")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            theme.Metrics.PAGE_MARGIN, 18, theme.Metrics.PAGE_MARGIN, 18)
        layout.setSpacing(12)
        layout.addWidget(header)
        layout.addWidget(self.table, 1)
        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(self.count_lbl)
        layout.addLayout(footer)

        new_btn.clicked.connect(lambda: self._edit(None))
        self.table.itemDoubleClicked.connect(self._edit_selected)

    def _localized_name(self, s: TariffSchedule) -> str:
        """Display name for the schedule row (single shared name column)."""
        return s.name

    def refresh(self) -> None:
        schedules = self.app.tariffs.list(include_inactive=True)
        colors = theme.colors()
        left = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        center = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        self.table.setUpdatesEnabled(False)
        try:
            self.table.clearContents()
            self.table.setRowCount(len(schedules))
            for r, s in enumerate(schedules):
                name = self._localized_name(s)
                source = self.app.i18n.enum_label(s.source)
                values = (
                    name,
                    self.app.i18n.enum_label(s.subscriber_type),
                    self.app.i18n.enum_label(s.method),
                    self.app.i18n.enum_label(s.service_zone),
                    s.effective_from.strftime("%d/%m/%Y"),
                )
                for c, text in enumerate(values):
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(left)
                    item.setData(Qt.ItemDataRole.UserRole, s.id)
                    if c == 0:      # version/source live in the detail dialog; keep them a hover away
                        item.setToolTip(self.tr(
                            "tf_row_tip", name=name, version=s.version, source=source))
                    elif c >= 3:
                        item.setToolTip(text)
                    self.table.setItem(r, c, item)
                status = self.tr("tf_active") if s.is_active else self.tr("tf_inactive")
                status_item = QTableWidgetItem("")   # the chip widget paints the label
                status_item.setTextAlignment(center)
                status_item.setToolTip(status)
                status_item.setData(Qt.ItemDataRole.UserRole, s.id)
                self.table.setItem(r, 5, status_item)
                self.table.setCellWidget(r, 5, chip_cell(
                    status, colors["success"] if s.is_active else colors["muted"]))
                actions = self._actions_cell(s.id)
                self.table.setCellWidget(r, 6, actions)
                fit_action_column(self.table, 6, actions)
        finally:
            self.table.setUpdatesEnabled(True)
        self.count_lbl.setText(self.tr("tf_showing", n=str(len(schedules))))

    def _actions_cell(self, schedule_id: int) -> QWidget:
        edit_btn = small_button(self.tr("edit"))
        delete_btn = danger_small_button(self.tr("delete"))
        edit_btn.clicked.connect(lambda: self._edit_schedule(schedule_id))
        delete_btn.clicked.connect(lambda: self._delete_schedule(schedule_id))
        return action_cell(edit_btn, delete_btn)

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
