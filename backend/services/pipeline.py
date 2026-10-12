"""Orchestrate understanding → layout → PDF → validation for one document."""

from __future__ import annotations

import base64
import re

from models import (
    BusinessProfile,
    ClientInfo,
    Understanding,
    ValidationFinding,
    ValidationReport,
)
from services.designs import Design, PaintContext, get_design
from services.fonts import FontRegistry
from services.mapping import expand_lists, to_flow_blocks
from services import understanding as understanding_mod
from services.render import RenderResult, render_pdf_document, render_previews
from services.validation import validate

_DATA_URL = re.compile(r"^data:image/[a-zA-Z0-9.+-]+;base64,", re.I)


def decode_logo(data_url: str | None) -> bytes | None:
    if not data_url:
        return None
    try:
        payload = _DATA_URL.sub("", data_url.strip())
        return base64.b64decode(payload)
    except Exception:
        return None


def profile_contact_lines(profile: BusinessProfile) -> list[str]:
    return [part for part in [profile.phone, profile.email, profile.website, profile.address] if part]


def build(design_id: str, understanding: Understanding, profile: BusinessProfile,
          client: ClientInfo, title: str = "", *, reference_design: Design | None = None,
          make_previews: bool = True) -> tuple[RenderResult, ValidationReport, list[bytes]]:
    registry = FontRegistry()
    design = reference_design or get_design(design_id)
    understanding = understanding_mod.refresh(understanding, profile, client)
    flow_blocks = expand_lists(to_flow_blocks(understanding, profile, client))

    ctx = PaintContext(
        profile_name=profile.name or "Your company",
        profile_contact=profile_contact_lines(profile),
        logo_bytes=decode_logo(profile.logo_data_url),
        doc_title=(title or understanding.title or "Quotation").upper(),
    )
    result = render_pdf_document(design, flow_blocks, registry, ctx)
    report = validate(understanding, result.pdf_bytes, flow_block_count=len(flow_blocks))
    for warning in result.warnings:
        report.findings.append(ValidationFinding(level="warning", code="layout", message=warning))
    previews = render_previews(result.pdf_bytes) if make_previews else []
    return result, report, previews
