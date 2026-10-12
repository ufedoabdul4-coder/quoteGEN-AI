"""Job quotation drafting validation (no provider calls)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest
from unittest import mock

import httpx
import pymupdf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import BusinessProfile, ClientInfo  # noqa: E402
from services import understanding  # noqa: E402
from services import store  # noqa: E402
from services import job_draft  # noqa: E402
from services.job_draft import (  # noqa: E402
    JobDraftError,
    _amount_in_words,
    _build_quotation,
    active_master_reference,
)


class JobDraftTests(unittest.TestCase):
    def setUp(self):
        self.data = {
            "title": "Residential Cleaning Quotation",
            "scope_sections": [{
                "heading": "Bedrooms and bathrooms",
                "items": [
                    "Dust and wipe accessible bedroom surfaces",
                    "Clean bedroom floors",
                    "Wash and sanitize bathroom fixtures",
                    "Clean mirrors and polish fittings",
                    "Remove collected waste",
                    "Inspect the finished rooms",
                    "Report any access limitations",
                    "Prepare rooms for handover",
                ],
            }],
            "phases": [
                "Site preparation",
                "Room-by-room cleaning",
                "Quality inspection",
                "Final handover",
            ],
            "cost_items": [
                {"description": f"Detailed cleaning task {index}", "amount_ngn": 100000}
                for index in range(1, 9)
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
            job_description="Bedrooms and bathrooms",
            target_total_ngn=800000,
            profile=BusinessProfile(name="Bright Works Ltd"),
            client=ClientInfo(name="Acme Ltd"),
        )

        result = understanding.understand(quotation)
        self.assertEqual(total, 800000)
        self.assertEqual(missing, ["Confirm the service address."])
        self.assertTrue(quotation.startswith("# PROPOSAL FOR RESIDENTIAL CLEANING QUOTATION"))
        self.assertGreaterEqual(quotation.count("- "), 9)
        self.assertIn("Amount in Words: Eight Hundred Thousand Naira only", quotation)
        self.assertEqual(result.financials.rows_total, 800000)
        self.assertEqual(result.financials.grand_total, 800000)
        self.assertTrue(result.financials.consistent)

    def test_draft_rejects_total_that_does_not_equal_target(self):
        self.data["cost_items"][0]["amount_ngn"] = 600001

        with self.assertRaisesRegex(JobDraftError, "did not add up to your target"):
            _build_quotation(
                self.data,
                job_description="Bedrooms and bathrooms",
                target_total_ngn=800000,
                profile=BusinessProfile(),
                client=ClientInfo(),
            )

    def test_each_separately_described_area_gets_its_own_detailed_section(self):
        areas = [
            "Bedroom 1 with toilet",
            "Bedroom 2 with toilet",
            "Bedroom 3 with toilet",
            "Sitting room and toilet",
            "Guest room with toilet",
            "Open kitchen",
            "Dining room",
            "Family lounge with balcony and BQ room with toilet",
        ]
        data = {
            **self.data,
            "scope_sections": [
                {
                    "heading": area,
                    "items": [
                        f"Prepare and inspect {area}",
                        f"Clean all accessible surfaces in {area}",
                        f"Finish and quality-check {area}",
                    ],
                }
                for area in areas
            ],
        }
        quotation, _missing, total = _build_quotation(
            data,
            job_description="\n".join(areas),
            target_total_ngn=800000,
            profile=BusinessProfile(),
            client=ClientInfo(),
        )

        self.assertEqual(total, 800000)
        for area in areas:
            self.assertIn(f"### {area}", quotation)
        self.assertGreaterEqual(quotation.count("- "), 25)

    def test_draft_rejects_fractional_or_invalid_costs(self):
        self.data["cost_items"][0]["amount_ngn"] = 500000.5

        with self.assertRaisesRegex(JobDraftError, "whole Naira"):
            _build_quotation(
                self.data,
                job_description="Bedrooms and bathrooms",
                target_total_ngn=800000,
                profile=BusinessProfile(),
                client=ClientInfo(),
            )

    def test_master_reference_removes_identity_and_old_prices(self):
        document = pymupdf.open()
        page = document.new_page()
        page.insert_text((50, 50), "Prepared for: Yinka Client")
        page.insert_text((50, 80), "Email: client@example.com")
        page.insert_text((50, 110), "Quotation No: Q-2026-19")
        page.insert_text((50, 140), "Deep clean bedroom floors | ₦250,000")
        page.insert_text((50, 170), "Quality inspection and handover")
        page.insert_text((50, 200), "Clean 3 bedrooms for 250,000")
        pdf_bytes = document.tobytes()
        document.close()

        with (
            mock.patch.object(store, "get_active_template_id", return_value="master"),
            mock.patch.object(store, "read_reference", return_value=pdf_bytes),
        ):
            reference_text = active_master_reference()

        self.assertIn("Deep clean bedroom floors", reference_text)
        self.assertIn("Quality inspection and handover", reference_text)
        self.assertNotIn("Yinka Client", reference_text)
        self.assertNotIn("client@example.com", reference_text)
        self.assertNotIn("Q-2026-19", reference_text)
        self.assertNotIn("250,000", reference_text)
        self.assertIn("Clean 3 bedrooms for [price omitted]", reference_text)

    def test_ai_prompt_uses_sanitized_master_and_exact_target(self):
        captured_prompts = []
        original_client = httpx.AsyncClient

        async def provider(request):
            payload = json.loads(request.content)
            captured_prompts.append(payload["contents"][0]["parts"][0]["text"])
            return httpx.Response(
                200,
                json={"candidates": [{
                    "content": {"parts": [{"text": json.dumps(self.data)}]},
                }]},
            )

        transport = httpx.MockTransport(provider)
        with (
            mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", "GEMINI_MODEL": "test-model"}),
            mock.patch.object(
                job_draft.httpx,
                "AsyncClient",
                side_effect=lambda timeout: original_client(timeout=timeout, transport=transport),
            ),
        ):
            result = asyncio.run(job_draft.draft_quotation(
                job_description="Bedrooms and bathrooms",
                quotation_goal="A detailed cleaning proposal",
                target_total_ngn=800000,
                profile=BusinessProfile(),
                client=ClientInfo(),
                master_reference="Bedroom cleaning; old price [price omitted]",
            ))

        self.assertIn("Bedroom cleaning; old price [price omitted]", captured_prompts[0])
        self.assertIn("target_proposal_total_ngn", captured_prompts[0])
        self.assertIn("800000", captured_prompts[0])
        self.assertEqual(result["suggested_total_ngn"], 800000)
