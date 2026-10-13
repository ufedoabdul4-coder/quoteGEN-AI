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
from services import pipeline  # noqa: E402
from services import store  # noqa: E402
from services import job_draft  # noqa: E402
from services.job_draft import (  # noqa: E402
    JobDraftError,
    _amount_in_words,
    _allocate_costs,
    _build_quotation,
    active_master_reference,
)


class JobDraftTests(unittest.TestCase):
    def setUp(self):
        self.data = {
            "service_type": "residential_deep_cleaning",
            "title": "Residential Cleaning Quotation",
            "project_introduction": (
                "A proposed cleaning service for the requested residential areas."
            ),
            "scope_sections": [{
                "heading": "Bedrooms and bathrooms",
                "source_reference": "Bedrooms and bathrooms",
                "quantity": "",
                "associated_facilities": [],
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
                {
                    "title": "Preparation and mobilisation",
                    "description": "Prepare the site and mobilise the proposed team.",
                    "activities": ["Protect occupied areas", "Remove loose surface dust"],
                    "cost_items": [
                        {"description": f"Preparation task {index}", "relative_weight": 1}
                        for index in range(1, 4)
                    ],
                },
                {
                    "title": "Detailed room cleaning",
                    "description": "Clean the rooms and fixtures in the agreed scope.",
                    "activities": ["Clean surfaces", "Sanitise bathroom fixtures"],
                    "cost_items": [
                        {"description": f"Room cleaning task {index}", "relative_weight": 1}
                        for index in range(1, 4)
                    ],
                },
                {
                    "title": "Final inspection and handover",
                    "description": "Inspect completed work and prepare for handover.",
                    "activities": ["Inspect completed areas", "Record outstanding access issues"],
                    "cost_items": [
                        {"description": f"Handover task {index}", "relative_weight": 1}
                        for index in range(1, 3)
                    ],
                },
            ],
            "equipment_materials": ["Proposed vacuum equipment and suitable cleaning cloths"],
            "quality_assurance": [
                "Supervisor checks each completed room.",
                "Correct accessible missed areas before handover.",
                "Confirm any unresolved site-access limitations with the client.",
            ],
            "safety_considerations": [],
            "assumptions_exclusions": [],
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
            profile=BusinessProfile(
                name="Bright Works Ltd",
                phone="+2348000000000",
                email="hello@brightworks.example",
                address="Lagos, Nigeria",
            ),
            client=ClientInfo(
                name="Acme Ltd",
                contact_person="Ada Client",
                address="Ikeja, Lagos",
            ),
        )

        result = understanding.understand(quotation)
        self.assertEqual(total, 800000)
        self.assertEqual(missing, ["Confirm the service address."])
        self.assertTrue(quotation.startswith("# PROPOSAL FOR RESIDENTIAL CLEANING QUOTATION"))
        self.assertIn("Service type: Residential deep cleaning", quotation)
        self.assertIn("Company phone: +2348000000000", quotation)
        self.assertIn("Company email: hello@brightworks.example", quotation)
        self.assertIn("Client address: Ikeja, Lagos", quotation)
        self.assertGreaterEqual(quotation.count("- "), 9)
        self.assertIn("Amount in Words: Eight Hundred Thousand Naira only", quotation)
        self.assertIn("## Project overview", quotation)
        self.assertIn("## Equipment, tools and materials proposed for deployment", quotation)
        self.assertIn("## Project execution and quality assurance", quotation)
        self.assertIn("## Consolidated project cost summary", quotation)
        self.assertEqual(quotation.count("| Grand Total |"), 1)
        self.assertEqual(quotation.count("| Subtotal - "), 6)
        self.assertEqual(result.financials.rows_total, 800000)
        self.assertEqual(result.financials.grand_total, 800000)
        self.assertTrue(result.financials.consistent)
        rendered, report, _previews = pipeline.build(
            "premium_business",
            result,
            BusinessProfile(name="Bright Works Ltd"),
            ClientInfo(name="Acme Ltd"),
            result.title,
            make_previews=False,
        )
        self.assertTrue(rendered.pdf_bytes.startswith(b"%PDF"))
        self.assertGreaterEqual(rendered.page_count, 1)
        self.assertTrue(report.ok)

    def test_server_allocates_exact_target_using_relative_weights(self):
        cost_items = [
            {"description": f"Work item {index}", "relative_weight": index}
            for index in range(1, 9)
        ]
        allocated = _allocate_costs(cost_items, target_total_ngn=850001)

        self.assertEqual(sum(amount for _, amount in allocated), 850001)
        self.assertTrue(all(amount >= 1 for _, amount in allocated))
        self.assertEqual(allocated[0][0], "Work item 1")
        self.assertLess(allocated[0][1], allocated[-1][1])

    def test_server_reconciles_model_amounts_to_target(self):
        phases = [
            {
                **phase,
                "cost_items": [
                    {"description": item["description"], "amount_ngn": 1}
                    for item in phase["cost_items"]
                ],
            }
            for phase in self.data["phases"]
        ]
        data = {
            **self.data,
            "phases": phases,
        }
        _quotation, _missing, total = _build_quotation(
            data,
            job_description="Bedrooms and bathrooms",
            target_total_ngn=850000,
            profile=BusinessProfile(),
            client=ClientInfo(),
        )

        self.assertEqual(total, 850000)

    def test_draft_rejects_service_type_that_differs_from_user_selection(self):
        with self.assertRaisesRegex(JobDraftError, "selected cleaning service type"):
            _build_quotation(
                {**self.data, "service_type": "post_construction_cleaning"},
                cleaning_type="residential_deep_cleaning",
                job_description="Three bedrooms",
                target_total_ngn=800000,
                profile=BusinessProfile(),
                client=ClientInfo(),
            )

    def test_proposal_does_not_invent_terms_when_none_are_supported(self):
        quotation, _missing, _total = _build_quotation(
            {**self.data, "terms": []},
            job_description="Bedrooms and bathrooms",
            target_total_ngn=800000,
            profile=BusinessProfile(),
            client=ClientInfo(),
        )

        self.assertNotIn("## Terms and conditions", quotation)

    def test_cost_allocation_rejects_invalid_weights_and_too_small_target(self):
        for weight in (0, -1, "NaN", "Infinity", "1e-13"):
            with self.subTest(weight=weight):
                with self.assertRaisesRegex(JobDraftError, "invalid cost allocation weight"):
                    _allocate_costs(
                        [{"description": "Work", "relative_weight": weight}] * 8,
                        target_total_ngn=850000,
                    )
        with self.assertRaisesRegex(JobDraftError, "at least"):
            _allocate_costs(
                [{"description": "Work", "relative_weight": 1}] * 8,
                target_total_ngn=7,
            )

    def test_each_separately_described_area_gets_its_own_detailed_section(self):
        areas = [
            "3 bedrooms with toilets",
            "Sitting room and toilet",
            "Guest room with toilet",
            "Open kitchen",
            "Dining room",
            "Family lounge with balcony",
            "BQ",
            "1 additional room with toilet",
        ]
        detailed_tasks = [
            ["Dust accessible bedroom surfaces", "Clean bedroom floors", "Sanitise the attached toilets"],
            ["Dust living-room surfaces", "Wipe accessible furniture exteriors", "Clean the sitting-room toilet"],
            ["Dust guest-room fixtures", "Clean guest-room flooring", "Sanitise the guest toilet"],
            ["Wipe accessible worktops", "Clean the sink and taps", "Clean kitchen flooring"],
            ["Wipe accessible dining surfaces", "Clean visible fixtures", "Clean dining-area flooring"],
            ["Dust lounge fixtures", "Clean accessible balcony surfaces", "Remove loose balcony debris"],
            ["Confirm BQ facilities before detailing", "Clean confirmed accessible surfaces", "Flag unspecified BQ areas for review"],
            ["Dust the additional room", "Clean the room floor", "Sanitise its toilet"],
        ]
        data = {
            **self.data,
            "scope_sections": [
                {
                    "heading": area,
                    "source_reference": area,
                    "quantity": (
                        "3 bedrooms" if area == "3 bedrooms with toilets"
                        else "1 additional room" if area == "1 additional room with toilet"
                        else ""
                    ),
                    "associated_facilities": (
                        ["toilets"] if "toilet" in area.lower() else []
                    ),
                    "items": detailed_tasks[index],
                }
                for index, area in enumerate(areas)
            ],
            "missing_info": ["Confirm which facilities are included in the BQ."],
        }
        quotation, missing, total = _build_quotation(
            data,
            job_description="\n".join(areas),
            target_total_ngn=800000,
            profile=BusinessProfile(),
            client=ClientInfo(),
        )

        self.assertEqual(total, 800000)
        for area in areas:
            self.assertIn(f". {area}", quotation)
        self.assertIn("3 bedrooms with toilets", quotation)
        self.assertIn("1 additional room with toilet", quotation)
        self.assertIn("Wipe accessible worktops", quotation)
        self.assertIn("Confirm BQ facilities before detailing", quotation)
        self.assertEqual(missing, ["Confirm which facilities are included in the BQ."])
        self.assertGreaterEqual(quotation.count("- "), 25)

    def test_selected_office_service_type_is_rendered_without_changing_finances(self):
        quotation, _missing, total = _build_quotation(
            {**self.data, "service_type": "office_cleaning"},
            cleaning_type="office_cleaning",
            job_description="Bedrooms and bathrooms",
            target_total_ngn=800000,
            profile=BusinessProfile(),
            client=ClientInfo(),
        )

        self.assertIn("Service type: Office cleaning", quotation)
        self.assertEqual(total, 800000)

    def test_post_construction_and_office_types_are_schema_constrained(self):
        captured = []
        original_client = httpx.AsyncClient

        async def provider(request):
            payload = json.loads(request.content)
            prompt = payload["contents"][0]["parts"][0]["text"]
            source_json = prompt.split("data:\n", 1)[1].split(
                "\n\nThe active master proposal", 1,
            )[0]
            source = json.loads(source_json)
            captured.append((source, payload["generationConfig"]["responseSchema"]))
            response_data = {**self.data, "service_type": source["selected_cleaning_type"]}
            return httpx.Response(
                200,
                json={"candidates": [{
                    "content": {"parts": [{"text": json.dumps(response_data)}]},
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
            for service_type, label in (
                ("post_construction_cleaning", "Post-construction cleaning"),
                ("office_cleaning", "Office cleaning"),
            ):
                result = asyncio.run(job_draft.draft_quotation(
                    cleaning_type=service_type,
                    job_description="Bedrooms and bathrooms",
                    quotation_goal="Prepare a service-specific proposal",
                    target_total_ngn=800000,
                    profile=BusinessProfile(),
                    client=ClientInfo(),
                    master_reference="Reusable work sequence and handover guidance",
                ))
                self.assertIn(f"Service type: {label}", result["quotation_text"])

        self.assertEqual(
            [source["selected_cleaning_type"] for source, _schema in captured],
            ["post_construction_cleaning", "office_cleaning"],
        )
        for source, schema in captured:
            self.assertEqual(
                schema["properties"]["service_type"]["enum"],
                [source["selected_cleaning_type"]],
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
        captured_schemas = []
        original_client = httpx.AsyncClient

        async def provider(request):
            payload = json.loads(request.content)
            captured_prompts.append(payload["contents"][0]["parts"][0]["text"])
            captured_schemas.append(payload["generationConfig"]["responseSchema"])
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
        self.assertIn("relative_weight", captured_prompts[0])
        self.assertIn("server allocates the exact target total", captured_prompts[0])
        self.assertIn('"equipment_materials"', captured_prompts[0])
        self.assertIn('"quality_assurance"', captured_prompts[0])
        self.assertIn('"safety_considerations"', captured_prompts[0])
        self.assertIn('"assumptions_exclusions"', captured_prompts[0])
        self.assertIn("each with a description, practical activities", captured_prompts[0])
        self.assertIn('"selected_cleaning_type": "residential_deep_cleaning"', captured_prompts[0])
        self.assertIn("The selected cleaning type in the input is authoritative", captured_prompts[0])
        self.assertIn("Residential deep cleaning and regular house cleaning do not imply", captured_prompts[0])
        self.assertIn("Include those additional services only when explicitly selected or requested.", captured_prompts[0])
        self.assertIn("800000", captured_prompts[0])
        self.assertEqual(
            captured_schemas[0]["properties"]["service_type"]["enum"],
            ["residential_deep_cleaning"],
        )
        self.assertEqual(result["suggested_total_ngn"], 800000)

    def test_provider_quota_error_is_exposed_without_leaking_api_key(self):
        original_client = httpx.AsyncClient

        async def provider(_request):
            return httpx.Response(
                429,
                json={"error": {
                    "message": "Quota exceeded for key test-key; retry later.",
                    "status": "RESOURCE_EXHAUSTED",
                }},
            )

        transport = httpx.MockTransport(provider)
        with (
            mock.patch.dict(os.environ, {
                "GEMINI_API_KEY": "test-key",
                "GEMINI_MODEL": "test-model",
            }),
            mock.patch.object(
                job_draft.httpx,
                "AsyncClient",
                side_effect=lambda timeout: original_client(timeout=timeout, transport=transport),
            ),
        ):
            with self.assertRaisesRegex(
                JobDraftError,
                r"HTTP 429: Quota exceeded for key \[redacted\]; retry later",
            ) as raised:
                asyncio.run(job_draft.draft_quotation(
                    job_description="Bedrooms and bathrooms",
                    quotation_goal="A detailed cleaning proposal",
                    target_total_ngn=800000,
                    profile=BusinessProfile(),
                    client=ClientInfo(),
                    master_reference="Bedroom cleaning reference",
                ))

        self.assertNotIn("test-key", str(raised.exception))
