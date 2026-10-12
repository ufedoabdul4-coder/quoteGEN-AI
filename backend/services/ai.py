"""AI understanding, with the deterministic parser as a guaranteed floor.

The model may only *reorder and label* what the provider already wrote. It can
never add a price, a client or a total that is not in the source text, and its
answer is discarded — silently falling back to :mod:`services.understanding` —
if it returns a type outside the shared vocabulary or produces nothing usable.

This keeps the pipeline useful with no API key at all, and makes the key a
quality upgrade rather than a hard dependency.
"""

from __future__ import annotations

import json
import os
import re

import httpx

from models import (
    SEMANTIC_TYPES,
    BusinessProfile,
    ClientInfo,
    SemanticBlock,
    Understanding,
)
from services import understanding as deterministic
from services.financials import reconcile

DEFAULT_MODEL = "gemini-flash-latest"
#: Tried in order after the configured model. Providers retire and rate-limit
#: specific models, so the pipeline keeps a short ladder of known-good ones
#: rather than failing the whole request on one 404/503.
FALLBACK_MODELS = (
    "gemini-flash-latest",
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-flash-lite-latest",
)
_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

SYSTEM_PROMPT = """You are quoteGEN's document-understanding engine for quotations and proposals.
You will receive the provider's raw notes, a pasted document, or transcribed speech.

Your job is to prepare a clear, professional quotation while preserving the
provider's meaning and every factual detail. Correct obvious spelling, grammar,
spacing, heading casing, broken lists and malformed tables. You may turn terse
notes into readable sentences only when the source clearly supports that wording.
Never invent, assume, add a service, promise, date, quantity, price, person or term.
Keep all source facts, especially names, addresses, references, quantities and
financial figures unchanged. Do not include analysis or commentary in the quote.

Allowed block types and when to use them:
  document_title, subtitle, provider_name, client_name, client_address,
  service_address, quotation_number, quotation_date, validity_period, introduction,
  major_section_heading, subsection_heading, paragraph, bullet_list, numbered_list,
  scope_item, table_header, table_row, cost_amount, subtotal, grand_total,
  amount_in_words, equipment_item, material_item, safety_item, duration, term,
  signature, client_acceptance, contact_information

Rules:
1. A number is money ONLY when the provider marked it as money (a currency symbol,
   or words like "total", "amount", "price", "rate", "cost", "fee").
2. Phone numbers, dates, quantities and reference numbers are NEVER money.
3. Keep the source reading order, but combine wrapped lines into one coherent
   paragraph. Do not make a separate block for each sentence or ordinary line.
4. Keep each heading, complete paragraph and complete list as one block. Put all
   members of a list in that block's "items". For tables put the header in one
   table_header block and each row in a table_row block, each "items" holding cells.
5. Use polished, natural business English; remove stray Markdown and repair
   fragments without changing their factual meaning.

Respond with JSON only:
{"title": "...", "blocks": [{"type": "...", "text": "...", "level": 1, "items": []}]}
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
    key = os.getenv("GEMINI_API_KEY", "")
    if not key or not (text or "").strip():
        return base, False, "", list(base.notes)

    preferred = model or os.getenv("GEMINI_MODEL") or DEFAULT_MODEL
    candidates = [preferred] + [m for m in FALLBACK_MODELS if m != preferred]
    errors: list[str] = []
    for chosen in candidates:
        try:
            refined = await _ask_gemini(text, key, chosen, profile, client)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{chosen}: {exc}")
            continue
        if refined is not None:
            refined = deterministic.refresh(refined, profile, client)
            return refined, True, chosen, list(refined.notes)

    notes = list(base.notes)
    notes.append("AI understanding was unavailable; used the offline parser.")
    return base, False, "", notes


async def _ask_gemini(text: str, key: str, model: str, profile, client) -> Understanding | None:
    payload = {
        "contents": [{"parts": [{"text": SYSTEM_PROMPT}, {"text": _user_prompt(text, profile, client)}]}],
        "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"},
    }
    url = _ENDPOINT.format(model=model)
    async with httpx.AsyncClient(timeout=40.0) as http:
        response = await http.post(url, headers={"x-goog-api-key": key}, json=payload)
    if response.status_code != 200:
        return None
    data = response.json()
    try:
        raw = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        return None
    return _build_understanding(_load_json(raw), kind="describe")


def _user_prompt(text: str, profile, client) -> str:
    lines = []
    if profile and profile.name:
        lines.append(f"Provider (the business issuing the quote): {profile.name}")
    if client and client.name:
        lines.append(f"Known client name: {client.name}")
    header = "\n".join(lines)
    return f"{header}\n\nProvider's raw text:\n\"\"\"\n{text}\n\"\"\"".strip()


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


def _build_understanding(data: dict | None, *, kind: str) -> Understanding | None:
    if not isinstance(data, dict):
        return None
    blocks: list[SemanticBlock] = []
    for order, item in enumerate(data.get("blocks") or []):
        if not isinstance(item, dict):
            continue
        block_type = str(item.get("type", "")).strip()
        if block_type not in SEMANTIC_TYPES:
            continue
        items = [str(x) for x in (item.get("items") or []) if str(x).strip()]
        blocks.append(SemanticBlock(
            type=block_type,
            text=str(item.get("text", "")).strip(),
            level=int(item.get("level", 1) or 1),
            items=items,
            order=order,
        ))
    if not blocks:
        return None

    summary, warnings = reconcile(blocks)
    title = str(data.get("title", "")).strip()
    if not title:
        title = next((b.text for b in blocks if b.type == "document_title"), "Quotation")
    understanding = Understanding(
        title=title,
        blocks=blocks,
        financials=summary,
        blocks_seen=len(blocks),
        source_kind=kind,
        notes=list(warnings),
    )
    return understanding
