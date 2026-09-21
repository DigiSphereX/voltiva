"""Enums used across the billing domain.

Stored in SQLite as TEXT names (enum `value`). `label_ar`/`label_en` are
business *data* labels (used on reports/exports), UI chrome strings live in
the i18n resource files instead.
"""
from __future__ import annotations

import enum


class SubscriberType(str, enum.Enum):
    RESIDENTIAL = "RESIDENTIAL"
    COMMERCIAL = "COMMERCIAL"
    INDUSTRIAL = "INDUSTRIAL"
    AGRICULTURAL = "AGRICULTURAL"
    GOVERNMENTAL = "GOVERNMENTAL"
    OTHER = "OTHER"

    @property
    def label_ar(self) -> str:
        return {
            "RESIDENTIAL": "منزلي",
            "COMMERCIAL": "تجاري",
            "INDUSTRIAL": "صناعي",
            "AGRICULTURAL": "زراعي",
            "GOVERNMENTAL": "حكومي",
            "OTHER": "أخرى",
        }[self.value]

    @property
    def label_en(self) -> str:
        return {
            "RESIDENTIAL": "Residential",
            "COMMERCIAL": "Commercial",
            "INDUSTRIAL": "Industrial",
            "AGRICULTURAL": "Agricultural",
            "GOVERNMENTAL": "Governmental",
            "OTHER": "Other",
        }[self.value]


class TariffMethod(str, enum.Enum):
    FLAT = "FLAT"
    PROGRESSIVE = "PROGRESSIVE"

    @property
    def label_ar(self) -> str:
        return {"FLAT": "تعرفة ثابتة", "PROGRESSIVE": "تعرفة شرائح"}[self.value]

    @property
    def label_en(self) -> str:
        return {"FLAT": "Flat rate", "PROGRESSIVE": "Progressive (tiered)"}[self.value]


class ServiceZone(str, enum.Enum):
    """Region/service class of the electricity supply.

    The official billing differs between the classic grid, smart-meter areas
    and the private (investment) service-and-collection companies, each of
    which may keep its own tariff over the same subscriber type & period.
    """

    TRADITIONAL = "TRADITIONAL"          # الشبكة الكلاسيكية (الجباية التقليدية)
    SMART_METER = "SMART_METER"          # مناطق العداد الذكي / الخدمة والجباية الذكية
    INVESTMENT = "INVESTMENT"            # شركات الاستثمار (الخدمة والجباية)

    @property
    def label_ar(self) -> str:
        return {
            "TRADITIONAL": "تقليدي (شبكة عامة)",
            "SMART_METER": "عداد ذكي",
            "INVESTMENT": "استثمار (خدمة وجباية)",
        }[self.value]

    @property
    def label_en(self) -> str:
        return {
            "TRADITIONAL": "Traditional (public grid)",
            "SMART_METER": "Smart meter",
            "INVESTMENT": "Investment (service & collection)",
        }[self.value]


class MeterScenario(str, enum.Enum):
    NORMAL = "NORMAL"
    MULTIPLIER = "MULTIPLIER"
    REPLACEMENT = "REPLACEMENT"
    RESET = "RESET"
    ROLLOVER = "ROLLOVER"

    @property
    def label_ar(self) -> str:
        return {
            "NORMAL": "عداد طبيعي",
            "MULTIPLIER": "عداد بمعامل قياس",
            "REPLACEMENT": "استبدال العداد",
            "RESET": "إعادة ضبط (Reset)",
            "ROLLOVER": "Rollover",
        }[self.value]

    @property
    def label_en(self) -> str:
        return {
            "NORMAL": "Normal meter",
            "MULTIPLIER": "Multiplier meter",
            "REPLACEMENT": "Meter replacement",
            "RESET": "Reset",
            "ROLLOVER": "Rollover",
        }[self.value]


class MeterType(str, enum.Enum):
    ELECTROMECHANICAL = "ELECTROMECHANICAL"
    ELECTRONIC = "ELECTRONIC"
    OTHER = "OTHER"


class MeterPhase(str, enum.Enum):
    SINGLE = "SINGLE"
    THREE = "THREE"


class PaymentStatus(str, enum.Enum):
    UNPAID = "UNPAID"
    PARTIAL = "PARTIAL"
    PAID = "PAID"

    @property
    def label_ar(self) -> str:
        return {"UNPAID": "غير مدفوعة", "PARTIAL": "مدفوعة جزئياً", "PAID": "مدفوعة"}[self.value]


class InvoiceStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"
    RECALCULATED = "RECALCULATED"


class ChargeCategory(str, enum.Enum):
    FIXED_FEE = "FIXED_FEE"            # أجور المقياس / قاطع الدورة…
    ADDITIONAL_FEE = "ADDITIONAL_FEE"  # قراءة خاصة / أثمان مختلفة
    SERVICE_FEE = "SERVICE_FEE"
    DISCOUNT = "DISCOUNT"
    SETTLEMENT = "SETTLEMENT"          # تسوية
    PENALTY = "PENALTY"                # غرامة
    DEBT = "DEBT"                      # دين سابق
    OTHER = "OTHER"

    @property
    def label_ar(self) -> str:
        return {
            "FIXED_FEE": "رسوم ثابتة",
            "ADDITIONAL_FEE": "رسوم إضافية",
            "SERVICE_FEE": "رسوم خدمة",
            "DISCOUNT": "خصم",
            "SETTLEMENT": "تسوية",
            "PENALTY": "غرامة",
            "DEBT": "دين سابق",
            "OTHER": "أخرى",
        }[self.value]


class DataSource(str, enum.Enum):
    OFFICIAL = "OFFICIAL"
    HISTORICAL = "HISTORICAL"
    USER_DEFINED = "USER_DEFINED"
    ESTIMATED = "ESTIMATED"
    UNKNOWN = "UNKNOWN"

    @property
    def label_ar(self) -> str:
        return {
            "OFFICIAL": "رسمي",
            "HISTORICAL": "تاريخي",
            "USER_DEFINED": "من المستخدم",
            "ESTIMATED": "تقديري",
            "UNKNOWN": "غير معروف",
        }[self.value]


class ComparisonStatus(str, enum.Enum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    NOT_COMPARED = "NOT_COMPARED"

    @property
    def label_ar(self) -> str:
        return {"MATCH": "مطابق", "MISMATCH": "غير مطابق", "NOT_COMPARED": "لم تتم المقارنة"}[self.value]