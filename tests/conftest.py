import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from decimal import Decimal

from kse.domain.enums import ServiceZone, SubscriberType, TariffMethod
from kse.domain.models import TariffSchedule, TariffTier
from kse.infrastructure.sqlite.db import connect  # noqa: E402


@pytest.fixture
def mem_db():
    conn = connect(":memory:")
    yield conn
    conn.close()


def make_schedule(subscriber_type=SubscriberType.RESIDENTIAL, method=TariffMethod.FLAT,
                  tiers=None, rate=Decimal("10"), name="Test Tariff",
                  effective_from=None, effective_to=None, active=True, version="1",
                  service_zone=ServiceZone.TRADITIONAL):
    import datetime as dt

    s = TariffSchedule(
        name_ar=name,
        name_en=name,
        subscriber_type=subscriber_type,
        method=method,
        service_zone=service_zone,
        version=version,
        effective_from=effective_from or dt.date(2024, 1, 1),
        effective_to=effective_to,
        is_active=active,
    )
    if tiers is not None:
        s.tiers = tiers
    elif method == TariffMethod.FLAT:
        s.tiers = [TariffTier(tier_no=1, from_kwh=Decimal("0"), to_kwh=None, rate_per_kwh=rate)]
    else:
        s.tiers = [
            TariffTier(tier_no=1, from_kwh=Decimal("0"), to_kwh=Decimal("1500"), rate_per_kwh=Decimal("10")),
            TariffTier(tier_no=2, from_kwh=Decimal("1500"), to_kwh=Decimal("3000"), rate_per_kwh=Decimal("15")),
            TariffTier(tier_no=3, from_kwh=Decimal("3000"), to_kwh=Decimal("4000"), rate_per_kwh=Decimal("20")),
            TariffTier(tier_no=4, from_kwh=Decimal("4000"), to_kwh=None, rate_per_kwh=Decimal("25")),
        ]
    return s


def progressive_tiers():
    return [
        TariffTier(tier_no=1, from_kwh=Decimal("0"), to_kwh=Decimal("1000"), rate_per_kwh=Decimal("10")),
        TariffTier(tier_no=2, from_kwh=Decimal("1000"), to_kwh=Decimal("2000"), rate_per_kwh=Decimal("15")),
        TariffTier(tier_no=3, from_kwh=Decimal("2000"), to_kwh=Decimal("3000"), rate_per_kwh=Decimal("20")),
        TariffTier(tier_no=4, from_kwh=Decimal("3000"), to_kwh=Decimal("4000"), rate_per_kwh=Decimal("25")),
        TariffTier(tier_no=5, from_kwh=Decimal("4000"), to_kwh=None, rate_per_kwh=Decimal("30")),
    ]