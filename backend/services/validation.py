"""Output validation: inspect the rendered PDF, not the intention behind it.

Everything upstream may be correct and the PDF still come out wrong — a glyph
missing from the font, a line pushed past the margin, Markdown syntax that
survived into the print, a total that does not equal the sum of its rows. This
module reads the finished file back and reports what it finds, so a defect is
surfaced as a warning instead of shipping silently.
"""

from __future__ import annotations

import re

import pymupdf

from models import ValidationFinding, ValidationReport, Understanding

_MARKDOWN_TOKENS = [
    (re.compile(r"\*\*"), "bold markers (**)"),
    (re.compile(r"(?m)^#{1,6}\s"), "heading hashes (#)"),
    (re.compile(r"`{1,3}"), "code backticks (`)"),
    (re.compile(r"\]\("), "markdown links"),
    (re.compile(r"(?m)^\s*[-+*]\s+\S"), "hyphen bullets"),
]


def validate(understanding: Understanding, pdf_bytes: bytes, *,
             flow_block_count: int = 0) -> ValidationReport:
    report = ValidationReport()
    report.blocks_built = len(understanding.blocks)
    report.blocks_mapped = flow_block_count

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        report.page_count = doc.page_count
        all_text_parts: list[str] = []
        for page_index in range(doc.page_count):
            page = doc.load_page(page_index)
            text = page.get_text("text")
            all_text_parts.append(text)
            _check_overflow(page, page_index + 1, report)
        all_text = "\n".join(all_text_parts)
    finally:
        doc.close()

    _check_markdown(all_text, report)
    _check_financials(understanding, report)
    _check_missing(understanding, report)

    report.ok = not any(f.level == "error" for f in report.findings)
    return report


def _check_overflow(page: "pymupdf.Page", page_number: int, report: ValidationReport) -> None:
    rect = page.rect
    margin = 1.5
    offenders: list[str] = []
    for item in page.get_text("words"):
        x0, y0, x1, y1 = item[0], item[1], item[2], item[3]
        if x0 < rect.x0 - margin or y0 < rect.y0 - margin or x1 > rect.x1 + margin or y1 > rect.y1 + margin:
            offenders.append(str(item[4]))
    if offenders:
        report.findings.append(ValidationFinding(
            level="error", code="text_overflow",
            message=f"{len(offenders)} word(s) fall outside the page on page {page_number}",
            detail=offenders[:8],
        ))


def _check_markdown(text: str, report: ValidationReport) -> None:
    for pattern, label in _MARKDOWN_TOKENS:
        hits = re.findall(pattern, text)
        if hits:
            report.literal_markdown.append(f"{label}: {len(hits)} occurrence(s)")
    if report.literal_markdown:
        report.findings.append(ValidationFinding(
            level="warning", code="markdown_leak",
            message="Markdown syntax reached the printed page.",
            detail=report.literal_markdown,
        ))


def _check_financials(understanding: Understanding, report: ValidationReport) -> None:
    financials = understanding.financials
    report.computed_total = financials.rows_total
    report.stated_total = financials.stated_total
    report.pricing_rows = sum(
        1 for b in understanding.blocks if b.type in ("table_row", "cost_amount")
    )
    if financials.rows_total is not None and financials.stated_total is not None and not financials.consistent:
        report.findings.append(ValidationFinding(
            level="error", code="total_mismatch",
            message=(
                f"The priced lines sum to {financials.rows_total:,.2f} but the quoted total is "
                f"{financials.stated_total:,.2f}."
            ),
        ))
    if financials.rows_total is None and report.pricing_rows == 0:
        report.findings.append(ValidationFinding(
            level="warning", code="no_pricing",
            message="No priced rows were found in this document.",
        ))


def _check_missing(understanding: Understanding, report: ValidationReport) -> None:
    report.missing_blocks = list(understanding.missing)
    if understanding.missing:
        report.findings.append(ValidationFinding(
            level="info", code="missing_information",
            message="Some information was not found in the input.",
            detail=list(understanding.missing),
        ))
