"""Debt carry-forward accounting.

Every invoice's ``total_due`` includes the ``previous_debt`` entered on it, and the app now
pre-fills that field with the subscriber's outstanding balance. The older unpaid invoice is
never closed, so adding up ``total_due`` / remaining balances counts the same debt twice (or
more, along a chain of unpaid months).

:func:`allocate` walks each subscriber's invoices in order and splits every invoice into

* ``duplicated`` - the part of its ``total_due`` that merely repeats balances already billed on
  OLDER invoices (``previous_debt`` that is attributable to them), and
* ``outstanding`` - what is genuinely still owed from that invoice after debts rolled into
  later invoices and payments made on older invoices after the roll-over are taken out.
* ``applied`` - the part of the recorded cash that settles THIS invoice's new billing. Cash is
  applied oldest-first (FIFO) inside each subscriber's chain, so a payment made on a newer
  invoice that carries old debt settles the old month first. This keeps every monthly "paid"
  figure non-negative and equal to the cash actually applied.

Invariant (no over-payments): ``sum(total_due) - sum(duplicated) - sum(paid) == sum(outstanding)``.
When payments do not exceed the new billing, ``sum(applied) == sum(paid)``.
Debt that no older invoice can account for (an opening balance) is treated as new billing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

ZERO = Decimal("0")


@dataclass
class CarryResult:
    outstanding: dict[int, Decimal] = field(default_factory=dict)   # keyed by id(invoice object)
    duplicated: dict[int, Decimal] = field(default_factory=dict)
    applied: dict[int, Decimal] = field(default_factory=dict)       # cash settling new billing

    def outstanding_of(self, invoice) -> Decimal:
        return self.outstanding.get(id(invoice), ZERO)

    def duplicated_of(self, invoice) -> Decimal:
        return self.duplicated.get(id(invoice), ZERO)

    def applied_of(self, invoice) -> Decimal:
        return self.applied.get(id(invoice), ZERO)

    def net_total(self, invoice) -> Decimal:
        """New money billed by this invoice (total_due without repeated older balances)."""
        return invoice.total_due.raw - self.duplicated_of(invoice)


def _group_key(inv):
    if getattr(inv, "subscriber_id", None) is not None:
        return ("sub", inv.subscriber_id)
    if getattr(inv, "account_no", None):
        return ("acct", inv.account_no)
    return ("inv", id(inv))


def allocate(invoices) -> CarryResult:
    result = CarryResult()
    groups: dict[tuple, list] = {}
    for inv in invoices:
        groups.setdefault(_group_key(inv), []).append(inv)

    for group in groups.values():
        group.sort(key=lambda i: (i.issue_date, i.id if i.id is not None else 0))
        outstanding: list[Decimal] = []
        net_billed: list[Decimal] = []
        for j, inv in enumerate(group):
            remaining = max(inv.total_due.raw - inv.paid_amount.raw, ZERO)
            claim = max(inv.previous_debt.raw, ZERO)
            capacity = sum(net_billed, ZERO)                 # what older invoices billed
            attributable = min(claim, capacity)
            # take the claim from the NEWEST older invoices first
            left = attributable
            for k in range(j - 1, -1, -1):
                if left <= 0:
                    break
                take = min(outstanding[k], left)
                outstanding[k] -= take
                left -= take
            settled_since = left            # older balance paid AFTER this invoice was issued
            remaining = max(remaining - settled_since, ZERO)
            outstanding.append(remaining)
            net_billed.append(inv.total_due.raw - attributable)
            result.duplicated[id(inv)] = attributable
        for inv, value in zip(group, outstanding):
            result.outstanding[id(inv)] = value

        # Cash application (FIFO): all money recorded on the chain settles the oldest
        # new billing first. The old "net - outstanding" formula produced a negative
        # "paid" bucket for the month that carried the debt and an inflated one for the
        # month it came from.
        cash = sum((max(inv.paid_amount.raw, ZERO) for inv in group), ZERO)
        for inv, net in zip(group, net_billed):
            take = min(max(net, ZERO), cash)
            result.applied[id(inv)] = take
            cash -= take
    return result
