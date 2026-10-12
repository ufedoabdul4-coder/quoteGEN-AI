"""AI understanding, with the deterministic parser as a guaranteed floor.

The model may only *label* what the provider already wrote — it chooses each
block's type and heading level and nothing else. It never supplies the words:
every block's text is the provider's own, in the provider's own case, taken from
:mod:`services.understanding`. If the model returns text that differs from the
source it is discarded, so a "helpful" rewrite can never leak into the PDF.

This keeps the pipeline useful with no API key at all, and makes the key a
quality upgrade rather than a hard dependency.
"""

from __future__ import annotations

import json
import logging
import os
import re

import httpx

from models import (
    SEMANTIC_TYPES,
    BusinessProfile,
    ClientInfo,
    Understanding,
)
from services import understanding as deterministic

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-3.8-flash"
#: Tried in order after the configured model. Providers retire and rate-limit
#: specific models, so the pipeline keeps a short ladder of known-good ones
#: rather than failing the whole request on one 404/503.
FALLBACK_MODELS = (
    "gemini-3.8-flash",
    "gemini-flash-latest",
    "gemini-3.7-flash",
    "gemini-flash-lite-latest",
)
_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

#: Types whose wording/figures are proven deterministically and must never be
#: relabelled away from pricing, or into it, by the model.
_LOCKED_TYPES = {"table_header", "table_row", "subtotal", "grand_total", "cost_amount"}

_HEADING_TYPES = {"heading", "major_section_heading", "subsection_heading", "document_title"}

SYSTEM_PROMPT = """You are quoteGEN's document classifier for quotations and proposals.

You receive a numbered list of blocks that were already extracted from the
provider's text, verbatim. YOU MUST NOT REWRITE, TRANSLATE, SHORTEN OR REORDER
ANY WORDS. Your only job is to label each block.

For every block, choose:
  * "type": exactly one of the allowed types below.
  * "level": for a heading, 1 (major section), 2 (subsection) or 3 (sub-subsection);
    otherwise 1.

Allowed types:
  document_title, subtitle, provider_name, client_name, client_address,
  service_address, quotation_number, quotation_date, validity_period, introduction,
  heading, major_section_heading, subsection_heading, paragraph, bullet_list,
  numbered_list, scope_item, table_header, table_row, cost_amount, subtotal,
  grand_total, amount_in_words, equipment_item, material_item, safety_item,
  duration, term, signature, client_acceptance, contact_information

Rules:
1. Never output text. Output only an index, a type and a level for each block.
2. Keep every block's index exactly as given. Do not add, drop or merge indices.
3. Blocks already labelled table_header, table_row, subtotal, grand_total or
   cost_amount are priced rows: leave their type unchanged.
4. A line like "SUBMITTED BY", "PREPARED BY" or "CLIENT ACCEPTANCE" is a heading,
   not a person or an address. Label it "heading" with the level its Markdown
   marker implies (# = 1, ## = 2, ### = 3).
5. "Amount in Words: ..." is amount_in_words. A line that is only a total is
   grand_total. A person/business name under a heading may be provider_name.

Respond with JSON only:
{"blocks": [{"i": 0, "type": "...", "level": 1}]}
"""


async def understand(
    text: str,
    *,
    kind: str = "auto",
    profile: BusinessProfile | None = None,
    client: ClientInfo | None = None,
    model: str | None = None,
) -> tuple[Understanding, bool, str, list[str]]:
    """Return (understanding, used_ai, model_name, notes)."""
    text = deterministic.repair_mojibake(text or "")
    base = deterministic.understand(text, kind=kind, profile=profile, client=client)
    notes = list(base.notes)

    missing = deterministic.verify_completeness(text, base)
    if missing:
        base.missing = list(base.missing) + [f"unplaced source line: {line}" for line in missing]
        notes.append(
            f"{len(missing)} source line(s) did not reach a block and were reported, not dropped."
        )

    key = os.getenv("GEMINI_API_KEY", "")
    if not key or not (text or "").strip():
        return base, False, "", notes

    preferred = model or os.getenv("GEMINI_MODEL") or DEFAULT_MODEL
    candidates = [preferred] + [m for m in FALLBACK_MODELS if m != preferred]
    for chosen in candidates:
        try:
            data = await _ask_gemini(base, key, chosen, profile, client)
        except Exception as exc:  # noqa: BLE001
            logger.warning("understanding model %s failed: %s", chosen, exc)
            notes.append(f"{chosen}: {exc}")
            continue
        applied = _apply_labels(base, data)
        if applied:
            logger.info("understanding labelled by model %s (%d blocks)", chosen, applied)
            notes.append(f"understood by {chosen}")
            return base, True, chosen, notes
        logger.warning("model %s returned nothing usable; trying the next model", chosen)
        notes.append(f"{chosen}: no usable labels")

    notes.append("AI understanding was unavailable; used the offline parser.")
    return base, False, "", notes


async def _ask_gemini(base: Understanding, key: str, model: str,
                      profile, client) -> dict | None:
    payload = {
        "contents": [{"parts": [
            {"text": SYSTEM_PROMPT},
            {"text": _user_prompt(base, profile, client)},
        ]}],
        "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"},
    }
    url = _ENDPOINT.format(model=model)
    async with httpx.AsyncClient(timeout=40.0) as http:
        response = await http.post(url, headers={"x-goog-api-key": key}, json=payload)
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}")
    data = response.json()
    try:
        raw = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("response had no candidate text") from exc
    parsed = _load_json(raw)
    if not isinstance(parsed, dict):
        raise ValueError("response was not valid JSON")
    return parsed


def _user_prompt(base: Understanding, profile, client) -> str:
    lines = []
    if profile and profile.name:
        lines.append(f"Provider (the business issuing the quote): {profile.name}")
    if client and client.name:
        lines.append(f"Known client name: {client.name}")
    header = "\n".join(lines)
    listing = "\n".join(
        f'{index}: [{block.type}] {_describe(block)}'
        for index, block in enumerate(base.blocks)
    )
    return (
        f"{header}\n\nBlocks to label (verbatim; do not edit):\n{listing}"
    ).strip()


def _describe(block) -> str:
    if block.items:
        return " | ".join(block.items)
    return block.text or ""


def _load_json(raw: str) -> dict | None:
    cleaned = re.sub(r"^```(?:json)?|```$", "", (raw or "").strip(), flags=re.M).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.S)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


def _apply_labels(base: Understanding, data: dict | None) -> int:
    """Apply the model's type/level labels to the source blocks; keep the words.

    Returns how many blocks were actually relabelled. Text is never taken from
    the model, and priced rows are locked so a total can never be moved or lost.
    """
    if not isinstance(data, dict):
        return 0
    applied = 0
    title_taken = False
    seen_title = any(block.type == "document_title" for block in base.blocks)
    for item in data.get("blocks") or []:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("i"))
        except (TypeError, ValueError):
            continue
        if index < 0 or index >= len(base.blocks):
            continue
        block = base.blocks[index]
        new_type = str(item.get("type", "")).strip()
        if new_type not in SEMANTIC_TYPES:
            continue
        if block.type in _LOCKED_TYPES or new_type in _LOCKED_TYPES:
            continue
        if new_type == "document_title":
            if seen_title or title_taken:
                continue
            title_taken = True
            seen_title = True
        if new_type != block.type:
            block.type = new_type
            applied += 1
        if new_type in _HEADING_TYPES:
            try:
                level = int(item.get("level", block.level) or block.level)
            except (TypeError, ValueError):
                level = block.level
            level = min(max(level, 1), 3)
            if level != block.level:
                block.level = level
                applied += 1
    if applied:
        deterministic.refresh(base, None, None)
    return applied
