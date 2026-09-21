from __future__ import annotations

import datetime as dt
from decimal import Decimal

from PyQt6.QtCore import QDate, QObject, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QDateEdit, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QVBoxLayout, QWidget,
)

from ...application.services import CalculateInvoiceRequest
from ...domain.enums import MeterScenario, PaymentStatus, SubscriberType
from ...domain.money import Money
from ...domain.models import Invoice
from ..widgets import MoneyEdit, ReadingEdit, error_label, ghost_button, primary_button, error_text


class _OcrWorker(QObject):
    """Runs InvoiceOcr.extract() off the GUI thread so the dialog stays responsive."""

    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, path: str) -> None:
        super().__init__()
        self.path = path

    def run(self) -> None:
        try:
            from ...infrastructure.ocr.invoice_ocr import InvoiceOcr
            self.finished.emit(InvoiceOcr.extract(self.path))
        except Exception as exc:  # pragma: no cover
            self.failed.emit(str(exc))


class ImportInvoiceDialog(QDialog):
    """Add an invoice manually (typed from the paper invoice) and optionally prefill via OCR."""

    def __init__(self, app, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.tr = app.tr
        self._saved: Invoice | None = None
        self.setWindowTitle(self.tr("ni_title") + " — " + self.tr("import_manual"))
        self.setMinimumWidth(560)

        today = dt.date.today()
        self.account_no = QLineEdit()
        self.subscription_no = QLineEdit()
        self.subscriber_name = QLineEdit()
        self.subscriber_type = QComboBox()
        for t in SubscriberType:
            self.subscriber_type.addItem(app.i18n.enum_label(t), t)
        self.meter_no = QLineEdit()
        self.meter_no.setToolTip(self.tr("tt_imp_meter"))
        self.prev_reading = ReadingEdit()
        self.curr_reading = ReadingEdit()
        self.multiplier = ReadingEdit(); self.multiplier.setText("1")
        self.issue_date = QDateEdit(QDate(today.year, today.month, today.day)); self.issue_date.setCalendarPopup(True)
        self.prev_date = QDateEdit(QDate(today.year, today.month, today.day)); self.prev_date.setCalendarPopup(True)
        self.curr_date = QDateEdit(QDate(today.year, today.month, today.day)); self.curr_date.setCalendarPopup(True)
        self.consumption_kwh = QLineEdit()
        self.consumption_kwh.setToolTip(self.tr("tt_imp_consumption"))
        self.official_amount = MoneyEdit()
        self.notes = QLineEdit()

        self.err_lbl = error_label()

        manual_tab = QWidget()
        form = QFormLayout(manual_tab)
        form.addRow(self.tr("sb_account_no"), self.account_no)
        form.addRow(self.tr("sb_subscription_no"), self.subscription_no)
        form.addRow(self.tr("sb_name"), self.subscriber_name)
        form.addRow(self.tr("ni_subscriber_type"), self.subscriber_type)
        form.addRow(self.tr("meter_no"), self.meter_no)
        form.addRow(self.tr("ni_prev_reading"), self.prev_reading)
        form.addRow(self.tr("ni_curr_reading"), self.curr_reading)
        form.addRow(self.tr("ni_multiplier"), self.multiplier)
        form.addRow(self.tr("ni_prev_date"), self.prev_date)
        form.addRow(self.tr("ni_curr_date"), self.curr_date)
        form.addRow(self.tr("issue_date"), self.issue_date)
        form.addRow(self.tr("import_consumption"), self.consumption_kwh)
        form.addRow(self.tr("vk_official"), self.official_amount)
        form.addRow(self.tr("il_notes"), self.notes)

        ocr_tab = QWidget()
        ocr_lbl = QLabel(self.tr("ocr_hint"))
        ocr_lbl.setWordWrap(True)
        self.ocr_btn = ghost_button(self.tr("ocr_read"))
        self.ocr_btn.setToolTip(self.tr("tt_imp_ocr"))
        ocr_layout = QVBoxLayout(ocr_tab)
        ocr_layout.addWidget(ocr_lbl)
        ocr_layout.addWidget(self.ocr_btn)
        ocr_layout.addStretch(1)
        self.ocr_text = QLabel("")
        self.ocr_text.setWordWrap(True)
        self.ocr_text.setObjectName("Muted")
        ocr_layout.addWidget(self.ocr_text)
        token_lbl = QLabel(self.tr("ocr_token_heading"))
        token_lbl.setWordWrap(True)
        ocr_layout.addWidget(token_lbl)
        self.token_table = QTableWidget(0, 3)
        self.token_table.setHorizontalHeaderLabels(
            [self.tr("ocr_col_value"), "X", self.tr("ocr_col_conf")])
        self.token_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.token_table.verticalHeader().setVisible(False)
        self.token_table.verticalHeader().setDefaultSectionSize(36)
        self.token_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        ocr_layout.addWidget(self.token_table)

        tabs = QTabWidget()
        tabs.addTab(manual_tab, self.tr("import_manual"))
        tabs.addTab(ocr_tab, self.tr("ocr_tab"))

        save_btn = primary_button(self.tr("ni_save"))
        cancel_btn = QPushButton(self.tr("cancel"))
        buttons = QHBoxLayout()
        buttons.addWidget(save_btn)
        buttons.addWidget(cancel_btn)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(self.err_lbl)
        layout.addLayout(buttons)

        self.ocr_btn.clicked.connect(self._ocr_read)
        save_btn.clicked.connect(self._save)
        cancel_btn.clicked.connect(self.reject)

    # ---- OCR ---------------------------------------------------------
    def _ocr_read(self) -> None:
        from ...infrastructure.ocr.invoice_ocr import InvoiceOcr

        if not InvoiceOcr.is_available():
            QMessageBox.warning(
                self, self.tr("ocr_tab"),
                self.tr("ocr_unavailable") + "\n\n" + self.tr("ocr_install"))
            return
        path, _ = QFileDialog.getOpenFileName(self, self.tr("ocr_read"), "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        self._running_ocr(path)

    def _running_ocr(self, path: str) -> None:
        self.ocr_btn.setEnabled(False)
        self.ocr_btn.setText(self.tr("ocr_working"))
        self.ocr_text.setText("")
        self.thread = QThread(self)
        self.worker = _OcrWorker(path)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._ocr_done)
        self.worker.failed.connect(self._ocr_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.failed.connect(self.worker.deleteLater)
        self.thread.finished.connect(self._ocr_thread_finished)
        self.thread.start()

    def _ocr_thread_finished(self) -> None:
        self.ocr_btn.setEnabled(True)
        self.ocr_btn.setText(self.tr("ocr_read"))

    def _apply_ocr(self, extracted) -> None:
        from ...infrastructure.ocr.invoice_ocr import InvoiceOcr

        values = extracted.confirmed_values()
        text_map = {
            "account_no": self.account_no,
            "subscription_no": self.subscription_no,
            "meter_no": self.meter_no,
            "previous_reading": self.prev_reading,
            "current_reading": self.curr_reading,
            "official_amount": self.official_amount,
            "consumption_kwh": self.consumption_kwh,
        }
        date_map = {
            "issue_date": self.issue_date,
            "previous_read_date": self.prev_date,
            "current_read_date": self.curr_date,
        }
        filled = 0
        for key, widget in text_map.items():
            value = values.get(key, "")
            if value and not widget.text().strip():
                widget.setText(InvoiceOcr.normalize_digits(value))
                filled += 1
        for key, widget in date_map.items():
            value = InvoiceOcr.normalize_digits(values.get(key, ""))
            if len(value) == 8 and value.isdigit():
                try:
                    widget.setDate(QDate(int(value[0:4]), int(value[4:6]), int(value[6:8])))
                    filled += 1
                except (ValueError, TypeError):
                    pass

        account_val = values.get("account_no", "")
        if account_val:
            mismatch = self._account_mismatch(InvoiceOcr.normalize_digits(account_val))
            if mismatch:
                extracted.warnings.append(mismatch)

        self.token_table.setRowCount(0)
        for tok in extracted.numeric_tokens():
            row = self.token_table.rowCount()
            self.token_table.insertRow(row)
            self.token_table.setItem(row, 0, QTableWidgetItem(tok.digits))
            self.token_table.setItem(row, 1, QTableWidgetItem(f"{tok.x},{tok.y}"))
            self.token_table.setItem(row, 2, QTableWidgetItem(f"{tok.confidence:.0%}"))

        lines = [extracted.text.strip().replace(chr(10), " ")[:260]]
        lines += extracted.warnings
        summary = self.tr("ocr_warns", w="\n- ".join(extracted.warnings)) if extracted.warnings else ""
        self.ocr_text.setText(
            (self.tr("ocr_found", count=filled) if filled else self.tr("ocr_none")) +
            ("\n\n" + summary if summary else "") + "\n\n" + "\n".join(lines))
        if filled:
            QMessageBox.information(self, self.tr("success"), self.tr("ocr_review"))

    def _account_mismatch(self, ocr_account: str) -> str:
        """Empty string when the OCR account matches a recorded account, else a warning.

        The household's collector slips always carry the same account number;
        a different OCR-read number usually means a misread (e.g. transposed
        digits) or someone else's bill.
        """
        from ...infrastructure.ocr.invoice_ocr import InvoiceOcr

        if len(ocr_account) < 4:
            return ""
        known: set[str] = set()
        try:
            for inv in self.app.repos["invoices"].list_recent(limit=2000):
                acc = InvoiceOcr.normalize_digits(inv.account_no or "")
                if len(acc) >= 4:
                    known.add(acc)
        except Exception:
            return ""
        if not known or ocr_account in known:
            return ""
        return self.tr(
            "ocr_account_mismatch", account=ocr_account, known=", ".join(sorted(known)[:3]))

    def _ocr_done(self, extracted) -> None:
        try:
            self._apply_ocr(extracted)
        except RuntimeError:
            pass  # dialog closed while OCR was running

    def _ocr_error(self, message: str) -> None:
        try:
            QMessageBox.warning(self, self.tr("error"), message)
        except RuntimeError:
            pass

    def reject(self) -> None:
        thread = getattr(self, "thread", None)
        if thread is not None and thread.isRunning():
            thread.requestInterruption()
        super().reject()

    # ---- save --------------------------------------------------------
    def _save(self) -> None:
        self.err_lbl.setVisible(False)
        try:
            account_no = self.account_no.text().strip()
            if not account_no:
                raise ValueError(self.tr("import_account_required"))
            sub = self.app.subscribers.find_or_create(
                account_no,
                subscription_no=self.subscription_no.text().strip(),
                name=self.subscriber_name.text().strip(),
            )
            issue_date = self.issue_date.date().toPyDate()
            prev_date = self.prev_date.date().toPyDate()
            curr_date = self.curr_date.date().toPyDate()
            official = self.official_amount.money()

            consumption_text = self.consumption_kwh.text().strip()
            prev_text = self.prev_reading.text().strip()
            if prev_text and self.curr_reading.text().strip():
                req = CalculateInvoiceRequest(
                    subscriber_type=sub.subscriber_type,
                    previous_reading=self.prev_reading.reading(),
                    current_reading=self.curr_reading.reading(),
                    previous_read_date=prev_date,
                    current_read_date=curr_date,
                    meter_multiplier=self.multiplier.reading(),
                    scenario=MeterScenario.NORMAL,
                    official_amount=official,
                )
                calc, schedule = self.app.invoices.calculate(req)
                invoice = self.app.invoices.save_calculation(
                    calc, schedule, sub,
                    invoice_no=("IMP-" + str(issue_date.year) + "-" + str(issue_date.month).zfill(2)),
                    issue_date=issue_date,
                    previous_read_date=prev_date,
                    current_read_date=curr_date,
                    notes=self.notes.text().strip() or self.tr("import_manual_note"),
                    official_amount=official,
                )
                if official is None and consumption_text:
                    invoice.consumption_kwh = Decimal(consumption_text)
                    invoice.adjusted_kwh = Decimal(consumption_text)
                    self.app.repos["invoices"].save(
                        invoice, self.app.repos["invoices"].list_reading(invoice.id),
                        self.app.repos["invoices"].list_charges(invoice.id))
            else:
                consumption = Decimal(consumption_text) if consumption_text else Decimal("0")
                invoice = Invoice(
                    invoice_no="IMP-" + str(issue_date.year) + "-" + str(issue_date.month).zfill(2),
                    account_no=account_no,
                    subscription_no=sub.subscription_no,
                    subscriber_name=sub.name,
                    subscriber_type=sub.subscriber_type,
                    issue_date=issue_date,
                    previous_read_date=prev_date,
                    current_read_date=curr_date,
                    previous_reading=Decimal(self.prev_reading.reading()),
                    current_reading=Decimal(self.curr_reading.reading()),
                    consumption_kwh=consumption,
                    adjusted_kwh=consumption,
                    current_amount=official or Money.zero(),
                    total_due=official or Money.zero(),
                    official_amount=official,
                    due_date=issue_date + dt.timedelta(days=15),
                    payment_status=PaymentStatus.UNPAID,
                    notes=self.notes.text().strip() or self.tr("import_manual_note"),
                )
                self.app.repos["invoices"].save(invoice, None, [])
            self._saved = invoice
            self.accept()
        except Exception as exc:
            self.err_lbl.setText(error_text(self.app, exc))
            self.err_lbl.setVisible(True)

    @property
    def saved_invoice(self) -> Invoice | None:
        return self._saved