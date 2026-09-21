"""ValidationEngine — catches invalid input early (spec §36).

Never hides an error; never guesses a value.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from ..enums import MeterScenario
from ..models import Subscriber, TariffSchedule, TariffTier
from ..money import Money, latin_digits

ACCOUNT_NO_RE = re.compile(r"^\d{4,20}$")
SUBSCRIPTION_NO_RE = re.compile(r"^[\w\-]{4,30}$")

_VLD_KEYS = {
    "READING_NEGATIVE", "READING_INVALID", "READING_DECREASE",
    "DATE_MISSING", "DATE_ORDER", "ISSUE_DATE_BEFORE_READING",
    "ACCOUNT_MISSING", "ACCOUNT_FORMAT",
    "NEGATIVE_FEE", "DOUBLE_NEGATIVE_DISCOUNT", "NEGATIVE_AMOUNT",
    "TARIFF_NAME", "TARIFF_DATE", "TARIFF_RANGE", "TARIFF_NO_TIERS",
    "TARIFF_NEGATIVE", "TARIFF_OVERLAP", "SUBSCRIBER_NAME",
}


@dataclass
class Issue:
    code: str
    level: str  # ERROR | WARNING
    message: str
    field: str = ""
    name: str = ""

    def __bool__(self):
        return True

    def localized(self, tr) -> str:
        """Localized message via an i18n translation callable (tr(key, **kwargs)).

        Codes without a vld_* key fall back to the original (Arabic) message.
        """
        if self.code not in _VLD_KEYS:
            return self.message
        kwargs: dict = {}
        if self.field.startswith("previous"):
            kwargs["field"] = tr("field_previous")
        elif self.field.startswith("current"):
            kwargs["field"] = tr("field_current")
        if self.name:
            kwargs["name"] = self.name
        return tr("vld_" + self.code.lower(), **kwargs)


@dataclass
class ValidationReport:
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "ERROR"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "WARNING"]

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    def messages(self) -> list[str]:
        return [i.message for i in self.issues]


class ValidationEngine:
    @staticmethod
    def parse_reading(text: str) -> Decimal | None:
        try:
            return Money.parse_reading(text)
        except ValueError:
            return None

    @staticmethod
    def validate_readings(*, previous, current, scenario: MeterScenario) -> ValidationReport:
        report = ValidationReport()

        prev_text = str(previous).strip()
        curr_text = str(current).strip()

        if prev_text.startswith("-"):
            report.issues.append(Issue("READING_NEGATIVE", "ERROR", "القراءة السابقة لا يمكن أن تكون سالبة.", "previous_reading"))
        if curr_text.startswith("-"):
            report.issues.append(Issue("READING_NEGATIVE", "ERROR", "القراءة الحالية لا يمكن أن تكون سالبة.", "current_reading"))

        prev = ValidationEngine.parse_reading(previous)
        curr = ValidationEngine.parse_reading(current)

        if prev is None:
            report.issues.append(Issue("READING_INVALID", "ERROR", "القراءة السابقة غير صالحة (يجب أن تكون رقمًا صحيحاً).", "previous_reading"))
        if curr is None:
            report.issues.append(Issue("READING_INVALID", "ERROR", "القراءة الحالية غير صالحة (يجب أن تكون رقمًا صحيحاً).", "current_reading"))
        if prev is not None and prev < 0:
            report.issues.append(Issue("READING_NEGATIVE", "ERROR", "القراءة السابقة لا يمكن أن تكون سالبة.", "previous_reading"))
        if curr is not None and curr < 0:
            report.issues.append(Issue("READING_NEGATIVE", "ERROR", "القراءة الحالية لا يمكن أن تكون سالبة.", "current_reading"))

        if prev is not None and curr is not None and scenario in (MeterScenario.NORMAL, MeterScenario.MULTIPLIER):
            if curr < prev:
                report.issues.append(Issue(
                    "READING_DECREASE",
                    "ERROR",
                    "القراءة الحالية أقل من السابقة --- يرجى التحقق من تبديل العداد أو إدخال القراءة.",
                    "current_reading",
                ))
            # consumption non-negative
        return report

    @staticmethod
    def validate_dates(*, previous_date: Optional[dt.date], current_date: Optional[dt.date], issue_date: Optional[dt.date]) -> ValidationReport:
        report = ValidationReport()
        if previous_date is None:
            report.issues.append(Issue("DATE_MISSING", "ERROR", "تاريخ القراءة السابقة غير محدد.", "previous_read_date"))
        if current_date is None:
            report.issues.append(Issue("DATE_MISSING", "ERROR", "تاريخ القراءة الحالية غير محدد.", "current_read_date"))
        if previous_date is not None and current_date is not None and current_date < previous_date:
            report.issues.append(Issue("DATE_ORDER", "ERROR", "تاريخ القراءة الحالية قبل تاريخ القراءة السابقة.", "current_read_date"))
        if issue_date is not None and current_date is not None and issue_date < current_date:
            report.issues.append(Issue("ISSUE_DATE_BEFORE_READING", "ERROR", "تاريخ الإصدار قبل تاريخ القراءة الحالية.", "issue_date"))
        return report

    @staticmethod
    def validate_account_numbers(account_no: str) -> ValidationReport:
        report = ValidationReport()
        if not account_no or not str(account_no).strip():
            report.issues.append(Issue("ACCOUNT_MISSING", "ERROR", "رقم الحساب مطلوب.", "account_no"))
        elif not ACCOUNT_NO_RE.match(latin_digits(str(account_no).strip())):
            report.issues.append(Issue("ACCOUNT_FORMAT", "ERROR", "رقم الحساب غير صحيح حسب صيغة الحساب (أرقام من 4 إلى 20).", "account_no"))
        return report

    @staticmethod
    def validate_fees(charges) -> ValidationReport:
        report = ValidationReport()
        from ..enums import ChargeCategory

        for idx, c in enumerate(charges):
            from ..models import InvoiceCharge

            if not isinstance(c, InvoiceCharge):
                continue
            if c.amount < Money.zero() and c.category != ChargeCategory.DISCOUNT:
                report.issues.append(Issue("NEGATIVE_FEE", "ERROR", f"الرسم «{c.name}» لا يمكن أن يكون سالباً (لاستخدام الخصم اختر نوع خصم).", f"charge[{idx}]", name=c.name))
            if c.category == ChargeCategory.DISCOUNT and c.amount < Money.zero():
                report.issues.append(Issue("DOUBLE_NEGATIVE_DISCOUNT", "WARNING", f"الخصم «{c.name}» مدخل بقيمة سالبة (سيُعامل الرقم كما هو).", f"charge[{idx}]", name=c.name))
        return report

    @staticmethod
    def validate_amount(amount: Money) -> ValidationReport:
        report = ValidationReport()
        if amount < Money.zero():
            report.issues.append(Issue("NEGATIVE_AMOUNT", "ERROR", "المبلغ النهائي سالب وغير منطقي.", "total"))
        return report

    @staticmethod
    def validate_tariff(schedule: TariffSchedule) -> ValidationReport:
        report = ValidationReport()

        if not schedule.name_ar.strip() and not schedule.name_en.strip():
            report.issues.append(Issue("TARIFF_NAME", "ERROR", "اسم التعرفة مطلوب."))
        if schedule.effective_from is None:
            report.issues.append(Issue("TARIFF_DATE", "ERROR", "تاريخ بداية التعرفة مطلوب."))
        if schedule.effective_to is not None and schedule.effective_from and schedule.effective_to <= schedule.effective_from:
            report.issues.append(Issue("TARIFF_RANGE", "ERROR", "تاريخ النهاية يجب أن يكون بعد تاريخ البداية."))

        if not schedule.tiers:
            report.issues.append(Issue("TARIFF_NO_TIERS", "ERROR", "يجب إضافة شريحة واحدة على الأقل للتعرفة."))
            return report

        # tiers ordering/overlap/gap/negativity
        # Both real-world conventions are accepted and treated as contiguous:
        #   A) 0-1500 / 1500-3000 (exclusive upper bound on the previous tier)
        #   B) 1-1500 / 1501-3000 (inclusive bounds as printed on the official invoices)
        expected_from: Optional[Decimal] = None
        for t in sorted(schedule.tiers, key=lambda x: x.from_kwh):
            if t.from_kwh < 0 or t.rate_per_kwh < 0:
                report.issues.append(Issue("TARIFF_NEGATIVE", "ERROR", "نقاط الشرائح والأسعار لا يمكن أن تكون سالبة."))
            if expected_from is None:
                if t.from_kwh not in (Decimal("0"), Decimal("1")):
                    report.issues.append(Issue(
                        "TARIFF_OVERLAP", "ERROR",
                        "هناك تداخل أو فراغ بين الشرائح — يجب أن تبدأ الشريحة الأولى من 0 أو 1، "
                        "وكل شريحة من قيمة نهاية السابقة (مثل 1-1500 ثم 1501-3000)."))
            elif t.from_kwh not in (expected_from, expected_from + 1):
                report.issues.append(Issue(
                    "TARIFF_OVERLAP", "ERROR",
                    "هناك تداخل أو فراغ بين الشرائح — يجب أن تبدأ كل شريحة من نهاية سابقتها "
                    "(مثل 1-1500 ثم 1501-3000، أو 0-1500 ثم 1500-3000)."))
            expected_from = t.to_kwh
        return report

    @staticmethod
    def validate_subscriber(s: Subscriber) -> ValidationReport:
        report = ValidationReport()
        if not s.name.strip():
            report.issues.append(Issue("SUBSCRIBER_NAME", "ERROR", "اسم المشترك مطلوب."))
        report.issues += ValidationEngine.validate_account_numbers(s.account_no).issues
        report.issues += ValidationEngine.validate_account_numbers(s.subscription_no).issues if s.subscription_no else []
        return report