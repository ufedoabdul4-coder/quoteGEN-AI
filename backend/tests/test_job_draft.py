"""Job quotation drafting validation (no provider calls)."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import BusinessProfile, ClientInfo  # noqa: E402
from services import understanding  # noqa: E402
from services.job_draft import JobDraftError, _amount_in_words, _build_quotation  # noqa: E402


class JobDraftTests(unittest.TestCase):
    def setUp(self):
        self.data = {
            "title": "Residential Cleaning Quotation",
            "scope_items": ["Clean bedrooms and bathrooms", "Clean kitchen and living areas"],
            "phases": ["Site preparation", "Room-by-room cleaning", "Final inspection"],
            "cost_items": [
                {"description": "Bedroom and bathroom cleaning", "amount_ngn": 500000},
                {"description": "Kitchen and living area cleaning", "amount_ngn": 300000},
            ],
            "terms": ["Confirm site measurements before work begins."],
            "missing_info": ["Confirm the service address."],
        }

    def test_amount_in_words_handles_large_ngn_amounts(self):
        self.assertEqual(_amount_in_words(850000), "Eight Hundred Fifty Thousand Naira only")
        self.assertEqual(_amount_in_words(1000000000), "One Billion Naira only")

    def test_draft_parses_as_a_reconciled_quotation(self):
        quotation, missing, total = _build_quotation(
            self.data,
            budget_ngn=850000,
            profile=BusinessProfile(name="Bright Works Ltd"),
            client=ClientInfo(name="Acme Ltd"),
        )

        result = understanding.understand(quotation)
        self.assertEqual(total, 800000)
        self.assertEqual(missing, ["Confirm the service address."])
        self.assertIn("Amount in Words: Eight Hundred Thousand Naira only", quotation)
        self.assertEqual(result.financials.rows_total, 800000)
        self.assertEqual(result.financials.grand_total, 800000)
        self.assertTrue(result.financials.consistent)

    def test_draft_rejects_total_above_approved_budget(self):
        self.data["cost_items"][0]["amount_ngn"] = 600000

        with self.assertRaisesRegex(JobDraftError, "exceeded the approved budget"):
            _build_quotation(
                self.data,
                budget_ngn=850000,
                profile=BusinessProfile(),
                client=ClientInfo(),
            )

    def test_draft_rejects_fractional_or_invalid_costs(self):
        self.data["cost_items"][0]["amount_ngn"] = 500000.5

        with self.assertRaisesRegex(JobDraftError, "whole Naira"):
            _build_quotation(
                self.data,
                budget_ngn=850000,
                profile=BusinessProfile(),
                client=ClientInfo(),
            )
