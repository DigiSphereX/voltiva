"""Debt carry-forward accounting (no double counting of rolled-over balances)."""
import datetime as dt
import random
from decimal import Decimal
from types import SimpleNamespace

from kse.application.analytics import AnalyticsService
from kse.application.carry_forward import allocate
from kse.domain.enums import InvoiceStatus, PaymentStatus
from kse.domain.money import Money


def inv(sub, day, total, paid=0, prev=0, current=None):
    """Light stand-in with the attributes the allocation / analytics read."""
    total_m, paid_m = Money.of(total), Money.of(paid)
    status = (PaymentStatus.PAID if paid >= total else PaymentStatus.PARTIAL if paid > 0 else PaymentStatus.UNPAID)
    return SimpleNamespace(
        id=None, subscriber_id=sub, account_no=f"A{sub}", subscriber_name=f"S{sub}", subscription_no="",
        issue_date=dt.date(2025, 1, day), total_due=total_m, paid_amount=paid_m, previous_debt=Money.of(prev),
        current_amount=Money.of(current if current is not None else total - prev),
        adjusted_kwh=Decimal("100"), payment_status=status, status=InvoiceStatus.ACTIVE,
        remaining_balance=Money.of(max(total - paid, 0)), official_amount=None)


def totals(invoices):
    a = allocate(invoices)
    net = sum(a.net_total(i) for i in invoices)
    out = sum(a.outstanding_of(i) for i in invoices)
    paid = sum(i.paid_amount.raw for i in invoices)
    return a, net, out, paid


def test_chain_of_unpaid_months_counts_each_charge_once():
    a, b, c = inv(1, 1, 100), inv(1, 2, 150, prev=100), inv(1, 3, 210, paid=100, prev=150)
    al, net, out, paid = totals([a, b, c])
    assert net == 100 + 50 + 60            # only NEW money: 210, not 460
    assert out == 110                      # what the customer really owes
    assert al.outstanding_of(a) == 0 and al.outstanding_of(b) == 0 and al.outstanding_of(c) == 110


def test_payment_on_older_invoice_after_roll_over_is_not_lost():
    a = inv(1, 1, 100, paid=40)            # 40 paid after the next invoice carried 100
    b = inv(1, 2, 150, prev=100)
    al, net, out, paid = totals([a, b])
    assert net == 150 and paid == 40 and out == 110       # 100 + 50 billed, 40 paid
    assert net - paid == out


def test_opening_balance_without_older_invoice_is_new_billing():
    only = inv(1, 1, 130, prev=30)
    al, net, out, paid = totals([only])
    assert net == 130 and out == 130 and al.duplicated_of(only) == 0


def test_subscribers_are_independent():
    a, b = inv(1, 1, 100), inv(2, 2, 150, prev=100)       # b's debt is NOT subscriber 1's
    al, net, out, paid = totals([a, b])
    assert net == 250 and out == 250


def test_cash_is_applied_oldest_first_and_never_negative():
    # The customer paid 500 on the newer invoice, which also carries the older month's debt.
    # The old "billed - outstanding" shortcut reported 1 000 paid for the older month and
    # -500 for the newer one.
    a, b = inv(1, 1, 1000), inv(1, 2, 2000, paid=500, prev=1000)
    al, net, out, paid = totals([a, b])
    assert al.applied_of(a) == 500 and al.applied_of(b) == 0
    assert sum(al.applied_of(i) for i in (a, b)) == paid


def test_cash_over_new_billing_is_capped_to_new_billing():
    a, b = inv(1, 1, 100), inv(1, 2, 200, paid=250, prev=100)
    al, net, out, paid = totals([a, b])
    assert net == 200 and paid == 250 and out == 0
    assert sum(al.applied_of(i) for i in (a, b)) == net


def test_input_order_does_not_matter():
    chain = [inv(1, 1, 100), inv(1, 2, 150, prev=100), inv(1, 3, 210, paid=100, prev=150)]
    shuffled = list(reversed(chain))
    assert totals(chain)[1:] == totals(shuffled)[1:]


def test_random_chains_keep_the_accounting_identity():
    rnd = random.Random(42)
    for _ in range(300):
        invoices, owed = [], 0
        for day in range(1, rnd.randint(2, 8)):
            current = rnd.randint(0, 200)
            carry = owed if rnd.random() < 0.8 else rnd.randint(0, owed)    # sometimes carry less/more
            total = current + carry
            paid = rnd.randint(0, total)
            invoices.append(inv(1, day, total, paid=paid, prev=carry))
            owed = total - paid
        al, net, out, paid = totals(invoices)
        assert all(al.outstanding_of(i) >= 0 for i in invoices)
        assert net - paid == out, (net, paid, out)
        applied = sum(al.applied_of(i) for i in invoices)
        assert all(al.applied_of(i) >= 0 for i in invoices)
        assert applied == min(paid, net), (applied, paid, net)


def test_analytics_kpis_use_the_allocation():
    class Repo:
        def __init__(self, items): self.items = items
        def list_recent(self, limit=50): return list(self.items)
    chain = [inv(1, 1, 100), inv(1, 2, 150, prev=100), inv(1, 3, 210, paid=100, prev=150)]
    an = AnalyticsService(Repo(chain))
    stats = an.dashboard()
    assert stats["total_amount"].raw == 210
    assert stats["total_unpaid"].raw == 110
    assert stats["total_paid"].raw == 100
    assert stats["unpaid_count"] == 1                       # the two rolled-over invoices are not "unpaid"
    # monthly: settled + outstanding == net billed, and the chart never shows a rolled invoice as unpaid
    month = stats["monthly"]["2025-01"]
    assert month["amount"].raw - month["paid"].raw == 110
    rows = an.payment_breakdown(chain)
    assert rows["UNPAID"]["amount"].raw + rows["PARTIAL"]["amount"].raw == 110
    assert an.subscriber_leaders(chain)[0]["unpaid"].raw == 110
