from __future__ import annotations

import datetime as dt
from decimal import Decimal

from PyQt6.QtCore import QDate, QObject, QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QScrollArea, QTabWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ...application.services import CalculateInvoiceRequest
from ...domain.enums import MeterScenario, PaymentStatus, SubscriberType
from ...domain.money import Money, latin_digits
from ...domain.models import Invoice
from .. import theme
from ..widgets import (
    DataTable, MoneyEdit, ReadingEdit, configure_table, date_edit, error_label,
    error_text, form_label, ghost_button, primary_button,
)


class _OcrWorker(QObject):
    """Runs the configured scanner off the GUI thread so the dialog stays responsive."""

    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, path: str, cfg, error_prefix: str = "") -> None:
        super().__init__()
        self.path = path
        self.cfg = cfg
        self.error_prefix = error_prefix

    def run(self) -> None:
        try:
            from ...infrastructure.ocr.ai_scanner import scan_invoice
            self.finished.emit(scan_invoice(self.path, self.cfg))
        except Exception as exc:  # pragma: no cover
            message = str(exc)
            if self.error_prefix:
                message = f"{self.error_prefix}\n\n{message}"
            self.failed.emit(message)


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
        today_q = QDate(today.year, today.month, today.day)
        self.issue_date = date_edit(today_q)
        self.prev_date = date_edit(today_q)
        self.curr_date = date_edit(today_q)
        self.consumption_kwh = QLineEdit()
        self.consumption_kwh.setToolTip(self.tr("tt_imp_consumption"))
        self.official_amount = MoneyEdit()
        self.notes = QLineEdit()

        self.err_lbl = error_label()

        manual_content = QWidget()
        form = QFormLayout(manual_content)
        form.setContentsMargins(16, 14, 16, 14)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for label, widget in (
            (self.tr("sb_account_no"), self.account_no),
            (self.tr("sb_subscription_no"), self.subscription_no),
            (self.tr("sb_name"), self.subscriber_name),
            (self.tr("ni_subscriber_type"), self.subscriber_type),
            (self.tr("meter_no"), self.meter_no),
            (self.tr("ni_prev_reading"), self.prev_reading),
            (self.tr("ni_curr_reading"), self.curr_reading),
            (self.tr("ni_multiplier"), self.multiplier),
            (self.tr("ni_prev_date"), self.prev_date),
            (self.tr("ni_curr_date"), self.curr_date),
            (self.tr("issue_date"), self.issue_date),
            (self.tr("import_consumption"), self.consumption_kwh),
            (self.tr("vk_official"), self.official_amount),
            (self.tr("il_notes"), self.notes),
        ):
            form.addRow(form_label(label, 140), widget)
        manual_tab = QScrollArea()
        manual_tab.setWidgetResizable(True)
        manual_tab.setFrameShape(QScrollArea.Shape.NoFrame)
        manual_tab.setWidget(manual_content)

        ocr_tab = QWidget()
        ocr_lbl = QLabel(self.tr("ocr_hint"))
        ocr_lbl.setWordWrap(True)
        self.ocr_engine_lbl = QLabel()
        self.ocr_engine_lbl.setObjectName("Muted")
        self.ocr_engine_lbl.setWordWrap(True)
        self.ocr_engine_hint = QLabel(self.tr("ocr_engine_hint"))
        self.ocr_engine_hint.setObjectName("Muted")
        self.ocr_engine_hint.setWordWrap(True)
        self.ocr_btn = ghost_button(self.tr("ocr_read"))
        self.ocr_btn.setToolTip(self.tr("tt_imp_ocr"))
        ocr_layout = QVBoxLayout(ocr_tab)
        ocr_layout.setContentsMargins(16, 14, 16, 14)
        ocr_layout.setSpacing(10)
        ocr_layout.addWidget(ocr_lbl)
        ocr_layout.addWidget(self.ocr_engine_lbl)
        ocr_layout.addWidget(self.ocr_engine_hint)
        ocr_btn_row = QHBoxLayout()
        ocr_btn_row.addWidget(self.ocr_btn)
        ocr_btn_row.addStretch(1)
        ocr_layout.addLayout(ocr_btn_row)
        self.ocr_text = QLabel("")
        self.ocr_text.setWordWrap(True)
        self.ocr_text.setObjectName("Muted")
        ocr_layout.addWidget(self.ocr_text)
        token_lbl = QLabel(self.tr("ocr_token_heading"))
        token_lbl.setWordWrap(True)
        ocr_layout.addWidget(token_lbl)
        self.token_table = DataTable()
        self.token_table.setColumnCount(3)
        self.token_table.setHorizontalHeaderLabels(
            [self.tr("ocr_col_value"), self.tr("ocr_col_position"), self.tr("ocr_col_conf")])
        configure_table(self.token_table, widths={1: 100, 2: 100}, stretch=(0,),
                        row_height=theme.Metrics.ROW_H, header_height=theme.Metrics.HEADER_H)
        self.token_table.setMinimumHeight(220)
        self.token_table.set_empty_text(self.tr("ocr_none"))
        ocr_layout.addWidget(self.token_table, 1)

        tabs = QTabWidget()
        tabs.addTab(manual_tab, self.tr("import_manual"))
        tabs.addTab(ocr_tab, self.tr("ocr_tab"))

        save_btn = primary_button(self.tr("ni_save"))
        cancel_btn = ghost_button(self.tr("cancel"))
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(save_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)
        layout.addWidget(tabs, 1)
        layout.addWidget(self.err_lbl)
        layout.addLayout(buttons)

        save_btn.setDefault(True)
        self.ocr_btn.clicked.connect(self._ocr_read)
        save_btn.clicked.connect(self._save)
        cancel_btn.clicked.connect(self.reject)
        self._refresh_engine()

    # ---- OCR ---------------------------------------------------------
    def _scan_config(self):
        from ...infrastructure.ocr.ai_scanner import AiScanConfig

        return AiScanConfig.load(self.app.repos["settings"])

    def _refresh_engine(self):
        cfg = self._scan_config()
        self.ocr_engine_lbl.setText(
            self.tr("ocr_engine", engine=self.tr(cfg.engine_key())))
        return cfg

    def _ocr_read(self) -> None:
        from ...infrastructure.ocr.ai_scanner import MODE_AUTO, MODE_CUSTOM, MODE_LOCAL
        from ...infrastructure.ocr.invoice_ocr import InvoiceOcr

        cfg = self._refresh_engine()
        if cfg.mode == MODE_CUSTOM and not cfg.endpoint():
            QMessageBox.warning(self, self.tr("ocr_tab"), self.tr("ocr_ai_need_url"))
            return
        if cfg.mode == MODE_LOCAL and not InvoiceOcr.is_available():
            QMessageBox.warning(
                self, self.tr("ocr_tab"),
                self.tr("ocr_unavailable") + "\n\n" + self.tr("ocr_install"))
            return
        if (cfg.mode == MODE_AUTO and not cfg.api_key.strip()
                and not InvoiceOcr.is_available()):
            QMessageBox.warning(
                self, self.tr("ocr_tab"),
                self.tr("ocr_ai_need_key") + "\n\n" + self.tr("ocr_install"))
            return
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("ocr_read"), "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff)")
        if not path:
            return
        self._running_ocr(path, cfg)

    def _running_ocr(self, path: str, cfg) -> None:
        from ...infrastructure.ocr.ai_scanner import MODE_LOCAL

        self.ocr_btn.setEnabled(False)
        self.ocr_btn.setText(self.tr("ocr_working"))
        self.ocr_text.setText("")
        prefix = "" if cfg.mode == MODE_LOCAL else self.tr("ocr_ai_failed")
        self._ocr_thread = QThread(self)
        self._ocr_worker = _OcrWorker(path, cfg, prefix)
        self._ocr_worker.moveToThread(self._ocr_thread)
        self._ocr_thread.started.connect(self._ocr_worker.run)
        self._ocr_worker.finished.connect(self._ocr_done)
        self._ocr_worker.failed.connect(self._ocr_error)
        self._ocr_worker.finished.connect(self._ocr_thread.quit)
        self._ocr_worker.failed.connect(self._ocr_thread.quit)
        self._ocr_worker.finished.connect(self._ocr_worker.deleteLater)
        self._ocr_worker.failed.connect(self._ocr_worker.deleteLater)
        self._ocr_thread.finished.connect(self._ocr_thread_finished)
        self._ocr_thread.start()

    def _ocr_thread_finished(self) -> None:
        self._ocr_thread = None
        self.ocr_btn.setEnabled(True)
        self.ocr_btn.setText(self.tr("ocr_read"))

    def _apply_ocr(self, extracted) -> None:
        from ...infrastructure.ocr.invoice_ocr import InvoiceOcr

        values = extracted.confirmed_values()
        text_map = {
            "account_no": self.account_no,
            "subscription_no": self.subscription_no,
            "subscriber_name": self.subscriber_name,
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
            if not value or widget.text().strip():
                continue
            if key == "subscriber_name":
                text = value
            elif key == "official_amount":
                # keep a decimal separator; MoneyEdit parses it, while commas never reach it
                text = InvoiceOcr._clean(value).replace(",", "").strip()
            else:
                text = InvoiceOcr.normalize_digits(value)
            widget.setText(text)
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

        engine_key = {
            "ai-auto": "ocr_engine_auto",
            "ai-custom": "ocr_engine_custom",
            "tesseract": "ocr_engine_local",
            "tesseract-fallback": "ocr_engine_local",
        }.get(extracted.engine, "ocr_engine_local")
        self.ocr_engine_lbl.setText(
            self.tr("ocr_engine", engine=self.tr(engine_key)))
        warnings = list(extracted.warnings)
        if extracted.engine == "tesseract-fallback":
            warnings.insert(0, self.tr("ocr_ai_fallback"))

        self.token_table.setRowCount(0)
        right = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        center = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        for tok in extracted.numeric_tokens():
            row = self.token_table.rowCount()
            self.token_table.insertRow(row)
            position = f"{tok.x},{tok.y}" if (tok.x or tok.y) else ""
            for col, text, align in (
                (0, tok.digits, right),
                (1, position, center),
                (2, f"{tok.confidence:.0%}", right),
            ):
                item = QTableWidgetItem(text)
                item.setTextAlignment(align)
                self.token_table.setItem(row, col, item)

        lines = [extracted.text.strip().replace(chr(10), " ")[:260]]
        lines += warnings
        summary = self.tr("ocr_warns", w="\n- ".join(warnings)) if warnings else ""
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
        thread = getattr(self, "_ocr_thread", None)
        if isinstance(thread, QThread) and thread.isRunning():
            thread.requestInterruption()
        super().reject()

    # ---- save --------------------------------------------------------
    def _save(self) -> None:
        self.err_lbl.setVisible(False)
        try:
            account_no = latin_digits(self.account_no.text().strip())
            if not account_no:
                raise ValueError(self.tr("import_account_required"))
            sub = self.app.subscribers.find_or_create(
                account_no,
                subscription_no=latin_digits(self.subscription_no.text().strip()),
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