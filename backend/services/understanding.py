"""Content understanding: raw input in, ordered semantic blocks out.

This is the deterministic half of the AI pipeline. Given free text, pasted
Markdown or a structured note, it decides what each piece *is* — a heading, a
priced row, a client name, an amount in words — and returns the blocks in the
order the provider wrote them, together with the amounts it could prove.

Two rules are absolute and are enforced here rather than trusted to a model:

* **Nothing is invented.** A figure only becomes monetary when
  :mod:`services.classify` can read it as money, and reconciliation in
  :mod:`services.financials` reports any mismatch rather than hiding it.
* **Nothing is dropped.** Every non-empty source line must land in a block;
  :func:`verify_completeness` re-reads the finished blocks against the source
  and reports the lines that went missing. The understanding stage keeps the
  provider's own words, in their own case, and never rewrites them.

An AI provider may refine *which* type a block is and *which* heading level it
carries, but it never supplies the words: the text always comes from the source.
"""

from __future__ import annotations

import re
import uuid

from models import BusinessProfile, ClientInfo, SemanticBlock, Understanding
from services import classify
from services.financials import reconcile

_INLINE_MD = re.compile(r"(\*\*|`{1,3})")
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_BULLET = re.compile(r"^\s*([-*•·‣▪◦○])\s+(.*\S)\s*$")
_NUMBERED = re.compile(r"^\s*(?:\d{1,3}|[a-zA-Z])[.)]\s+(.*\S)\s*$")
_NUMBERED_HEADING = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2}){0,3})[.)]?\s+(.+?)\s*$")
_MD_TABLE_SEP = re.compile(r"^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$")
_MD_RULE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_MOJIBAKE_MARKERS = ("Ã", "Â", "â", "ƒ")

_MAX_HEADING_LEVEL = 3

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
}

_TITLE_WORDS = {"quotation", "quote", "proposal", "invoice", "estimate", "proforma", "pro forma"}

#: Headings that open a signature block. Their sections stay together on one
#: page, and a short all-caps name directly under one is the provider, not a
#: section heading.
_SIGNATURE_LABELS = {
    "prepared by", "prepared", "client acceptance", "acceptance",
    "submitted by", "submitted", "signed by", "authorised by", "authorized by",
}

#: ``**Label:** value`` and ``**Label**: value`` — the label was deliberately
#: emboldened next to a plain value, so it must render bold over a regular value.
_BOLD_LABEL_COLON = re.compile(r"^\s*\*\*(.+?)\*\*\s*:\s*(.*)$")
_BOLD_LABEL_INNER = re.compile(r"^\s*\*\*(.+?):\*\*\s*(.*)$")
#: A whole line wrapped in ``**…**`` is emphasised text, never a section heading.
_WHOLE_BOLD = re.compile(r"^\s*\*\*(.+?)\*\*\s*$")


def _clean(text: str) -> str:
    """Remove Markdown syntax but keep the provider's own words and their case."""
    text = _MD_LINK.sub(r"\1", text or "")
    text = _INLINE_MD.sub("", text)
    return " ".join(text.split()).strip()


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
    """Return a heading level (1-3) when a line reads like a heading, else 0."""
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
            if "." in numbering:
                depth = min(numbering.count(".") + 1, _MAX_HEADING_LEVEL)
                return max(2, depth)
            return 1
    return 0


def _split_label(line: str) -> tuple[str, str] | None:
    if ":" not in line:
        return None
    label, _, value = line.partition(":")
    key = label.strip().strip("*_` \t").lower()
    if key in _LABELS:
        return _LABELS[key], value.strip()
    return None


def _rich_split(line: str) -> tuple[str, str] | None:
    """A line like ``**Phone:** 0916…`` or ``**Signature:** ______``.

    Returns ``(label, value)`` when the line's label was explicitly bolded, so
    the renderer can draw the weight the provider chose instead of flattening
    every ``**…**`` to plain text.
    """
    match = _BOLD_LABEL_COLON.match(line) or _BOLD_LABEL_INNER.match(line)
    if not match:
        return None
    label = match.group(1).strip().strip("*_` \t")
    value = match.group(2).strip()
    return (label, value) if label else None


def _heading_block(text: str, level: int, *, is_title: bool) -> SemanticBlock:
    if is_title:
        return _make("document_title", text=text, level=1)
    return _make("heading", text=text, level=min(max(level, 1), _MAX_HEADING_LEVEL))


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
        items.append(_clean(match.group(match.lastindex)))
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


def _emit_label(label_type: str, source_line: str, blocks: list[SemanticBlock]) -> None:
    """Emit a labelled line, keeping the provider's own label and value together."""
    text = _clean(source_line)
    if label_type in {
        "client_name", "provider_name", "client_address", "service_address",
        "contact_information", "quotation_number", "quotation_date",
        "validity_period", "duration", "term", "subtitle", "document_title",
    }:
        blocks.append(_make(label_type, text=text))
    else:
        blocks.append(_make("introduction", text=text))


def _first_title(blocks: list[SemanticBlock]) -> str:
    for block in blocks:
        if block.type == "document_title" and block.text:
            return block.text
    return ""


def _is_numbered_section(text: str) -> bool:
    match = _NUMBERED_HEADING.match(text.strip().rstrip(":").strip())
    return bool(match)


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
    title_seen = False
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        if paragraph_lines:
            blocks.append(_make("paragraph", text=" ".join(paragraph_lines)))
            paragraph_lines.clear()

    def emit_heading(raw_text: str, level: int) -> None:
        nonlocal title, title_seen
        cleaned = _clean(raw_text)
        if not cleaned:
            return
        # A "heading" that is really a total or an amount in words keeps its
        # label and stays financial; forcing it to a heading would lose a figure.
        if classify.is_amount_in_words(cleaned):
            blocks.append(_make("amount_in_words", text=cleaned))
            return
        if _GRAND_TOTAL_RE.match(cleaned):
            value, figure = classify.extract_amount(cleaned)
            blocks.append(_make("grand_total", text=cleaned, value=value, figure=figure))
            return
        if _SUBTOTAL_RE.match(cleaned):
            value, figure = classify.extract_amount(cleaned)
            blocks.append(_make("subtotal", text=cleaned, value=value, figure=figure))
            return
        low = cleaned.lower().rstrip(":")
        if low in _SIGNATURE_LABELS:
            # A signature heading stays a heading (mapped to subsection level);
            # it is not a person or a company name to nibble off.
            blocks.append(_make("heading", text=cleaned,
                                level=min(max(level, 1), _MAX_HEADING_LEVEL)))
            return
        # A short all-caps name that sits directly under a signature heading is
        # the provider's own masthead (KAMIBRIX LIMITED), which belongs on the
        # PREPARED BY block as emphasised body text, not as a bare section.
        if (
            blocks
            and blocks[-1].type == "heading"
            and (blocks[-1].text or "").lower().rstrip(":") in _SIGNATURE_LABELS
            and not _is_numbered_section(cleaned)
            and _is_all_caps(cleaned)
            and len(cleaned.split()) <= 6
        ):
            blocks.append(_make("provider_name", text=cleaned))
            return
        is_title = (
            level == 1
            and not title_seen
            and not _is_numbered_section(cleaned)
            and (len(cleaned.split()) > 4 or any(w in low for w in _TITLE_WORDS))
        )
        block = _heading_block(cleaned, level, is_title=is_title)
        blocks.append(block)
        if block.type == "document_title":
            title = block.text
            title_seen = True

    index = 0
    while index < len(lines):
        raw = lines[index]
        line = raw.strip()

        if not line:
            flush_paragraph()
            index += 1
            continue

        if _MD_RULE.match(line):
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
            level = min(len(heading_match.group(1)), _MAX_HEADING_LEVEL)
            emit_heading(heading_match.group(2), level)
            index += 1
            continue

        if _BULLET.match(line):
            flush_paragraph()
            list_blocks, index = _parse_list(lines, index, numbered=False)
            blocks.extend(list_blocks)
            continue

        rich = _rich_split(line)
        if rich:
            flush_paragraph()
            label_text, value = rich
            mapped = _split_label(line)
            block_type = mapped[0] if mapped else "contact_information"
            if label_text.lower().startswith("sign"):
                block_type = "signature"
            block = _make(block_type, text=_clean(line))
            block.meta["label"] = label_text + ":"
            block.meta["rich_value"] = _clean(value)
            blocks.append(block)
            index += 1
            continue

        whole = _WHOLE_BOLD.match(line)
        if whole:
            flush_paragraph()
            bold_text = _clean(whole.group(1))
            if bold_text:
                blocks.append(_make("provider_name", text=bold_text))
            index += 1
            continue

        labelled = _split_label(line)
        if labelled:
            flush_paragraph()
            label_type, value = labelled
            value = _clean(value)
            if value:
                _emit_label(label_type, line, blocks)
                if label_type == "subtitle" and not subtitle:
                    subtitle = value
                if label_type == "document_title":
                    title = value or title
            index += 1
            continue

        level = _looks_like_heading(line)
        if level and not _NUMBERED.match(line):
            flush_paragraph()
            emit_heading(line, level)
            index += 1
            continue

        if _NUMBERED.match(line):
            flush_paragraph()
            if _looks_like_heading(line):
                emit_heading(line, 2)
                index += 1
                continue
            list_blocks, index = _parse_list(lines, index, numbered=True)
            blocks.extend(list_blocks)
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
        if re.search(r"\bsign(?:ature|ed|ing)?\b", lowered) or "accepted for and on behalf" in lowered:
            flush_paragraph()
            blocks.append(_make("signature", text=_clean(line)))
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


# ---------------------------------------------------------------------------
# completeness
# ---------------------------------------------------------------------------


def _norm_for_check(text: str) -> str:
    """The comparison key the completeness gate uses: case- and space-insensitive."""
    return re.sub(r"[\s\u00ad\u2011\u2010\-]+", "", (text or "").lower())


def _strip_markers(line: str) -> str:
    line = re.sub(r"^\s*#{1,6}\s+", "", line.strip())
    line = re.sub(r"^\s*(?:[-*•·‣▪◦○]|\d{1,3}[.)])\s+", "", line)
    return line.strip()


def _is_separator_cell(cell: str) -> bool:
    stripped = cell.strip(" *")
    return bool(stripped) and set(stripped) <= set("-: ")


def source_candidates(text: str) -> list[str]:
    """Every content-bearing candidate a source line must leave in the output.

    A plain line yields one candidate; a Markdown table row yields one per cell,
    so a dropped priced line is caught cell by cell.
    """
    candidates: list[str] = []
    for raw in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        stripped = raw.strip()
        if not stripped or _MD_RULE.match(stripped) or _MD_TABLE_SEP.match(stripped):
            continue
        if stripped.startswith("|") and stripped.endswith("|") and "|" in stripped[1:-1]:
            for cell in stripped.strip("|").split("|"):
                if _is_separator_cell(cell):
                    continue
                cleaned = _clean(cell).strip(" *")
                if cleaned:
                    candidates.append(cleaned)
            continue
        value = _clean(_strip_markers(stripped))
        if value:
            candidates.append(value)
    return candidates


def verify_completeness(text: str, understanding: Understanding) -> list[str]:
    """Return the source lines that did not reach a block.

    The understanding stage is not allowed to drop content, so this is checked
    rather than assumed: an AI refinement that silently swallowed a heading is a
    failure the caller must see, not one to paper over.
    """
    haystack = " ".join(
        [block.text for block in understanding.blocks]
        + [item for block in understanding.blocks for item in block.items]
    )
    haystack = _norm_for_check(haystack)
    missing: list[str] = []
    for candidate in source_candidates(text):
        key = _norm_for_check(candidate)
        if key and key not in haystack:
            missing.append(candidate)
    return missing


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
            label = re.sub(re.escape(figure), "", block.text or "").strip()
            block.items = [label or block.type.replace("_", " ").title(), figure]
