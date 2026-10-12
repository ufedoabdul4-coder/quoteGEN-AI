"""Flow layout: turn meaning into placed lines across as many sheets as needed.

This module knows nothing about designs, coordinates inside a master, or the AI.
It receives *blocks* that say what they are (a paragraph, a heading, a priced
row) and a :class:`StyleSet` that says how each kind is set, and it returns
:class:`FlowPlacement` objects that carry a page, a baseline and the lines to
draw.

Two rules shape everything here:

* A block's height is what its text *actually* needs, measured against a real
  font. A paragraph that needs eight lines is eight lines tall, and the cursor
  moves down by all eight. Nothing is clipped to fit an original box.
* When a block will not fit, the cursor opens a new sheet and tries again. A
  heading refuses to be the last thing on a page; a table repeats its header on
  every continuation sheet; a paragraph taller than a page is split at a line
  boundary. Content is never dropped to make a page come out even.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Iterable

from services.fonts import FontRegistry, wrap_text

# -- block vocabulary --------------------------------------------------------

TITLE = "title"
SUBTITLE = "subtitle"
HEADING = "heading"
SUBHEADING = "subheading"
SUBSUBHEADING = "subsubheading"
PARAGRAPH = "paragraph"
LIST_ITEM = "list_item"
BULLET_LIST = "bullet_list"
NUMBERED_LIST = "numbered_list"
TABLE = "table"
SUBTOTAL = "subtotal"
GRAND_TOTAL = "grand_total"
SIGNATURE = "signature"
PROVIDER_NAME = "provider_name"
CONTACT_INFORMATION = "contact_information"
TERMS = "terms"
SPACER = "spacer"

BLOCK_TYPES = {
    TITLE, SUBTITLE, HEADING, SUBHEADING, SUBSUBHEADING, PARAGRAPH, LIST_ITEM,
    BULLET_LIST, NUMBERED_LIST, TABLE, SUBTOTAL, GRAND_TOTAL, SIGNATURE,
    PROVIDER_NAME, CONTACT_INFORMATION, TERMS, SPACER,
}

HEADING_TYPES = {HEADING, SUBHEADING, SUBSUBHEADING, TITLE, SUBTITLE}

HEADING_GAP = 0.25
BODY_GAP = 0.55
LIST_GAP = 0.35
SECTION_GAP = 1.0
SUBHEADING_GAP = 0.55
SUBSUBHEADING_GAP = 0.4
TITLE_GAP = 1.35
KEEP_WITH_NEXT_LINES = 3
LEAD_IN_KEEP_ITEMS = 2
MAX_FLOW_PAGES = 500

DEFAULT_CELL_PADDING_X = 4.0
DEFAULT_CELL_PADDING_Y = 3.0
DEFAULT_ROW_GAP = 1.5


class FlowError(ValueError):
    """The document cannot be laid out as asked."""


# -- content model -----------------------------------------------------------


@dataclass
class TableSpec:
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    totals: list[list[str]] = field(default_factory=list)
    column_ratios: list[float] | None = None


@dataclass
class FlowBlock:
    type: str
    text: str = ""
    level: int = 1
    numbered: bool = False
    table: TableSpec | None = None
    #: Blocks sharing a non-empty group are kept on the same page (a signature
    #: block, an acceptance clause). Empty means "flow normally".
    group: str = ""
    #: A label drawn bold in front of the text (e.g. "Phone:" over the number),
    #: so a signature block can keep its label's weight without bolding the
    #: whole line.
    label: str = ""
    rich_value: str = ""

    def __post_init__(self) -> None:
        if self.type not in BLOCK_TYPES:
            raise FlowError(f"unknown block type {self.type!r}")


@dataclass
class Style:
    font: str = "Arial"
    size: float = 10.5
    bold: bool = False
    italic: bool = False
    color: str = "#1B1B1B"
    align: str = "left"
    pitch: float = 0.0
    leading: float = 0.0

    def resolved_pitch(self) -> float:
        if self.leading:
            return self.size * self.leading
        return max(self.pitch or 0.0, self.size * 1.05)


@dataclass
class ContentArea:
    width: float
    height: float
    left: float
    top: float
    right: float
    bottom: float

    @property
    def column_width(self) -> float:
        return max(1.0, self.right - self.left)

    @property
    def usable_height(self) -> float:
        return max(1.0, self.bottom - self.top)


@dataclass
class StyleSet:
    title: Style
    subtitle: Style
    heading: Style
    subheading: Style
    subsubheading: Style
    body: Style
    list_item: Style
    table_header: Style
    table_cell: Style
    total: Style
    signature: Style
    contact: Style
    provider: Style
    bullet_text: str = "\u2022"
    bullet_gap: float = 2.0
    cell_padding_x: float = DEFAULT_CELL_PADDING_X
    cell_padding_y: float = DEFAULT_CELL_PADDING_Y
    row_gap: float = DEFAULT_ROW_GAP
    column_ratios: list[float] | None = None
    row_rule: float = 0.0


@dataclass
class FlowPlacement:
    page: int
    x: float
    y: float
    width: float
    lines: list[str]
    font: str
    size: float
    color: str
    align: str
    kind: str
    pitch: float = 0.0
    bold: bool = False
    italic: bool = False
    numbered: bool = False
    repeated_header: bool = False
    #: Table geometry so the renderer can shade a header band or stripe a row
    #: without re-deriving anything from the text.
    role: str = ""  # "" | "head" | "body" | "total"
    row_top: float = 0.0
    row_height: float = 0.0
    row_index: int = -1
    #: (label, value) drawn on the first line as bold + regular runs.
    rich: tuple[str, str] | None = None


@dataclass
class LayoutResult:
    placements: list[FlowPlacement] = field(default_factory=list)
    page_count: int = 0
    warnings: list[str] = field(default_factory=list)


# -- measurement -------------------------------------------------------------


def _style_for(kind: str, styles: StyleSet) -> Style:
    return {
        TITLE: styles.title,
        SUBTITLE: styles.subtitle,
        HEADING: styles.heading,
        SUBHEADING: styles.subheading,
        SUBSUBHEADING: styles.subsubheading,
        PARAGRAPH: styles.body,
        LIST_ITEM: styles.list_item,
        BULLET_LIST: styles.body,
        NUMBERED_LIST: styles.body,
        TERMS: styles.body,
        SIGNATURE: styles.signature,
        CONTACT_INFORMATION: styles.contact,
        PROVIDER_NAME: styles.provider,
        TABLE: styles.table_cell,
        SUBTOTAL: styles.total,
        GRAND_TOTAL: styles.total,
        SPACER: styles.body,
    }[kind]


def _measure(text: str, style: Style, width: float, registry: FontRegistry) -> list[str]:
    if not text or not text.strip():
        return []
    face = registry.resolve(style.font, bold=style.bold, italic=style.italic)
    return wrap_text(text, face, style.size, max(1.0, width))


@dataclass
class Measured:
    lines: list[str]
    height: float
    style: Style


def block_height(line_count: int, style: Style) -> float:
    if line_count <= 0:
        return 0.0
    pitch = style.resolved_pitch()
    return style.size * 0.98 + (line_count - 1) * pitch - style.size * 0.22


def first_baseline(top: float, style: Style) -> float:
    return top + style.size * 0.98 - style.size * 0.22


def lines_that_fit(area: ContentArea, style: Style) -> int:
    per_line = style.resolved_pitch()
    if per_line <= 0:
        return 1
    return max(1, int((area.usable_height - style.size * 0.76) // per_line) + 1)


def split_measured(measured: Measured, area: ContentArea) -> list[Measured]:
    per_page = lines_that_fit(area, measured.style)
    if len(measured.lines) <= per_page:
        return [measured]
    pieces: list[Measured] = []
    for start in range(0, len(measured.lines), per_page):
        chunk = measured.lines[start:start + per_page]
        pieces.append(Measured(lines=chunk, height=block_height(len(chunk), measured.style),
                               style=measured.style))
    return pieces


def _measure_block(block: FlowBlock, styles: StyleSet, area: ContentArea,
                   registry: FontRegistry, *, indent: float = 0.0, marker: str = "") -> Measured:
    style = _style_for(block.type, styles)
    text = block.text
    if block.type == LIST_ITEM and marker:
        text = f"{marker} {text}"
    lines = _measure(text, style, area.column_width - indent, registry)
    return Measured(lines=lines, height=block_height(len(lines), style), style=style)


def _indent_for(block: FlowBlock, styles: StyleSet) -> float:
    if block.type != LIST_ITEM:
        return 0.0
    return max(0.0, styles.bullet_gap) + styles.list_item.size * 0.9


def gap_after(block: FlowBlock, style: Style) -> float:
    pitch = style.resolved_pitch()
    # Headings sit ~3pt above the text they name, whatever the body size.
    if block.type in HEADING_TYPES:
        return 3.0
    if block.type == LIST_ITEM:
        return pitch * LIST_GAP
    return pitch * BODY_GAP


def gap_before(block: FlowBlock, style: Style) -> float:
    if block.type not in HEADING_TYPES:
        return 0.0
    # Absolute gaps so a hierarchy reads the same on any master: ~12pt before a
    # major section, ~8pt before a subsection.
    if block.type == TITLE:
        return 18.0
    if block.type == HEADING:
        return 12.0
    if block.type == SUBHEADING:
        return 8.0
    if block.type == SUBSUBHEADING:
        return 8.0
    return 8.0


# -- list numbering ----------------------------------------------------------

_OWN_ENUMERATOR = re.compile(r"^\s*(\(?\d{1,3}[.)]|[A-Za-z][.)])\s+")


def split_own_enumerator(text: str) -> tuple[str, str]:
    match = _OWN_ENUMERATOR.match(text or "")
    if not match:
        return "", text or ""
    return match.group(1), text[match.end():]


def _list_marker(block: FlowBlock, blocks: list[FlowBlock], index: int) -> str:
    if not block.numbered:
        return ""
    own, _ = split_own_enumerator(block.text)
    if own:
        return own
    number = 1
    for back in range(index - 1, -1, -1):
        other = blocks[back]
        if other.type == NUMBERED_LIST:
            break
        if other.type == LIST_ITEM and other.numbered:
            number += 1
        elif other.type not in (BULLET_LIST,):
            break
    return f"{number}."


# -- tables ------------------------------------------------------------------


@dataclass
class RowLayout:
    cells: list[str]
    lines: list[list[str]]
    height: float
    style: Style
    is_header: bool = False
    is_total: bool = False


def column_widths(table: TableSpec, styles: StyleSet, area: ContentArea) -> list[float]:
    count = max(
        [len(table.headers), *(len(r) for r in table.rows), *(len(r) for r in table.totals), 0]
    )
    if count <= 0:
        return []
    total = area.column_width
    ratios = table.column_ratios or styles.column_ratios
    if ratios and len(ratios) >= count:
        ratios = ratios[:count]
        total_ratio = sum(ratios) or 1.0
        widths = [total * (r / total_ratio) for r in ratios]
    else:
        rest = max(1, count - 1)
        widths = [total * 2.0 / (2.0 + rest)] + [total / (2.0 + rest)] * rest
    minimum_figure = min(48.0, total * 0.12)
    if len(widths) >= 2 and widths[-1] < minimum_figure:
        surplus = widths[-1] - minimum_figure
        widths[-1] = minimum_figure
        widths[0] = max(minimum_figure, widths[0] - surplus)
    return widths


def measure_row(cells, widths, style, styles, registry, *, is_header=False, is_total=False) -> RowLayout:
    face = registry.resolve(style.font, bold=style.bold, italic=style.italic)
    inner = [max(1.0, w - 2.0 * styles.cell_padding_x) for w in widths]
    lines: list[list[str]] = []
    for index, cell in enumerate(cells):
        width = inner[index] if index < len(inner) else inner[-1]
        cell_lines = wrap_text(str(cell or ""), face, style.size, width)
        lines.append(cell_lines or [""])
    tallest = max((len(entry) for entry in lines), default=1)
    height = block_height(tallest, style) + 2.0 * styles.cell_padding_y
    return RowLayout(cells=[str(c or "") for c in cells], lines=lines, height=height,
                     style=style, is_header=is_header, is_total=is_total)


def measure_table(table: TableSpec, styles: StyleSet, area: ContentArea, registry: FontRegistry):
    widths = column_widths(table, styles, area)
    if not widths:
        return [], []
    count = len(widths)

    def fit(cells):
        return (list(cells) + [""] * count)[:count]

    rows: list[RowLayout] = []
    if table.headers:
        rows.append(measure_row(fit(table.headers), widths, styles.table_header, styles, registry,
                                is_header=True))
    for r in table.rows:
        rows.append(measure_row(fit(r), widths, styles.table_cell, styles, registry))
    for r in table.totals:
        rows.append(measure_row(fit(r), widths, styles.total, styles, registry, is_total=True))
    return rows, widths


# -- cursor ------------------------------------------------------------------


class _Cursor:
    def __init__(self, area: ContentArea) -> None:
        self.area = area
        self.page = 1
        self.y = area.top
        self.first_on_page = True

    @property
    def remaining(self) -> float:
        return self.area.bottom - self.y

    def new_page(self) -> None:
        self.page += 1
        self.y = self.area.top
        self.first_on_page = True

    def draw(self, height: float) -> None:
        self.y += max(0.0, height)
        self.first_on_page = False

    def gap(self, space: float) -> None:
        self.y += max(0.0, space)


def _place(cursor: _Cursor, measured: Measured, *, indent: float, kind: str,
           x: float | None = None, width: float | None = None, align: str | None = None,
           repeated_header: bool = False, numbered: bool = False,
           rich: tuple[str, str] | None = None) -> FlowPlacement:
    style = measured.style
    left = (cursor.area.left + indent) if x is None else x
    usable = (cursor.area.column_width - indent) if width is None else width
    placement = FlowPlacement(
        page=cursor.page, x=left, y=first_baseline(cursor.y, style), width=usable,
        lines=list(measured.lines), font=style.font, size=style.size, color=style.color,
        align=align or style.align, kind=kind, pitch=style.resolved_pitch(),
        bold=style.bold, italic=style.italic, repeated_header=repeated_header,
        numbered=numbered, rich=rich,
    )
    cursor.draw(measured.height)
    return placement


def _flow_row(cursor: _Cursor, row: RowLayout, widths, styles: StyleSet, kind: str, *,
              repeated_header: bool = False, role: str = "body", row_index: int = -1) -> list[FlowPlacement]:
    placements: list[FlowPlacement] = []
    style = row.style
    row_top = cursor.y
    inner = [max(1.0, w - 2.0 * styles.cell_padding_x) for w in widths]
    last_index = len(widths) - 1
    for index, cell_lines in enumerate(row.lines):
        if index >= len(widths):
            break
        if row.is_header:
            align = style.align
        elif index == last_index and len(widths) > 1:
            align = "right"
        else:
            align = style.align
        placements.append(FlowPlacement(
            page=cursor.page, x=cursor.area.left + sum(widths[:index]) + styles.cell_padding_x,
            y=first_baseline(row_top + styles.cell_padding_y, style), width=inner[index],
            lines=list(cell_lines), font=style.font, size=style.size, color=style.color,
            align=align, kind=f"{kind}:cell", pitch=style.resolved_pitch(),
            bold=style.bold, italic=style.italic, repeated_header=repeated_header,
            role=role, row_top=row_top, row_height=row.height, row_index=row_index,
        ))
    cursor.draw(row.height)
    return placements


def _flow_table(cursor: _Cursor, block: FlowBlock, styles: StyleSet, area: ContentArea,
                registry: FontRegistry, result: LayoutResult) -> None:
    table = block.table
    if table is None:
        return
    rows, widths = measure_table(table, styles, area, registry)
    if not rows or not widths:
        return
    header = [r for r in rows if r.is_header]
    body_rows = [r for r in rows if not r.is_header and not r.is_total]
    total_rows = [r for r in rows if r.is_total]

    def emit_header(repeated: bool) -> None:
        for head in header:
            result.placements.extend(_flow_row(cursor, head, widths, styles, block.type,
                                               repeated_header=repeated, role="head", row_index=-1))
            cursor.gap(styles.row_gap)

    if not cursor.first_on_page and sum(r.height for r in rows) > cursor.remaining:
        cursor.new_page()
    emit_header(repeated=False)
    for index, row in enumerate(body_rows):
        if not cursor.first_on_page and row.height > cursor.remaining:
            cursor.new_page()
            emit_header(repeated=True)
        result.placements.extend(_flow_row(cursor, row, widths, styles, block.type,
                                           role="body", row_index=index))
        cursor.gap(styles.row_gap)
    for row in total_rows:
        if not cursor.first_on_page and row.height > cursor.remaining:
            cursor.new_page()
            emit_header(repeated=True)
        result.placements.extend(_flow_row(cursor, row, widths, styles, block.type,
                                           role="total", row_index=-1))
        cursor.gap(styles.row_gap)
    cursor.gap(styles.body.resolved_pitch() * BODY_GAP)


def _table_height(block: FlowBlock, styles: StyleSet, area: ContentArea,
                  registry: FontRegistry) -> float:
    if block.table is None:
        return 0.0
    rows, _ = measure_table(block.table, styles, area, registry)
    if not rows:
        return 0.0
    return (sum(row.height for row in rows) + styles.row_gap * len(rows)
            + styles.body.resolved_pitch() * BODY_GAP)


def _run_extent(blocks, index: int, styles: StyleSet, area: ContentArea,
                registry: FontRegistry, *, with_lead: bool = False) -> float:
    """Vertical room the block at ``index`` needs *together with what follows it*.

    A heading never ends a page, a lead-in sentence never leaves its first two
    list items, and an orphan list item is never alone: each block therefore
    reserves its own height plus every gap inside its kept run. Using one
    measured extent (rather than adding pieces up by hand) is what keeps a run
    from being broken by a page boundary one point short.
    """
    if index >= len(blocks):
        return 0.0
    block = blocks[index]
    _, _, _, measured = _measure_at(blocks, index, styles, area, registry)
    style = measured.style
    total = measured.height + gap_after(block, style)
    if with_lead:
        total += gap_before(block, style)

    if block.type in HEADING_TYPES:
        if index + 1 < len(blocks):
            following = blocks[index + 1]
            if following.type == TABLE:
                total += _table_height(following, styles, area, registry)
            else:
                total += _run_extent(blocks, index + 1, styles, area, registry, with_lead=True)
    elif block.type == PARAGRAPH and (block.text or "").rstrip().endswith(":"):
        seen = 0
        j = index + 1
        while j < len(blocks) and seen < LEAD_IN_KEEP_ITEMS:
            following = blocks[j]
            if following.type == LIST_ITEM:
                _, _, _, extra = _measure_at(blocks, j, styles, area, registry)
                total += gap_before(following, extra.style) + extra.height + gap_after(following, extra.style)
                seen += 1
            elif following.type in (BULLET_LIST, NUMBERED_LIST, SPACER):
                _, _, _, extra = _measure_at(blocks, j, styles, area, registry)
                total += gap_before(following, extra.style) + extra.height + gap_after(following, extra.style)
            else:
                break
            j += 1
    elif (block.type == LIST_ITEM and index + 1 < len(blocks)
            and blocks[index + 1].type == LIST_ITEM):
        _, _, _, extra = _measure_at(blocks, index + 1, styles, area, registry)
        total += gap_before(blocks[index + 1], extra.style) + extra.height
    return total


def rich_for(block: FlowBlock) -> tuple[str, str] | None:
    """The (bold prefix, regular value) pair a block carries on its first line."""
    label = (block.label or "").strip()
    if not label:
        return None
    return label, block.rich_value


def _marker_for(block: FlowBlock, blocks, index: int, styles: StyleSet):
    if block.type != LIST_ITEM:
        return block, "", 0.0
    own, wording = split_own_enumerator(block.text)
    if own:
        return replace(block, text=wording), own, _indent_for(block, styles)
    if block.numbered:
        return block, _list_marker(block, blocks, index), _indent_for(block, styles)
    return block, styles.bullet_text, _indent_for(block, styles)


def _measure_at(blocks, index: int, styles: StyleSet, area: ContentArea, registry: FontRegistry):
    effective, marker, indent = _marker_for(blocks[index], blocks, index, styles)
    measured = _measure_block(effective, styles, area, registry, indent=indent, marker=marker)
    return effective, marker, indent, measured


def _group_span(blocks, start: int) -> tuple[int, int]:
    group = blocks[start].group
    if not group:
        return start, start
    end = start
    while end < len(blocks) and blocks[end].group == group:
        end += 1
    return start, end


def _group_height(blocks, start: int, end: int, styles: StyleSet, area: ContentArea,
                  registry: FontRegistry) -> float:
    total = 0.0
    for position in range(start, end):
        _, _, _, measured = _measure_at(blocks, position, styles, area, registry)
        lead = 0.0 if position == start else gap_before(blocks[position], measured.style)
        total += lead + measured.height + gap_after(blocks[position], measured.style)
    return total



def flow_document(blocks, styles: StyleSet, area: ContentArea, registry: FontRegistry,
                  *, max_pages: int = MAX_FLOW_PAGES) -> LayoutResult:
    """Lay a document out, in order, across as many sheets as it needs."""
    result = LayoutResult()
    blocks = list(blocks)
    cursor = _Cursor(area)

    index = 0
    while index < len(blocks):
        if cursor.page > max_pages:
            result.warnings.append(f"flow stopped after {max_pages} pages; the rest was not laid out")
            break
        block = blocks[index]

        if block.type == SPACER:
            space = styles.body.resolved_pitch() * max(1, block.level)
            if space > cursor.remaining and not cursor.first_on_page:
                cursor.new_page()
            cursor.gap(space)
            index += 1
            continue

        if block.type == TABLE:
            _flow_table(cursor, block, styles, area, registry, result)
            index += 1
            continue

        span_start, span_end = _group_span(blocks, index)
        if span_end > span_start and (index == 0 or blocks[index - 1].group != block.group):
            if not cursor.first_on_page:
                group_height = _group_height(blocks, span_start, span_end, styles, area, registry)
                if group_height > cursor.remaining:
                    cursor.new_page()

        block, marker, indent, measured = _measure_at(blocks, index, styles, area, registry)
        if not measured.lines:
            index += 1
            continue

        needed = _run_extent(blocks, index, styles, area, registry)
        lead = 0.0 if cursor.first_on_page else gap_before(block, measured.style)
        needed += lead

        if not cursor.first_on_page and needed > cursor.remaining:
            cursor.new_page()
            lead = 0.0
        if lead:
            cursor.gap(lead)

        if measured.height > area.usable_height:
            for piece in split_measured(measured, area):
                if not cursor.first_on_page and piece.height > cursor.remaining:
                    cursor.new_page()
                result.placements.append(_place(cursor, piece, indent=indent, kind=block.type,
                                                numbered=bool(marker),
                                                rich=rich_for(block)))
            result.warnings.append(
                f"a {block.type} was longer than one page and continued onto the next sheet"
            )
            cursor.gap(gap_after(block, measured.style))
            index += 1
            continue

        result.placements.append(_place(cursor, measured, indent=indent, kind=block.type,
                                        numbered=bool(marker), rich=rich_for(block)))
        cursor.gap(gap_after(block, measured.style))
        index += 1

    result.page_count = cursor.page
    return result
