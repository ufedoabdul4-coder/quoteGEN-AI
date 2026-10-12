"""Deterministic financial reconciliation.

The totals in a quotation must be provable from the priced rows the provider
wrote. This module adds those rows up and compares the result with whatever
total the document states. It never edits a figure: a mismatch becomes a
finding, and the provider decides what to do about it. That is the difference
between "the system noticed your total is wrong" and "the software quietly
changed your price".
"""

from __future__ import annotations

from models import FinancialSummary, SemanticBlock

_ROW_TYPES = ("table_row", "cost_amount")
_TOTAL_TYPES = ("subtotal", "grand_total")


def reconcile(blocks: list[SemanticBlock]) -> tuple[FinancialSummary, list[str]]:
    from services import classify

    warnings: list[str] = []
    currency = ""
    row_amounts: list[float] = []
    subtotal: float | None = None
    grand: float | None = None

    for block in blocks:
        if block.value is not None and block.type in _ROW_TYPES:
            row_amounts.append(float(block.value))
            if not currency:
                currency = classify.currency_of(block.figure or block.text)
        if block.type in _TOTAL_TYPES and block.value is not None:
            if block.type == "grand_total":
                grand = float(block.value)
            else:
                subtotal = float(block.value)
            if not currency:
                currency = classify.currency_of(block.figure or block.text)

    rows_total = round(sum(row_amounts), 2) if row_amounts else None
    stated = grand if grand is not None else subtotal

    difference: float | None = None
    consistent = True
    if rows_total is not None and stated is not None:
        difference = round(rows_total - stated, 2)
        consistent = abs(difference) <= 0.5
        if not consistent:
            warnings.append(
                f"the priced lines add up to {rows_total:,.2f} but the stated total is "
                f"{stated:,.2f} (a difference of {difference:,.2f})"
            )

    note = ""
    if rows_total is None and stated is None:
        note = "no monetary figures were found"
    elif rows_total is not None and stated is None:
        note = "priced lines were found but no stated total"

    summary = FinancialSummary(
        currency=currency,
        rows_total=rows_total,
        subtotal=subtotal,
        grand_total=grand,
        stated_total=stated,
        difference=difference,
        consistent=consistent,
        note=note,
    )
    return summary, warnings
