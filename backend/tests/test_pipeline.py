"""End-to-end tests for the backend pipeline (no network, no Gemini key)."""

from __future__ import annotations

import os
import sys
import unittest

import pymupdf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import BusinessProfile, ClientInfo  # noqa: E402
from services.designs import Design, PaintContext  # noqa: E402
from services.flow import FlowBlock, TableSpec  # noqa: E402
from services.fonts import FontRegistry, wrap_text  # noqa: E402
from services import mapping, pipeline, reference, understanding  # noqa: E402
from services.render import render_pdf_document  # noqa: E402

SAMPLE = """# QUOTATION

Prepared for: Acme Facilities Ltd

Quotation No: Q-2026-0042
Date: 2026-02-01

## Scope of works

- Site survey and measurement
- Removal of existing fixtures
- Installation of new units

| Description | Amount |
|---|---|
| Supply and install unit A | 250,000 |
| Supply and install unit B | 150,000 |
| Subtotal | 400,000 |
| Grand Total | 400,000 |

Payment terms: 70% deposit on award, balance on completion.

Signature: ______________________
"""


class UnderstandingTests(unittest.TestCase):
    def setUp(self):
        self.profile = BusinessProfile(name="Bright Works Ltd", phone="+234 803 000 0000",
                                       email="hello@brightworks.ng")
        self.client = ClientInfo(name="Acme Facilities Ltd")
        self.result = understanding.understand(SAMPLE)

    def test_core_blocks_present(self):
        types = [b.type for b in self.result.blocks]
        self.assertIn("document_title", types)
        self.assertIn("table_row", types)
        self.assertIn("grand_total", types)
        self.assertIn("bullet_list", types)

    def test_amounts_are_money_not_phone_or_date(self):
        rows = [b for b in self.result.blocks if b.type == "table_row"]
        self.assertEqual([b.value for b in rows], [250000.0, 150000.0])

    def test_totals_reconcile(self):
        fin = self.result.financials
        self.assertEqual(fin.rows_total, 400000.0)
        self.assertEqual(self.result.financials.stated_total, 400000.0)
        self.assertTrue(self.result.financials.consistent)

    def test_no_markdown_survives_as_literal(self):
        texts = " ".join(b.text for b in self.result.blocks)
        self.assertNotIn("**", understanding._clean("**bold**"))

    def test_wrapped_prose_is_kept_as_one_paragraph(self):
        result = understanding.understand(
            "We appreciate the opportunity to provide this quotation.\n"
            "Our team will complete the work at the agreed location.\n"
            "All materials are included in the stated price."
        )
        paragraphs = [block for block in result.blocks if block.type == "paragraph"]
        self.assertEqual(len(paragraphs), 1)
        self.assertEqual(
            paragraphs[0].text,
            "We appreciate the opportunity to provide this quotation. "
            "Our team will complete the work at the agreed location. "
            "All materials are included in the stated price.",
        )

    def test_repeated_utf8_mojibake_is_repaired_before_layout(self):
        result = understanding.understand(
            "Professional Cleaning ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¢ "
            "Fumigation ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¢ Pest Control"
        )
        paragraphs = [block.text for block in result.blocks if block.type == "paragraph"]
        self.assertEqual(
            paragraphs,
            ["Professional Cleaning • Fumigation • Pest Control"],
        )

    def test_base14_fallback_renders_currency_symbols_as_codes(self):
        from services.fonts import FontFace

        face = FontFace(
            display="Helvetica",
            family="helvetica",
            bold=False,
            italic=False,
            base14="helv",
        )

        self.assertEqual(face.sanitize("₦25,000"), "NGN 25,000")
        self.assertGreater(face.text_length("₦25,000", 10), face.text_length("25,000", 10))

    def test_base14_fallback_transliterates_punctuation_and_symbols_without_question_marks(self):
        from services.fonts import FontFace

        face = FontFace(
            display="Helvetica",
            family="helvetica",
            bold=False,
            italic=False,
            base14="helv",
        )

        safe = face.sanitize("The client’s café — ready… ✓ 🧹")
        self.assertEqual(safe, "The client's café - ready... [check] [broom]")
        self.assertNotIn("?", safe)
        document = pymupdf.open()
        page = document.new_page()
        page.insert_text((40, 40), safe, fontname="helv", fontsize=11)
        pdf_bytes = document.tobytes()
        document.close()
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as rendered:
            extracted = rendered[0].get_text()
        self.assertIn(safe, extracted)
        self.assertNotIn("?", extracted)


class FidelityTests(unittest.TestCase):
    """Source words and case survive; headings and totals are never dropped."""

    SAMPLE = """# PROPOSAL FOR DEEP CLEANING

## SUBMITTED BY

# KAMIBRIX LIMITED

# 1. INTRODUCTION

We are pleased to submit this proposal.

## A. MAIN RESIDENTIAL BUILDING

### 1. Sitting Room and Toilet

* Wet cleaning of all surfaces

## Fumigation Treatment Includes:

* Cockroach control

| Description | Amount |
|---|---|
| Deep cleaning | 750,000 |
| GRAND TOTAL | 750,000 |

# GRAND TOTAL: \u20a6750,000

### Amount in Words: Seven Hundred and Fifty Thousand Naira Only.

# PREPARED BY

Name: ____________

# CLIENT ACCEPTANCE

Signature: ____________
"""

    def setUp(self):
        self.result = understanding.understand(self.SAMPLE)

    def test_title_and_headings_keep_exact_case(self):
        texts = [b.text for b in self.result.blocks]
        self.assertIn("PROPOSAL FOR DEEP CLEANING", texts)
        self.assertIn("SUBMITTED BY", texts)
        self.assertIn("1. INTRODUCTION", texts)
        self.assertIn("GRAND TOTAL: \u20a6750,000", texts)
        self.assertIn("Amount in Words: Seven Hundred and Fifty Thousand Naira Only.", texts)

    def test_headings_carry_their_level(self):
        headings = {(b.text, b.level) for b in self.result.blocks if b.type == "heading"}
        self.assertIn(("SUBMITTED BY", 2), headings)
        self.assertIn(("1. INTRODUCTION", 1), headings)
        self.assertIn(("A. MAIN RESIDENTIAL BUILDING", 2), headings)
        self.assertIn(("1. Sitting Room and Toilet", 3), headings)

    def test_separate_total_line_is_kept(self):
        totals = [b.value for b in self.result.blocks if b.type == "grand_total"]
        self.assertIn(750000.0, totals)

    def test_amount_in_words_keeps_its_label(self):
        words = [b.text for b in self.result.blocks if b.type == "amount_in_words"]
        self.assertTrue(any(t.startswith("Amount in Words:") for t in words))

    def test_no_invented_labels(self):
        blob = " ".join(b.text for b in self.result.blocks)
        self.assertNotIn("Prepared for:", blob)

    def test_every_source_line_reaches_a_block(self):
        self.assertEqual(understanding.verify_completeness(self.SAMPLE, self.result), [])

    def test_mapping_gives_signature_sections_a_group(self):
        flow = mapping.to_flow_blocks(self.result)
        grouped = {b.text for b in flow if b.group and b.text in ("PREPARED BY", "CLIENT ACCEPTANCE")}
        self.assertEqual(grouped, {"PREPARED BY", "CLIENT ACCEPTANCE"})

    def test_subheadings_map_to_subsubheading(self):
        flow = mapping.to_flow_blocks(self.result)
        kinds = {(b.type, b.text) for b in flow}
        self.assertIn(("subsubheading", "1. Sitting Room and Toilet"), kinds)


class MismatchTests(unittest.TestCase):
    def test_bad_total_is_flagged_not_corrected(self):
        text = SAMPLE.replace("| Grand Total | 400,000 |", "| Grand Total | 425,000 |")
        result = understanding.understand(text)
        self.assertFalse(result.financials.consistent)
        self.assertTrue(result.notes)

    def test_totals_never_overwritten(self):
        text = SAMPLE + "\nGrand Total: 999,999\n"
        result = understanding.understand(text)
        figures = [b.value for b in result.blocks if b.type == "grand_total"]
        self.assertIn(999999.0, figures)


class MappingTests(unittest.TestCase):
    def setUp(self):
        self.result = understanding.understand(SAMPLE)

    def test_table_rows_collapse_into_one_table(self):
        flow = mapping.to_flow_blocks(self.result)
        tables = [b for b in flow if b.type == "table"]
        self.assertEqual(len(tables), 1)
        self.assertEqual(len(tables[0].table.rows), 2)
        self.assertEqual(len(tables[0].table.totals), 2)

    def test_lists_expand(self):
        flow = mapping.expand_lists(mapping.to_flow_blocks(self.result))
        self.assertTrue(any(b.type == "list_item" for b in flow))


class PipelineTests(unittest.TestCase):
    def test_long_word_after_regular_word_wraps_inside_column(self):
        face = FontRegistry().resolve("Arial")
        lines = wrap_text("AMOUNT " + "X" * 80, face, 12, 90)
        self.assertGreater(len(lines), 2)
        self.assertEqual("".join(lines[1:]), "X" * 80)
        self.assertTrue(all(face.text_length(line, 12) <= 90 for line in lines))

    def test_flattened_master_redacts_old_text_from_image_and_keeps_color_artwork(self):
        source = pymupdf.open()
        page = source.new_page(width=320, height=420)
        page.draw_rect(pymupdf.Rect(0, 0, 320, 90), color=None, fill=(0.05, 0.2, 0.7))
        page.draw_rect(pymupdf.Rect(25, 260, 295, 264), color=None, fill=(0.0, 0.5, 0.2))
        page.draw_rect(pymupdf.Rect(30, 320, 290, 420), color=None, fill=(0.0, 0.5, 0.2))
        page.insert_text((42, 345), "OUR SERVICES", fontsize=12, color=(1, 1, 1))
        flattened = page.get_pixmap(alpha=False).tobytes("png")
        source.close()

        master = pymupdf.open()
        page = master.new_page(width=320, height=420)
        page.insert_image(page.rect, stream=flattened)
        page.insert_text((28, 160), "OLD QUOTATION BODY", fontsize=18, color=(0, 0, 0))
        page.insert_text((28, 200), "OLD SECOND LINE", fontsize=18, color=(0, 0, 0))
        page.draw_rect(pymupdf.Rect(35, 210, 285, 245), color=(0, 0, 0), width=0.6)
        page.draw_rect(pymupdf.Rect(25, 230, 295, 231), color=(0, 0, 0), width=0.5)
        page.draw_rect(pymupdf.Rect(25, 230, 26, 255), color=(0, 0, 0), width=0.5)
        page.draw_line(pymupdf.Point(25, 256), pymupdf.Point(295, 256), color=(0, 0, 0), width=0.5)
        page.draw_line(pymupdf.Point(296, 230), pymupdf.Point(296, 255), color=(0, 0, 0), width=0.5)
        source_image_xref = page.get_images(full=True)[0][0]
        source_image = master.extract_image(source_image_xref)["image"]
        master_bytes = master.tobytes()
        master.close()

        inferred_design = reference.analyze_reference(master_bytes)
        self.assertGreater(inferred_design.content_area.top, 130)
        self.assertLess(inferred_design.content_area.bottom, 260)

        cleaned_bytes = reference.prepare_template_background(
            master_bytes,
            content_top=inferred_design.content_area.top,
            content_bottom=inferred_design.content_area.bottom,
        )
        cleaned = pymupdf.open(stream=cleaned_bytes, filetype="pdf")
        cleaned_page = cleaned[0]
        self.assertNotIn("OLD QUOTATION BODY", cleaned_page.get_text())
        self.assertNotIn("OLD SECOND LINE", cleaned_page.get_text())
        cleaned_images = cleaned_page.get_images(full=True)
        self.assertTrue(cleaned_images)
        self.assertTrue(any(
            cleaned.extract_image(image[0])["image"] == source_image
            for image in cleaned_images
        ))
        original = pymupdf.open(stream=master_bytes, filetype="pdf")
        footer_pixel = original[0].get_pixmap(alpha=False).pixel(80, 340)
        self.assertEqual(cleaned_page.get_pixmap(alpha=False).pixel(80, 340), footer_pixel)
        original.close()
        content_area = pymupdf.Rect(
            0, inferred_design.content_area.top, 320, inferred_design.content_area.bottom,
        )
        inherited_dark_drawings = [
            drawing for drawing in cleaned_page.get_drawings()
            if drawing["rect"].intersects(content_area)
            and any(
                color is not None and max(color) < 0.1
                for color in (drawing.get("fill"), drawing.get("color"))
            )
        ]
        self.assertEqual(inherited_dark_drawings, [])

        pix = cleaned_page.get_pixmap(alpha=False)
        red, green, blue = pix.pixel(12, 12)[:3]
        self.assertGreater(blue, red * 2)
        dark_pixels_in_cleared_line = 0
        for y in range(140, 170):
            for x in range(20, 290):
                r, g, b = pix.pixel(x, y)[:3]
                if max(r, g, b) < 100:
                    dark_pixels_in_cleared_line += 1
        self.assertEqual(dark_pixels_in_cleared_line, 0)
        dark_pixels_on_removed_grid = sum(
            1
            for y in range(228, 234)
            for x in range(20, 300)
            if max(pix.pixel(x, y)[:3]) < 100
        )
        self.assertEqual(dark_pixels_on_removed_grid, 0)
        cleaned.close()

    def test_builds_pdf_without_errors(self):
        result = understanding.understand(SAMPLE)
        profile = BusinessProfile(name="Bright Works Ltd", phone="+234 803 000 0000",
                                  email="hello@brightworks.ng", website="brightworks.ng")
        render, report, previews = pipeline.build(
            "premium_business", result, profile, ClientInfo(name="Acme Facilities Ltd"),
            title="Quotation", make_previews=True)
        self.assertGreaterEqual(render.page_count, 1)
        self.assertTrue(report.ok, msg=[f.message for f in report.findings if f.level == "error"])
        self.assertEqual(report.literal_markdown, [])
        self.assertEqual(len(previews), render.page_count)

    def test_all_designs_render(self):
        result = understanding.understand(SAMPLE)
        profile = BusinessProfile(name="Bright Works Ltd")
        for design in ("clean_corporate", "premium_business", "formal_proposal", "branded_service"):
            with self.subTest(design=design):
                _, report, _ = pipeline.build(design, result, profile, ClientInfo(), make_previews=False)
                self.assertTrue(report.ok, msg=design)

    def test_master_continuation_artwork_survives_content_reflow(self):
        master = pymupdf.open()
        first = master.new_page(width=612, height=792)
        first.insert_text((40, 32), "FIRST_MASTER_SHEET")
        continuation = master.new_page(width=612, height=792)
        continuation.insert_text((40, 32), "CONTINUATION_MASTER_SHEET")
        master_bytes = master.tobytes()
        master.close()

        design = Design(
            id="uploaded_master",
            name="Uploaded master",
            description="",
            kind="reference",
            background_pdf=master_bytes,
            margin_left=50,
            margin_right=50,
            margin_top=65,
            margin_bottom=60,
        )
        text = "Beginning of quotation. " + "quotation details " * 5000 + " FINAL_CONTENT_MARKER"
        rendered = render_pdf_document(
            design,
            [FlowBlock(type="paragraph", text=text)],
            FontRegistry(),
            PaintContext(),
        )

        self.assertGreater(rendered.page_count, 2)
        output = pymupdf.open(stream=rendered.pdf_bytes, filetype="pdf")
        for page in output:
            self.assertIn("FIRST_MASTER_SHEET", page.get_text())
            self.assertNotIn("CONTINUATION_MASTER_SHEET", page.get_text())
        self.assertIn("FINAL_CONTENT_MARKER", output[-1].get_text())
        output.close()


class ReferenceStyleTests(unittest.TestCase):
    def test_reference_font_metrics_include_all_pages_and_preserve_weights(self):
        master = pymupdf.open()
        first = master.new_page(width=612, height=792)
        title = "CENTRED MASTER TITLE"
        title_width = pymupdf.get_text_length(title, fontname="Times-Bold", fontsize=12)
        first.insert_text(((612 - title_width) / 2, 225), title, fontname="Times-Bold", fontsize=12)
        first.insert_text((72, 250), "Regular first-page body", fontname="Times-Roman", fontsize=12)
        second = master.new_page(width=612, height=792)
        second.insert_text((72, 220), "Regular continuation body", fontname="Times-Roman", fontsize=12)
        second.insert_text((72, 250), "Bold continuation heading", fontname="Times-Bold", fontsize=12)
        master_bytes = master.tobytes()
        master.close()

        design = reference.analyze_reference(master_bytes)
        styles = design.styles(FontRegistry())
        self.assertEqual(design.body_size, 12)
        self.assertIsNone(design.heading_size)
        self.assertIsNone(design.title_size)
        self.assertEqual(design.title_align, "center")
        self.assertEqual(design.font_body, "Times New Roman")
        self.assertEqual(design.font_heading, "Times New Roman")
        self.assertTrue(styles.title.bold)
        self.assertTrue(styles.heading.bold)
        self.assertFalse(styles.body.bold)
        self.assertEqual(styles.title.size, 17.4)
        self.assertAlmostEqual(styles.heading.size, 14.6, places=2)
        self.assertEqual(styles.subheading.size, 13.0)
        self.assertEqual(styles.subsubheading.size, 13.0)
        self.assertEqual(styles.body.size, 12)

    def test_reference_tables_render_as_unfilled_bordered_grids(self):
        master = pymupdf.open()
        master.new_page(width=612, height=792)
        background_pdf = master.tobytes()
        master.close()
        design = Design(
            id="uploaded_master",
            name="Uploaded master",
            description="",
            kind="reference",
            background_pdf=background_pdf,
            font_body="Times New Roman",
            font_heading="Times New Roman",
            body_size=12,
            title_size=12,
            heading_size=12,
            table_header_size=12,
        )
        table = FlowBlock(
            type="table",
            table=TableSpec(
                headers=["Description", "Amount"],
                rows=[["Cleaning", "500,000"]],
                totals=[["GRAND TOTAL", "500,000"]],
            ),
        )
        result = render_pdf_document(
            design, [table], FontRegistry(), PaintContext(),
        )
        output = pymupdf.open(stream=result.pdf_bytes, filetype="pdf")
        page = output[0]
        drawings = page.get_drawings()
        self.assertGreaterEqual(len(drawings), 5)
        self.assertTrue(all(drawing["fill"] is None for drawing in drawings))
        intended_colors = [(0.0, 0.0, 0.0), (217 / 255, 212 / 255, 199 / 255)]
        for drawing in drawings:
            self.assertTrue(any(
                all(abs(actual - expected) < 0.01 for actual, expected in zip(drawing["color"], color))
                for color in intended_colors
            ))
        text = " ".join(page.get_text().split()).replace("\u00a0", " ")
        self.assertEqual(text.casefold().count("grand total"), 1)
        self.assertIn("500,000", text)
        output.close()


if __name__ == "__main__":
    unittest.main()
