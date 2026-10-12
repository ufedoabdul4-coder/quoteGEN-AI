"""Map understood blocks onto the layout engine's flow blocks.

The understanding stage speaks *semantics* ("this is a grand total"); the layout
engine speaks *flow* ("this is a table"). This adapter is the one place that
knows both vocabularies, so a change to either never leaks into the other.

Consecutive priced blocks — a header, its rows and its totals — collapse into a
single :class:`services.flow.TableSpec`, which is what lets the layout engine
repeat the header on a continuation sheet instead of treating each row as its
own tiny table.
"""

from __future__ import annotations

import re

from models import BusinessProfile, ClientInfo, SemanticBlock, Understanding
from services.flow import FlowBlock, TableSpec

_PRICED = {"table_header", "table_row", "subtotal", "grand_total", "cost_amount"}

_BULLET_TYPES = {"bullet_list", "scope_item", "equipment_item", "material_item", "safety_item"}

_HEADING_TYPES = {"heading", "major_section_heading", "subsection_heading"}

#: A heading with one of these labels opens a signature-style section whose whole
#: body (heading included) is kept on one page by the layout engine.
_SIGNATURE_HEADINGS = {
    "prepared by", "prepared", "client acceptance", "acceptance",
    "signature", "signatures", "submitted by", "submitted",
    "signed by", "authorised by", "authorized by",
}


def _signature_label(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower()).rstrip(":")


def _flow_heading(kind: str, text: str, level: int, group: str) -> FlowBlock:
    if kind == "document_title":
        return FlowBlock("title", text=text, level=1, group=group)
    if kind == "major_section_heading":
        level = 1
    elif kind == "subsection_heading":
        level = 2
    elif _signature_label(text) in _SIGNATURE_HEADINGS:
        # SUBMITTED BY / PREPARED BY / CLIENT ACCEPTANCE are subsection-level,
        # whatever their Markdown marker says, so they match the mobile output.
        level = 2
    depth = min(max(int(level or 1), 1), 3)
    flow_type = {1: "heading", 2: "subheading", 3: "subsubheading"}[depth]
    return FlowBlock(flow_type, text=text, level=depth, group=group)


def _table_from(group: list[SemanticBlock]) -> FlowBlock:
    headers: list[str] = []
    rows: list[list[str]] = []
    totals: list[list[str]] = []
    width = 0
    for block in group:
        cells = block.items if block.items else [block.text]
        width = max(width, len(cells))
        if block.type == "table_header" and not headers:
            headers = cells
        elif block.type in ("subtotal", "grand_total"):
            totals.append(cells)
        else:
            rows.append(cells)

    if not headers and rows:
        # Synthesise a header only when the rows clearly have a description and
        # an amount, which is the shape almost every cost table takes.
        if width == 2:
            headers = ["Description", "Amount"]
        else:
            headers = ["" for _ in range(width)]

    ratios = None
    if width == 2:
        ratios = [3.0, 1.0]
    elif width == 3:
        ratios = [3.0, 1.0, 1.0]
    return FlowBlock("table", table=TableSpec(headers=headers, rows=rows, totals=totals,
                                              column_ratios=ratios))


def to_flow_blocks(understanding: Understanding, profile: BusinessProfile | None = None,
                   client: ClientInfo | None = None) -> list[FlowBlock]:
    blocks = understanding.blocks
    flow: list[FlowBlock] = []
    index = 0
    current_group = ""

    while index < len(blocks):
        block = blocks[index]

        if block.type in _PRICED:
            # A total that stands alone (not inside a Markdown table, so its own
            # text, not a cell) is NOT a table row: it must render as its own
            # bold line directly under the table, grouped with the words that
            # spell it out, instead of becoming a duplicate row in the grid.
            if block.type in ("subtotal", "grand_total") and not (block.group or ""):
                fin_group = "fin_" + re.sub(r"\W+", "_", (block.text or block.type).lower())[:48]
                flow.append(_map_single(block, group=fin_group))
                index += 1
                while index < len(blocks) and blocks[index].type == "amount_in_words":
                    flow.append(_map_single(blocks[index], group=fin_group))
                    index += 1
                continue
            table_group: list[SemanticBlock] = []
            while index < len(blocks) and blocks[index].type in _PRICED:
                current_b = blocks[index]
                if current_b.type in ("subtotal", "grand_total") and not (current_b.group or ""):
                    break
                table_group.append(current_b)
                index += 1
            if table_group:
                flow.append(_table_from(table_group))
            if index < len(blocks) and blocks[index].type in ("subtotal", "grand_total") and not (blocks[index].group or ""):
                fin_group = "fin_" + re.sub(r"\W+", "_", (blocks[index].text or blocks[index].type).lower())[:48]
                flow.append(_map_single(blocks[index], group=fin_group))
                index += 1
                while index < len(blocks) and blocks[index].type == "amount_in_words":
                    flow.append(_map_single(blocks[index], group=fin_group))
                    index += 1
                continue
            if table_group:
                continue
            # If we broke on a standalone total, the logic above should have handled it;
            # otherwise just consume this priced block as-is.
            mapped = _map_single(block, group=current_group)
            if mapped is not None:
                flow.append(mapped)
            index += 1
            continue

        if block.type in _HEADING_TYPES or block.type == "document_title":
            if _signature_label(block.text) in _SIGNATURE_HEADINGS:
                # A signature section owns every block until the next one, so the
                # whole PREPARED BY / CLIENT ACCEPTANCE run is kept on one page.
                current_group = "sig_" + re.sub(r"\W+", "_", _signature_label(block.text))
        elif block.type in ("signature", "client_acceptance") and not current_group:
            current_group = "sig_" + str(block.type)

        mapped = _map_single(block, group=current_group)
        if mapped is not None:
            flow.append(mapped)
        index += 1

    return flow


def _map_single(block: SemanticBlock, group: str = "") -> FlowBlock | None:
    kind = block.type
    text = block.text or ""

    def rich(flow: FlowBlock) -> FlowBlock:
        meta = block.meta or {}
        if meta.get("label"):
            flow.label = meta["label"]
            flow.rich_value = meta.get("rich_value", "")
        return flow

    if kind in _HEADING_TYPES or kind == "document_title":
        return _flow_heading(kind, text, block.level, group)
    if kind == "subtitle":
        return FlowBlock("subtitle", text=text, group=group)
    if kind in _BULLET_TYPES:
        items = block.items or [text]
        return FlowBlock("bullet_list", text="\n".join(items), group=group)
    if kind == "numbered_list":
        return FlowBlock("numbered_list", text="\n".join(block.items or [text]), group=group)
    if kind in ("subtotal", "grand_total"):
        return rich(FlowBlock(kind, text=text, group=group))
    if kind in ("client_name", "client_address", "service_address", "contact_information",
                "quotation_number", "quotation_date", "validity_period"):
        return rich(FlowBlock("contact_information", text=text, group=group))
    if kind == "amount_in_words":
        return FlowBlock("paragraph", text=text, group=group)
    if kind == "provider_name":
        return FlowBlock("provider_name", text=text, group=group)
    if kind in ("duration", "term", "introduction", "paragraph"):
        return FlowBlock("paragraph", text=text, group=group)
    if kind in ("signature", "client_acceptance"):
        fallback = text or "Signature: ______________________"
        return rich(FlowBlock("signature", text=fallback, group=group))
    if kind == "cost_amount":
        return FlowBlock("paragraph", text=text, group=group)
    return FlowBlock("paragraph", text=text, group=group)


def expand_lists(blocks: list[FlowBlock], styles=None) -> list[FlowBlock]:
    """Expand multi-item list blocks into individual ``list_item`` blocks.

    Kept separate from :func:`to_flow_blocks` so the mapping stays a pure
    type-translation and the (optional) style-aware expansion can be tested on
    its own.
    """
    out: list[FlowBlock] = []
    for block in blocks:
        if block.type in ("bullet_list", "numbered_list"):
            numbered = block.type == "numbered_list"
            for line in block.text.split("\n"):
                if line.strip():
                    out.append(FlowBlock("list_item", text=line.strip(), numbered=numbered))
        else:
            out.append(block)
    return out
