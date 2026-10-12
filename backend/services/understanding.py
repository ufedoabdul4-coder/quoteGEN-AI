"""Content understanding: raw input in, ordered semantic blocks out.

This is the deterministic half of the AI pipeline. Given free text, pasted
Markdown or a structured note, it decides what each piece *is* — a heading, a
priced row, a client name, an amount in words — and returns the blocks in the
order the provider wrote them, together with the amounts it could prove.

Nothing is invented. A figure only becomes monetary when :mod:`services.classify`
can read it as money, and reconciliation in :mod:`services.financials` reports
any mismatch rather than hiding it. An AI provider may later refine the
classification, but this module always produces a valid document on its own.
"""

from __future__ import annotations

import re
import uuid

from models import BusinessProfile, ClientInfo, SemanticBlock, Understanding
from services import classify
from services.financials import reconcile

_INLINE_MD = re.compile(r"(\*\*|__|`{1,3})")
_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_BULLET = re.compile(r"^\s*([-*•·‣▪◦○])\s+(.*\S)\s*$")
_NUMBERED = re.compile(r"^\s*(?:\d{1,3}|[a-zA-Z])[.)]\s+(.*\S)\s*$")
_NUMBERED_HEADING = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2}){0,3})[.)]?\s+(.+?)\s*$")
_MD_TABLE_SEP = re.compile(r"^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$")
_MOJIBAKE_MARKERS = ("Ã", "Â", "â", "ƒ")

_SUBTOTAL_RE = re.compile(r"^(?:sub[\s-]?total|net\s+total)\b", re.I)
_GRAND_TOTAL_RE = re.compile(
    r"^(?:grand\s+total|total(?:\s+(?:due|payable|amount))?|amount\s+due|balance\s+due|"
    r"total\s+cost|contract\s+sum)\b",
    re.I,
)

_LABELS = {
    "prepared for": "client_name", "client": "client_name", "client name": "client_name",
    "bill to": "client_name", "billed to": "client_name", "to": "client_name",
    "customer": "client_name", "customer name": "client_name", "name of client": "client_name",
    "company": "provider_name", "provider": "provider_name", "from": "provider_name",
    "attention": "contact_information", "attn": "contact_information", "contact": "contact_information",
    "email": "contact_information", "e-mail": "contact_information", "phone": "contact_information",
    "tel": "contact_information", "telephone": "contact_information", "mobile": "contact_information",
    "address": "client_address", "client address": "client_address",
    "site": "service_address", "site address": "service_address", "service address": "service_address",
    "location": "service_address", "project": "introduction",
    "subject": "subtitle", "re": "subtitle", "title": "document_title",
    "quotation no": "quotation_number", "quotation number": "quotation_number",
    "quote no": "quotation_number", "quote number": "quotation_number",
    "quotation ref": "quotation_number", "ref": "quotation_number", "reference": "quotation_number",
    "quote ref": "quotation_number", "our ref": "quotation_number", "your ref": "quotation_number",
    "date": "quotation_date", "quotation date": "quotation_date", "quote date": "quotation_date",
    "date issued": "quotation_date",
    "validity": "validity_period", "valid until": "validity_period", "valid for": "validity_period",
    "expires": "validity_period", "expiry": "validity_period", "validity period": "validity_period",
    "duration": "duration", "timeline": "duration", "delivery": "duration", "lead time": "duration",
    "terms": "term", "payment terms": "term", "terms and conditions": "term", "terms of payment": "term",
    "warranty": "term", "note": "term", "notes": "term", "remarks": "term",
    "site address": "service_address",
}

_TITLE_WORDS = {"quotation", "quote", "proposal", "invoice", "estimate", "proforma", "pro forma"}


def _clean(text: str) -> str:
    return _INLINE_MD.sub("", text).strip()


def repair_mojibake(text: str) -> str:
    """Undo repeated UTF-8/Windows-1252 mis-decoding when it is unambiguous."""
    for _ in range(5):
        if not any(marker in text for marker in _MOJIBAKE_MARKERS):
            break
        try:
            candidate = text.encode("cp1252").decode("utf-8")
        except UnicodeError:
            break
        if sum(candidate.count(marker) for marker in _MOJIBAKE_MARKERS) >= sum(
            text.count(marker) for marker in _MOJIBAKE_MARKERS
        ):
            break
        text = candidate
    return text


def _is_all_caps(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 2 and all(c.isupper() for c in letters)


def _make(block_type: str, **kwargs) -> SemanticBlock:
    return SemanticBlock(type=block_type, id=uuid.uuid4().hex[:10], **kwargs)


def _looks_like_heading(text: str) -> int:
    """Return heading level (1 or 2) when the line reads like a heading, else 0."""
    stripped = text.strip().rstrip(":").strip()
    if not stripped or len(stripped) > 90:
        return 0
    if classify.is_money(stripped) or classify.is_phone(stripped) or classify.is_date(stripped):
        return 0
    if stripped.endswith("."):
        return 0
    words = stripped.split()
    if len(words) > 14:
        return 0
    if _is_all_caps(stripped):
        return 1
    match = _NUMBERED_HEADING.match(stripped)
    if match:
        numbering, rest = match.group(1), match.group(2)
        if rest and not rest.endswith(".") and (
            _is_all_caps(rest) or (rest.istitle() and len(rest.split()) <= 8)
        ):
            return 1 if "." not in numbering else 2
    return 0


def _split_label(line: str) -> tuple[str, str] | None:
    if ":" not in line:
        return None
    label, _, value = line.partition(":")
    key = label.strip().lower().rstrip("*_ ")
    if key in _LABELS:
        return _LABELS[key], value.strip()
    return None


def _headline_block(text: str, level: int) -> SemanticBlock:
    low = text.strip().lower().rstrip(":")
    if low in _TITLE_WORDS or (
        level == 1 and len(text.split()) <= 4 and any(w in low for w in _TITLE_WORDS)
    ):
        return _make("document_title", text=text, level=1)
    return _make(
        "major_section_heading" if level == 1 else "subsection_heading",
        text=text, level=level,
    )


def _row_blocks(cells: list[str], group: str) -> list[SemanticBlock]:
    label = (cells[0] if cells else "").strip()
    amount, figure = None, ""
    for cell in reversed(cells):
        parsed = classify.parse_amount(cell)
        if parsed is not None:
            amount, figure = parsed, cell.strip()
            break
    if _SUBTOTAL_RE.match(label):
        return [_make("subtotal", text=" | ".join(cells), items=list(cells),
                      value=amount, figure=figure, group=group)]
    if _GRAND_TOTAL_RE.match(label):
        return [_make("grand_total", text=" | ".join(cells), items=list(cells),
                      value=amount, figure=figure, group=group)]
    return [_make("table_row", text=" | ".join(cells), items=list(cells),
                  value=amount, figure=figure, group=group)]


def _parse_markdown_table(lines: list[str], start: int) -> tuple[list[SemanticBlock], int]:
    header_cells = [c.strip() for c in lines[start].strip().strip("|").split("|")]
    group = uuid.uuid4().hex[:8]
    blocks: list[SemanticBlock] = [
        _make("table_header", items=[_clean(c) for c in header_cells], group=group)
    ]
    index = start + 2
    while index < len(lines):
        raw = lines[index].strip()
        if "|" not in raw:
            break
        cells = [_clean(c) for c in raw.strip("|").split("|")]
        blocks.extend(_row_blocks(cells, group))
        index += 1
    return blocks, index


def _parse_list(lines: list[str], start: int, numbered: bool) -> tuple[list[SemanticBlock], int]:
    pattern = _NUMBERED if numbered else _BULLET
    items: list[str] = []
    index = start
    while index < len(lines):
        match = pattern.match(lines[index])
        if not match:
            break
        items.append(_clean(match.group(1)))
        index += 1
    block_type = "numbered_list" if numbered else "bullet_list"
    return [_make(block_type, items=items)], index


def _trailing_cost(line: str) -> tuple[str, str] | None:
    """Split ``"Deep clean ........ 250,000"`` into a description and amount."""
    if "|" in line or classify.is_money(line) or classify.is_phone(line) or classify.is_date(line):
        return None
    match = classify.MARKED_MONEY_RE.search(line) or classify.BARE_MONEY_RE.search(line)
    if not match:
        return None
    tail = line[match.end():].strip()
    if tail and not re.fullmatch(r"[\s.,;:)%-]*", tail):
        return None
    desc = line[:match.start()].strip(" -–—:.\t")
    if len(desc) < 3 or not re.search(r"[A-Za-z]", desc):
        return None
    return desc, match.group(0).strip()


def _emit_label(label_type: str, value: str, blocks: list[SemanticBlock]) -> None:
    if label_type in {
        "client_name", "provider_name", "client_address", "service_address",
        "contact_information", "quotation_number", "quotation_date",
        "validity_period", "duration", "term", "subtitle", "document_title",
    }:
        blocks.append(_make(label_type, text=value))
    else:
        blocks.append(_make("introduction", text=value))


def _first_title(blocks: list[SemanticBlock]) -> str:
    for block in blocks:
        if block.type == "document_title" and block.text:
            return block.text
    return ""


def understand(
    text: str,
    *,
    kind: str = "auto",
    profile: BusinessProfile | None = None,
    client: ClientInfo | None = None,
) -> Understanding:
    source = repair_mojibake(text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = source.split("\n")
    blocks: list[SemanticBlock] = []
    title = ""
    subtitle = ""
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        if paragraph_lines:
            blocks.append(_make("paragraph", text=" ".join(paragraph_lines)))
            paragraph_lines.clear()

    index = 0
    while index < len(lines):
        raw = lines[index]
        line = raw.strip()

        if not line:
            flush_paragraph()
            index += 1
            continue

        # Markdown table.
        if (
            "|" in line
            and index + 1 < len(lines)
            and _MD_TABLE_SEP.match(lines[index + 1])
        ):
            flush_paragraph()
            table_blocks, index = _parse_markdown_table(lines, index)
            blocks.extend(table_blocks)
            continue

        heading_match = _HEADING.match(line)
        if heading_match:
            flush_paragraph()
            level = 1 if len(heading_match.group(1)) == 1 else 2
            block = _headline_block(_clean(heading_match.group(2)), level)
            blocks.append(block)
            if block.type == "document_title":
                title = block.text
            index += 1
            continue

        if _BULLET.match(line):
            flush_paragraph()
            list_blocks, index = _parse_list(lines, index, numbered=False)
            blocks.extend(list_blocks)
            continue

        labelled = _split_label(line)
        if labelled:
            flush_paragraph()
            label_type, value = labelled
            value = _clean(value)
            if value:
                _emit_label(label_type, value, blocks)
                if label_type == "subtitle" and not subtitle:
                    subtitle = value
                if label_type == "document_title":
                    title = value or title
            index += 1
            continue

        level = _looks_like_heading(line)
        if level and not _NUMBERED.match(line):
            flush_paragraph()
            block = _headline_block(_clean(line), level)
            blocks.append(block)
            if block.type == "document_title":
                title = block.text
            index += 1
            continue

        if _NUMBERED.match(line):
            flush_paragraph()
            if _looks_like_heading(line):
                block = _headline_block(_clean(line), 2)
                blocks.append(block)
            else:
                list_blocks, index = _parse_list(lines, index, numbered=True)
                blocks.extend(list_blocks)
                continue
            index += 1
            continue

        if classify.is_money(line):
            flush_paragraph()
            blocks.append(_make("cost_amount", text=line,
                                value=classify.parse_amount(line), figure=line))
            index += 1
            continue

        if classify.is_phone(line):
            flush_paragraph()
            blocks.append(_make("contact_information", text=line))
            index += 1
            continue

        cost = _trailing_cost(line)
        if cost:
            flush_paragraph()
            blocks.extend(_row_blocks([cost[0], cost[1]], uuid.uuid4().hex[:8]))
            index += 1
            continue

        if classify.is_amount_in_words(line):
            flush_paragraph()
            blocks.append(_make("amount_in_words", text=_clean(line)))
            index += 1
            continue

        lowered = line.lower()
        if "signature" in lowered or "signed" in lowered or "accepted for and on behalf" in lowered:
            flush_paragraph()
            blocks.append(_make("signature", text=_clean(line)))
            index += 1
            continue
        if "acceptance" in lowered and len(line) < 90:
            flush_paragraph()
            blocks.append(_make("client_acceptance", text=_clean(line)))
            index += 1
            continue

        paragraph_lines.append(_clean(line))
        index += 1

    flush_paragraph()

    for order, block in enumerate(blocks):
        block.order = order
    if not title:
        title = _first_title(blocks) or "Quotation"

    understanding = Understanding(
        title=title,
        subtitle=subtitle,
        blocks=blocks,
        blocks_seen=len(blocks),
        source_kind=kind,
    )
    return refresh(understanding, profile, client)


def _note_missing(understanding: Understanding, profile: BusinessProfile | None,
                  client: ClientInfo | None) -> None:
    missing: list[str] = []
    types = {b.type for b in understanding.blocks}
    if "client_name" not in types and not (client and client.name):
        missing.append("the client's name")
    if not (types & {"table_row", "cost_amount"}):
        missing.append("any priced lines")
    if not (types & {"subtotal", "grand_total"}):
        missing.append("a stated total")
    if "quotation_number" not in types:
        missing.append("a quotation number")
    understanding.missing = missing


def refresh(understanding: Understanding, profile: BusinessProfile | None = None,
            client: ClientInfo | None = None) -> Understanding:
    """Recompute ordering, totals and missing-info after the user edits blocks.

    The provider may fix a figure in the editor; the derived totals must follow
    without the model or the editor being trusted to do the arithmetic. This
    also normalises AI-supplied financial blocks — whose text reads like prose —
    into a value and, for totals, a label/amount pair.
    """
    for order, block in enumerate(understanding.blocks):
        block.order = order
        _normalize_financial(block)
    summary, warnings = reconcile(understanding.blocks)
    understanding.financials = summary
    understanding.blocks_seen = len(understanding.blocks)
    base_notes = [n for n in understanding.notes if not n.startswith("the priced lines")]
    understanding.notes = base_notes + list(warnings)
    _note_missing(understanding, profile, client)
    return understanding


def _normalize_financial(block: SemanticBlock) -> None:
    from services import classify

    if block.type not in ("table_row", "cost_amount", "subtotal", "grand_total"):
        return
    if block.type == "table_row":
        source = block.items[-1] if block.items else (block.text or block.figure or "")
        value, figure = classify.extract_amount(source)
        if value is not None:
            block.value, block.figure = value, figure or block.figure
    elif block.type == "cost_amount":
        value, figure = classify.extract_amount(block.text or block.figure or "")
        block.value, block.figure = value, figure or block.figure
    else:
        source = block.items[-1] if block.items else (block.text or block.figure or "")
        value, figure = classify.extract_amount(source)
        block.value, block.figure = value, figure
        if value is not None and not block.items:
            label = re.sub(re.escape(figure), "", block.text or "").strip(" .,:-")
            block.items = [label or block.type.replace("_", " ").title(), figure]
