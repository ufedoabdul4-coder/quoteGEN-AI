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

from models import BusinessProfile, ClientInfo, SemanticBlock, Understanding
from services.flow import FlowBlock, TableSpec

_PRICED = {"table_header", "table_row", "subtotal", "grand_total", "cost_amount"}

_BULLET_TYPES = {"bullet_list", "scope_item", "equipment_item", "material_item", "safety_item"}


def _meta_line(label: str, value: str) -> str:
    if value.lower().startswith(label.lower()):
        return value
    return f"{label}: {value}"


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

    while index < len(blocks):
        block = blocks[index]

        if block.type in _PRICED:
            group: list[SemanticBlock] = []
            while index < len(blocks) and blocks[index].type in _PRICED:
                group.append(blocks[index])
                index += 1
            flow.append(_table_from(group))
            continue

        mapped = _map_single(block)
        if mapped is not None:
            flow.append(mapped)
        index += 1

    return flow


def _map_single(block: SemanticBlock) -> FlowBlock | None:
    kind = block.type
    text = block.text or ""

    if kind == "document_title":
        return FlowBlock("title", text=text)
    if kind == "subtitle":
        return FlowBlock("subtitle", text=text)
    if kind == "major_section_heading":
        return FlowBlock("heading", text=text)
    if kind == "subsection_heading":
        return FlowBlock("subheading", text=text)
    if kind in _BULLET_TYPES:
        items = block.items or [text]
        return FlowBlock("bullet_list", text="\n".join(items))
    if kind == "numbered_list":
        return FlowBlock("numbered_list", text="\n".join(block.items or [text]))
    if kind in ("client_name",):
        return FlowBlock("contact_information", text=_meta_line("Prepared for", text))
    if kind in ("client_address", "service_address"):
        return FlowBlock("contact_information", text=_meta_line("Address", text))
    if kind == "quotation_number":
        return FlowBlock("contact_information", text=_meta_line("Quotation No", text))
    if kind == "quotation_date":
        return FlowBlock("contact_information", text=_meta_line("Date", text))
    if kind == "validity_period":
        return FlowBlock("contact_information", text=_meta_line("Valid until", text))
    if kind in ("contact_information",):
        return FlowBlock("contact_information", text=text)
    if kind == "amount_in_words":
        return FlowBlock("paragraph", text=text)
    if kind in ("duration", "term", "introduction", "paragraph", "provider_name"):
        return FlowBlock("paragraph", text=text)
    if kind in ("signature",):
        return FlowBlock("signature", text=text or "Signature: ______________________")
    if kind == "client_acceptance":
        return FlowBlock("signature", text=text)
    if kind == "cost_amount":
        return FlowBlock("paragraph", text=text)
    return FlowBlock("paragraph", text=text)


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
