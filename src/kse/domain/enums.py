"""Enums used across the billing domain.

Stored in SQLite as TEXT names (enum `value`). `label` is a business *data*
label (used on reports/exports); UI chrome strings live in the i18n resource
files instead.
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
    def label(self) -> str:
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
    def label(self) -> str:
        return {"FLAT": "Flat rate", "PROGRESSIVE": "Progressive"}[self.value]


class ServiceZone(str, enum.Enum):
    """Region/service class of the electricity supply.

    The official billing differs between the classic grid, smart-meter areas
    and the private (investment) service-and-collection companies, each of
    which may keep its own tariff over the same subscriber type & period.
    """

    TRADITIONAL = "TRADITIONAL"          # classic public grid (traditional collection)
    SMART_METER = "SMART_METER"            # smart-meter areas (smart service & collection)
    INVESTMENT = "INVESTMENT"              # investment companies (service & collection)

    @property
    def label(self) -> str:
        return {
            "TRADITIONAL": "Traditional",
            "SMART_METER": "Smart meter",
            "INVESTMENT": "Investment",
        }[self.value]


class MeterScenario(str, enum.Enum):
    NORMAL = "NORMAL"
    MULTIPLIER = "MULTIPLIER"
    REPLACEMENT = "REPLACEMENT"
    RESET = "RESET"
    ROLLOVER = "ROLLOVER"

    @property
    def label(self) -> str:
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


class InvoiceStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"
    RECALCULATED = "RECALCULATED"


class ChargeCategory(str, enum.Enum):
    FIXED_FEE = "FIXED_FEE"              # meter fee / circuit-breaker fee
    ADDITIONAL_FEE = "ADDITIONAL_FEE"    # special reading / miscellaneous prices
    SERVICE_FEE = "SERVICE_FEE"
    DISCOUNT = "DISCOUNT"
    SETTLEMENT = "SETTLEMENT"            # reconciliation
    PENALTY = "PENALTY"                  # fine
    DEBT = "DEBT"                        # previous debt
    OTHER = "OTHER"


class DataSource(str, enum.Enum):
    OFFICIAL = "OFFICIAL"
    HISTORICAL = "HISTORICAL"
    USER_DEFINED = "USER_DEFINED"
    ESTIMATED = "ESTIMATED"
    UNKNOWN = "UNKNOWN"

    @property
    def label(self) -> str:
        return {
            "OFFICIAL": "Official",
            "HISTORICAL": "Historical",
            "USER_DEFINED": "User-defined",
            "ESTIMATED": "Estimated",
            "UNKNOWN": "Unknown",
        }[self.value]


class ComparisonStatus(str, enum.Enum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    NOT_COMPARED = "NOT_COMPARED"
