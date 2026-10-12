"""Turn a layout into a real PDF page.

The renderer is deliberately thin: the layout engine already decided what goes
where, so this module only paints the design, draws the lines at their
baselines, and adds the table furniture (header bands, zebra rows, total rules)
that the placements carry geometry for. Nothing here re-measures text or moves a
block; if a line is drawn, it was placed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pymupdf

from services.designs import Design, PaintContext, hex_rgb, paint_design
from services.fonts import FontRegistry
from services.flow import FlowBlock, FlowPlacement, flow_document


@dataclass
class RenderResult:
    pdf_bytes: bytes
    page_count: int
    warnings: list[str] = field(default_factory=list)


def _blit_reference(page: "pymupdf.Page", background_pdf: bytes) -> None:
    """Paint the single cleaned master design sheet on every output page."""
    src = pymupdf.open(stream=background_pdf, filetype="pdf")
    try:
        if src.page_count == 0:
            raise ValueError("Reference template contains no pages.")
        page.show_pdf_page(page.rect, src, 0)
    finally:
        src.close()


def _draw_table_furniture(page: "pymupdf.Page", placements: list[FlowPlacement],
                          design: Design, area_left: float, area_width: float,
                          cell_padding_x: float = 5.0) -> None:
    if design.kind == "reference":
        rows: dict[tuple[float, str], list[FlowPlacement]] = {}
        for placement in placements:
            if placement.role:
                key = (round(placement.row_top, 1), placement.role)
                rows.setdefault(key, []).append(placement)

        border = hex_rgb("#000000")
        for (_, role), cells in rows.items():
            cells.sort(key=lambda placement: placement.x)
            x0 = min(cell.x - cell_padding_x for cell in cells)
            x1 = max(cell.x + cell.width + cell_padding_x for cell in cells)
            row_top = min(cell.row_top for cell in cells)
            row_bottom = max(cell.row_top + cell.row_height for cell in cells)
            page.draw_rect(
                pymupdf.Rect(x0, row_top, x1, row_bottom),
                color=border, fill=None, width=0.5, overlay=True,
            )
            for cell in cells[:-1]:
                divider = cell.x + cell.width + cell_padding_x
                page.draw_line(
                    pymupdf.Point(divider, row_top),
                    pymupdf.Point(divider, row_bottom),
                    color=border, width=0.5, overlay=True,
                )
            if role == "total":
                page.draw_line(
                    pymupdf.Point(x0, row_top), pymupdf.Point(x1, row_top),
                    color=hex_rgb("#D9D4C7"), width=0.7, overlay=True,
                )
        return

    t = design.tokens
    seen: set[tuple[int, str]] = set()
    for pl in placements:
        if not pl.role:
            continue
        key = (round(pl.row_top, 1), pl.role)
        if key in seen:
            continue
        seen.add(key)
        rect = pymupdf.Rect(area_left, pl.row_top, area_left + area_width, pl.row_top + pl.row_height)
        if pl.role == "head":
            page.draw_rect(rect, color=None, fill=hex_rgb(t.table_header_bg), overlay=True)
        elif pl.role == "total":
            page.draw_rect(rect, color=None, fill=hex_rgb(t.zebra), overlay=True)
            page.draw_line(pymupdf.Point(area_left, pl.row_top),
                           pymupdf.Point(area_left + area_width, pl.row_top),
                           color=hex_rgb(t.border), width=0.7)
        elif pl.role == "body" and pl.row_index >= 0 and pl.row_index % 2 == 1:
            page.draw_rect(rect, color=None, fill=hex_rgb(t.zebra), overlay=True)


def _draw_placement(page: "pymupdf.Page", pl: FlowPlacement, registry: FontRegistry) -> None:
    if not pl.lines:
        return
    face = registry.resolve(pl.font, bold=pl.bold, italic=pl.italic)
    name = registry.register(page, face)
    color = hex_rgb(pl.color)
    for i, line in enumerate(pl.lines):
        if not line:
            continue
        safe = face.sanitize(line)
        y = pl.y + i * (pl.pitch or pl.size * 1.2)
        width = face.text_length(safe, pl.size)
        if pl.align == "center":
            x = pl.x + max(0.0, (pl.width - width) / 2.0)
        elif pl.align == "right":
            x = pl.x + max(0.0, pl.width - width)
        else:
            x = pl.x
        page.insert_text((x, y), safe, fontname=name, fontsize=pl.size, color=hex_rgb(pl.color))


def render_pdf_document(design: Design, blocks: list[FlowBlock], registry: FontRegistry,
                        ctx: PaintContext) -> RenderResult:
    """Lay out `blocks` over `design` and return the finished PDF."""
    styles = design.styles(registry)
    area = design.content_area
    layout = flow_document(blocks, styles, area, registry)

    by_page: dict[int, list[FlowPlacement]] = {}
    for pl in layout.placements:
        by_page.setdefault(pl.page, []).append(pl)

    doc = pymupdf.open()
    for page_number in range(1, layout.page_count + 1):
        page = doc.new_page(width=area.width, height=area.height)
        ctx.page_number = page_number
        ctx.page_count = layout.page_count
        if design.kind == "reference" and design.background_pdf:
            _blit_reference(page, design.background_pdf)
        else:
            paint_design(page, design, ctx, registry)
        placements = by_page.get(page_number, [])
        _draw_table_furniture(
            page, placements, design, area.left, area.column_width,
            cell_padding_x=styles.cell_padding_x,
        )
        for pl in placements:
            _draw_placement(page, pl, registry)

    data = doc.tobytes(deflate=True, garbage=3)
    doc.close()
    return RenderResult(pdf_bytes=data, page_count=layout.page_count, warnings=list(layout.warnings))


def render_previews(pdf_bytes: bytes, *, dpi: int = 110, max_pages: int = 12) -> list[bytes]:
    """Rasterise the first pages of a PDF to PNG for the in-app preview."""
    images: list[bytes] = []
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        for index in range(min(doc.page_count, max_pages)):
            pix = doc.load_page(index).get_pixmap(dpi=dpi)
            images.append(pix.tobytes("png"))
    finally:
        doc.close()
    return images
