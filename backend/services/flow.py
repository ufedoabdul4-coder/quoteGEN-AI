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
PARAGRAPH = "paragraph"
LIST_ITEM = "list_item"
BULLET_LIST = "bullet_list"
NUMBERED_LIST = "numbered_list"
TABLE = "table"
SUBTOTAL = "subtotal"
GRAND_TOTAL = "grand_total"
SIGNATURE = "signature"
CONTACT_INFORMATION = "contact_information"
TERMS = "terms"
SPACER = "spacer"

BLOCK_TYPES = {
    TITLE, SUBTITLE, HEADING, SUBHEADING, PARAGRAPH, LIST_ITEM, BULLET_LIST,
    NUMBERED_LIST, TABLE, SUBTOTAL, GRAND_TOTAL, SIGNATURE, CONTACT_INFORMATION,
    TERMS, SPACER,
}

HEADING_TYPES = {HEADING, SUBHEADING, TITLE, SUBTITLE}

HEADING_GAP = 0.45
BODY_GAP = 0.55
LIST_GAP = 0.35
SECTION_GAP = 1.1
KEEP_WITH_NEXT_LINES = 3
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
    body: Style
    list_item: Style
    table_header: Style
    table_cell: Style
    total: Style
    signature: Style
    contact: Style
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
        PARAGRAPH: styles.body,
        LIST_ITEM: styles.list_item,
        BULLET_LIST: styles.body,
        NUMBERED_LIST: styles.body,
        TERMS: styles.body,
        SIGNATURE: styles.signature,
        CONTACT_INFORMATION: styles.contact,
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
    if block.type in HEADING_TYPES:
        return pitch * HEADING_GAP
    if block.type == LIST_ITEM:
        return pitch * LIST_GAP
    return pitch * BODY_GAP


def gap_before(block: FlowBlock, style: Style) -> float:
    if block.type not in HEADING_TYPES:
        return 0.0
    return style.resolved_pitch() * SECTION_GAP


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
           repeated_header: bool = False, numbered: bool = False) -> FlowPlacement:
    style = measured.style
    left = (cursor.area.left + indent) if x is None else x
    usable = (cursor.area.column_width - indent) if width is None else width
    placement = FlowPlacement(
        page=cursor.page, x=left, y=first_baseline(cursor.y, style), width=usable,
        lines=list(measured.lines), font=style.font, size=style.size, color=style.color,
        align=align or style.align, kind=kind, pitch=style.resolved_pitch(),
        bold=style.bold, italic=style.italic, repeated_header=repeated_header,
        numbered=numbered,
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


def _keep_with_next_height(blocks, index, styles, area, registry) -> float:
    if index >= len(blocks):
        return 0.0
    following = blocks[index]
    style = _style_for(following.type, styles)
    if following.type == TABLE:
        return min(style.resolved_pitch() * KEEP_WITH_NEXT_LINES, area.usable_height * 0.25)
    lines = _measure(following.text, style, area.column_width, registry)
    return style.resolved_pitch() * min(len(lines) or 1, KEEP_WITH_NEXT_LINES)


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

        marker = ""
        if block.type == LIST_ITEM:
            own, wording = split_own_enumerator(block.text)
            if own:
                marker = own
                block = replace(block, text=wording)
            elif block.numbered:
                marker = _list_marker(block, blocks, index)
            else:
                marker = styles.bullet_text

        indent = _indent_for(block, styles)
        measured = _measure_block(block, styles, area, registry, indent=indent, marker=marker)
        if not measured.lines:
            index += 1
            continue

        needed = measured.height
        if block.type in HEADING_TYPES:
            needed += _keep_with_next_height(blocks, index + 1, styles, area, registry)
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
                                                numbered=bool(marker)))
            result.warnings.append(
                f"a {block.type} was longer than one page and continued onto the next sheet"
            )
            cursor.gap(gap_after(block, measured.style))
            index += 1
            continue

        result.placements.append(_place(cursor, measured, indent=indent, kind=block.type,
                                        numbered=bool(marker)))
        cursor.gap(gap_after(block, measured.style))
        index += 1

    result.page_count = cursor.page
    return result
