"""API smoke tests using the in-process test client (no server, no network)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pymupdf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

SAMPLE = (
    "Quotation for Acme Ltd\n"
    "Quote No: Q-100\n"
    "Provide deep cleaning, 2,000,000 total\n"
    "Grand Total: 2,000,000\n"
)


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)
        cls.storage_temp = tempfile.TemporaryDirectory(prefix="quotegen-api-")
        cls.addClassCleanup(cls.storage_temp.cleanup)
        storage = Path(cls.storage_temp.name)
        cls.storage_patch = mock.patch.multiple(
            main.store,
            STORAGE=storage,
            DOCUMENTS=storage / "documents",
            PREVIEWS=storage / "previews",
            REFERENCES=storage / "references",
            PROFILE_FILE=storage / "profile.json",
            SETTINGS_FILE=storage / "settings.json",
        )
        cls.storage_patch.start()
        cls.addClassCleanup(cls.storage_patch.stop)

    def test_health(self):
        self.assertEqual(self.client.get("/health").json()["status"], "ok")

    def test_authentication_errors_include_cors_headers(self):
        allowed_origin = (
            "*"
            if "*" in main._cors_origins
            else main._cors_origins[0]
        )
        origin = (
            "https://quotegen1-ai.netlify.app"
            if allowed_origin == "*"
            else allowed_origin
        )
        with (
            mock.patch.object(main.supabase_client, "is_enabled", return_value=True),
            mock.patch.object(main.supabase_client, "verify_token", return_value=None),
        ):
            response = self.client.get("/templates/active", headers={"Origin": origin})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers.get("access-control-allow-origin"), allowed_origin)

    def test_billing_status_in_local_mode(self):
        response = self.client.get("/billing/status")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["free_limit"], 10)
        self.assertEqual(response.json()["free_daily_limit"], 3)
        self.assertEqual(response.json()["free_quota_window_days"], 30)
        self.assertEqual(response.json()["pdfs_generated_today"], 0)
        self.assertFalse(response.json()["billing_enabled"])

    def test_billing_status_reports_daily_and_rolling_usage(self):
        class Query:
            def __init__(self, result):
                self.result = result

            def select(self, *_args, **_kwargs):
                return self

            def eq(self, *_args, **_kwargs):
                return self

            def gte(self, *_args, **_kwargs):
                return self

            def limit(self, *_args, **_kwargs):
                return self

            def execute(self):
                return self.result

        account_query = Query(SimpleNamespace(data=[{"paid_until": None}]))
        usage_results = iter([
            SimpleNamespace(count=4),
            SimpleNamespace(count=2),
            SimpleNamespace(count=7),
        ])
        usage_query = Query(None)
        usage_query.execute = lambda: next(usage_results)
        client = mock.Mock()
        client.table.side_effect = lambda name: (
            account_query if name == "billing_accounts" else usage_query
        )

        with (
            mock.patch.object(main.billing, "_client", return_value=client),
            mock.patch.object(main.billing, "require_current_user", return_value="test-user"),
        ):
            status = main.billing.get_status()

        self.assertEqual(status["pdfs_generated_today"], 4)
        self.assertEqual(status["free_used_today"], 2)
        self.assertEqual(status["free_used"], 7)
        self.assertEqual(status["free_remaining"], 3)
        self.assertEqual(status["free_daily_remaining"], 1)

    def test_generation_blocks_when_quota_rpc_denies(self):
        understanding = self.client.post(
            "/understand", json={"text": SAMPLE}
        ).json()["understanding"]
        with (
            mock.patch.object(main.supabase_client, "is_enabled", return_value=True),
            mock.patch.object(main.supabase_client, "verify_token", return_value="test-user"),
            mock.patch.object(main.billing, "consume_quotation", return_value=False),
        ):
            response = self.client.post(
                "/generate",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "title": "Quota test quotation",
                    "design_id": "clean_corporate",
                    "understanding": understanding,
                    "profile": {"name": "Bright Works Ltd"},
                    "client": {"name": "Acme Ltd"},
                },
            )
        self.assertEqual(response.status_code, 402)
        self.assertEqual(response.json()["detail"]["code"], "FREE_QUOTATIONS_EXHAUSTED")

    def test_designs_listed(self):
        designs = self.client.get("/designs").json()["designs"]
        self.assertGreaterEqual(len(designs), 4)

    def test_understand(self):
        response = self.client.post("/understand", json={"text": SAMPLE, "kind": "describe"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("understanding", body)
        self.assertTrue(body["understanding"]["blocks"])

    def test_generate_and_fetch(self):
        understanding = self.client.post("/understand", json={"text": SAMPLE}).json()["understanding"]
        response = self.client.post("/generate", json={
            "title": "Cleaning quotation",
            "design_id": "clean_corporate",
            "understanding": understanding,
            "profile": {"name": "Bright Works Ltd"},
            "client": {"name": "Acme Ltd"},
        })
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertGreaterEqual(body["page_count"], 1)

        doc_id = body["document_id"]
        pdf = self.client.get(f"/documents/{doc_id}/pdf")
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF"))

        listing = self.client.get("/documents").json()["documents"]
        self.assertTrue(any(item["id"] == doc_id for item in listing))

        self.assertTrue(self.client.delete(f"/documents/{doc_id}").json()["deleted"])

    def test_failed_full_quotation_understanding_returns_clear_error(self):
        response = self.client.post("/preview", json={
            "understanding": {
                "failed": True,
                "failure_reason": "No usable quotation content was found.",
            },
        })
        self.assertEqual(response.status_code, 422)
        self.assertIn("Full quotation understanding failed", response.json()["detail"])

    def test_reference_upload_if_master_present(self):
        masters = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "storage", "masters")
        candidate = os.path.join(masters, "emerald_contractor_master.pdf")
        if not os.path.exists(candidate):
            self.skipTest("no master PDF available")
        with open(candidate, "rb") as handle:
            response = self.client.post(
                "/references/upload",
                files={"file": ("master.pdf", handle.read(), "application/pdf")},
            )
        self.assertEqual(response.status_code, 200, response.text)
        meta = response.json()
        self.assertIn("design", meta)
        self.assertTrue(meta["design"]["font_body"])
        self.assertGreater(meta["size_bytes"], 0)
        self.assertGreaterEqual(meta["page_count"], 1)
        self.assertEqual(meta["status"], "ready")
        self.assertTrue(self.client.delete(f"/references/{meta['id']}").json()["deleted"])

    def test_template_lifecycle_and_active_rendering(self):
        previous_active = self.client.get("/templates/active").json()["template"]
        template_id = None
        document_id = None

        def cleanup():
            if document_id:
                self.client.delete(f"/documents/{document_id}")
            if template_id:
                self.client.delete(f"/templates/{template_id}")
            if previous_active and self.client.get(
                f"/templates/{previous_active['id']}"
            ).status_code == 200:
                self.client.post("/templates/active", json={
                    "template_id": previous_active["id"],
                })

        self.addCleanup(cleanup)
        masters = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "storage", "masters")
        candidate = os.path.join(masters, "emerald_contractor_master.pdf")
        if not os.path.exists(candidate):
            self.skipTest("no master PDF available")
        with open(candidate, "rb") as handle:
            source = handle.read()
        response = self.client.post(
            "/templates/upload",
            files={"file": ("master.pdf", source, "application/pdf")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        template = response.json()
        template_id = template["id"]
        self.assertEqual(template["status"], "ready")
        self.assertEqual(template["size_bytes"], len(source))
        self.assertGreaterEqual(template["page_count"], 1)
        self.assertEqual(main.store.get_active_template_id(), template_id)
        self.assertEqual(
            self.client.get("/templates/active").json()["template"]["id"], template_id,
        )

        uploaded_again = self.client.post(
            "/templates/upload",
            files={"file": ("replacement.pdf", source, "application/pdf")},
        )
        self.assertEqual(uploaded_again.status_code, 200, uploaded_again.text)
        self.assertEqual(uploaded_again.json()["id"], template_id)
        self.assertEqual(len(self.client.get("/templates").json()["templates"]), 1)

        listing = self.client.get("/templates").json()["templates"]
        self.assertTrue(any(item["id"] == template_id for item in listing))
        self.assertEqual(self.client.get(f"/templates/{template_id}").status_code, 200)
        self.assertTrue(self.client.get(f"/templates/{template_id}/pdf").content.startswith(b"%PDF"))

        renamed = self.client.patch(
            f"/templates/{template_id}", json={"name": "Renamed master"}
        )
        self.assertEqual(renamed.status_code, 200, renamed.text)
        self.assertEqual(renamed.json()["name"], "Renamed master")
        self.assertFalse(any(item["id"] == template_id
                             for item in self.client.get("/references").json()["references"]))

        replaced = self.client.put(
            f"/templates/{template_id}/replace",
            files={"file": ("replacement.pdf", source, "application/pdf")},
        )
        self.assertEqual(replaced.status_code, 200, replaced.text)
        self.assertEqual(replaced.json()["id"], template_id)
        self.assertEqual(replaced.json()["source_filename"], "replacement.pdf")

        active = self.client.post("/templates/active", json={"template_id": template_id})
        self.assertEqual(active.status_code, 200, active.text)
        self.assertEqual(self.client.get("/templates/active").json()["template"]["id"], template_id)

        understanding = self.client.post("/understand", json={"text": SAMPLE}).json()["understanding"]
        generated = self.client.post("/generate", json={
            "title": "Template quotation",
            "raw_input": SAMPLE,
            "understanding": understanding,
            "profile": {"name": "Bright Works Ltd"},
            "client": {"name": "Acme Ltd"},
        })
        self.assertEqual(generated.status_code, 200, generated.text)
        document_id = generated.json()["document_id"]
        saved = self.client.get(f"/documents/{document_id}").json()
        self.assertEqual(saved["reference_id"], template_id)
        self.assertEqual(saved["raw_input"], SAMPLE)
        output_pdf = pymupdf.open(
            stream=self.client.get(f"/documents/{document_id}/pdf").content,
            filetype="pdf",
        )
        source_pdf = pymupdf.open(stream=source, filetype="pdf")
        self.assertAlmostEqual(output_pdf[0].rect.width, source_pdf[0].rect.width, places=1)
        self.assertAlmostEqual(output_pdf[0].rect.height, source_pdf[0].rect.height, places=1)
        self.assertIn("Provide", output_pdf[0].get_text())
        self.assertNotIn("ITEM DESCRIPTION & SPECIFICATION", output_pdf[0].get_text())
        content_area = main.reference.analyze_reference(source).content_area
        source_page = source_pdf[0]
        if main.reference._has_full_page_image(source_page):
            for page in output_pdf:
                for block in page.get_text("dict")["blocks"]:
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            if not (span.get("text") or "").strip():
                                continue
                            rect = pymupdf.Rect(span["bbox"])
                            self.assertGreaterEqual(rect.x0, content_area.left - 1)
                            self.assertLessEqual(rect.x1, content_area.right + 1)
                            self.assertGreaterEqual(rect.y0, content_area.top - 1)
                            self.assertLessEqual(rect.y1, content_area.bottom + 1)
        output_pdf.close()
        source_pdf.close()

        cleared = self.client.delete("/templates/active")
        self.assertEqual(cleared.status_code, 200)
        self.assertIsNone(cleared.json()["template"])
        self.assertEqual(
            self.client.get("/templates/active").json()["template"]["id"], template_id,
        )
        self.assertTrue(self.client.delete(f"/templates/{template_id}").json()["deleted"])
        self.assertIsNone(self.client.get("/templates/active").json()["template"])


if __name__ == "__main__":
    unittest.main()
