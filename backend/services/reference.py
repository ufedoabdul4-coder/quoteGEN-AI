"""Turn an uploaded reference document into a reusable design.

The brief is explicit: a reference tells us *how* the provider's documents look,
never what they say. So we read the reference's structure — page size, margins,
type family and size, colour hierarchy and header treatment — and rebuild a
clean letterhead in that style around the *user's own* business details. We
never copy the reference's wording, its client or its prices, so an uploaded
document can never leak another business's content into a new quotation.
"""

from __future__ import annotations

import logging
import statistics

import pymupdf

from services.designs import Design, DesignTokens, PAGE_H, PAGE_W

logger = logging.getLogger(__name__)

_FAMILY_HINTS = (
    ("times", "Times New Roman"),
    ("georgia", "Georgia"),
    ("garamond", "Georgia"),
    ("cambria", "Georgia"),
    ("book", "Georgia"),
    ("arial", "Arial"),
    ("helvetica", "Arial"),
    ("roboto", "Arial"),
    ("calibri", "Segoe UI"),
    ("segoe", "Segoe UI"),
    ("courier", "Courier New"),
)

_DARK = 0.5
_WHITEISH = 0.9


def _family_of(name: str) -> str:
    lowered = (name or "").lower()
    for hint, family in _FAMILY_HINTS:
        if hint in lowered:
            return family
    return "Arial"


def _hex_of(color: int) -> str:
    color = int(color) & 0xFFFFFF
    return f"#{color >> 16 & 0xFF:02X}{color >> 8 & 0xFF:02X}{color & 0xFF:02X}"


def _luminance(color: int) -> float:
    color = int(color) & 0xFFFFFF
    r, g, b = (color >> 16 & 0xFF) / 255, (color >> 8 & 0xFF) / 255, (color & 0xFF) / 255
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _dominant(values, *, dark: bool = False, exclude_white: bool = True) -> int | None:
    filtered = []
    for value in values:
        if exclude_white and _luminance(value) > _WHITEISH:
            continue
        if dark and _luminance(value) > _DARK:
            continue
        filtered.append(int(value))
    if not filtered:
        return None
    try:
        return statistics.mode(filtered)
    except statistics.StatisticsError:
        return filtered[0]


def count_pages(pdf_bytes: bytes) -> int:
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        return 0
    try:
        return int(doc.page_count)
    finally:
        doc.close()


def analyze_reference(pdf_bytes: bytes, *, name: str = "Reference design",
                      reference_of: str = "") -> Design:
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        page = doc.load_page(0)
        page_w, page_h = page.rect.width, page.rect.height
        spans = _collect_spans(page)
        drawings = _collect_drawings(page)
        all_spans = [span for item in doc for span in _collect_spans(item)]
        all_drawings = [drawing for item in doc for drawing in _collect_drawings(item)]

        body_spans = [span for span in all_spans if not span["bold"]]
        heading_spans = [span for span in all_spans if span["bold"]]
        body_family = _mode([span["family"] for span in body_spans]) or "Arial"
        heading_family = _mode([span["family"] for span in heading_spans]) or body_family

        body_sizes = [span["size"] for span in body_spans if 7.5 <= span["size"] <= 16]
        heading_sizes = [span["size"] for span in heading_spans if 7.5 <= span["size"] <= 16]
        body_size = _clamp(
            statistics.median(body_sizes or heading_sizes) if body_sizes or heading_sizes else 10.5,
            9.0,
            12.5,
        )
        heading_size = _clamp(
            statistics.median(heading_sizes) if heading_sizes else body_size,
            9.0,
            16.0,
        )
        title_y = min((span["bbox"][1] for span in spans), default=0.0)
        title_spans = [span for span in spans if abs(span["bbox"][1] - title_y) < 1.0]
        title_size = statistics.median([span["size"] for span in title_spans]) if title_spans else heading_size

        body_colors = [s["color"] for s in body_spans]
        primary = _dominant(body_colors, dark=True)
        if primary is None:
            primary = _dominant([s["color"] for s in all_spans], dark=True)
        if primary is None:
            primary = 0x1B1B1B

        fill_colors = [d["color"] for d in all_drawings if d["kind"] == "fill"]
        accent = _dominant([s["color"] for s in all_spans if s["color"] != primary])
        if accent is None:
            accent = _dominant(fill_colors)
        if accent is None:
            accent = primary

        header_style = _header_style(drawings, spans, body_size, page_w, page_h)
        header_height = _header_height(spans, body_size)
        margin_top = _clamp(header_height + 78, 90, page_h * 0.3)
        margin_bottom = _clamp(page_h - _max_bottom(spans) - 24, 40, 96)
        if _has_full_page_image(page):
            body_spans = [
                span for span in spans
                if span["bbox"][1] >= max(60.0, margin_top - 24.0)
                and span["bbox"][3] < page_h * 0.82
            ]
            if body_spans:
                margin_top = _clamp(
                    min(span["bbox"][1] for span in body_spans) + 15.0,
                    90,
                    page_h * 0.55,
                )
                body_bottom = max(span["bbox"][3] for span in body_spans) + 16.0
                footer_top = page_h - max(96.0, page_h * 0.15)
                content_bottom = min(body_bottom, footer_top)
                margin_bottom = page_h - content_bottom

        text_hex = _hex_of(primary)
        tokens = DesignTokens(
            primary=text_hex,
            accent=_hex_of(accent),
            text=text_hex,
            muted=text_hex,
            border="#D9D4C7",
            page_bg="#FFFFFF",
            header_bg="#FFFFFF",
            header_text=text_hex,
            table_header_bg="#FFFFFF",
            table_header_text=text_hex,
            zebra="#FFFFFF",
        )

        return Design(
            id="reference",
            name=name,
            description="Rebuilt from an uploaded reference document.",
            kind="reference",
            tokens=tokens,
            font_body=body_family,
            font_heading=heading_family,
            body_size=body_size,
            title_size=title_size,
            heading_size=heading_size,
            table_header_size=heading_size,
            title_bold=any(span["bold"] for span in title_spans),
            heading_bold=bool(heading_spans),
            table_header_bold=bool(heading_spans),
            title_align=_title_alignment(spans, page_w),
            heading_align="left",
            header_style=header_style,
            header_height=header_height,
            reference_of=reference_of,
            margin_left=_clamp(_min_left(spans) - 6, 24, 90),
            margin_right=_clamp(page_w - _max_right(spans) - 6, 24, 90),
            margin_bottom=margin_bottom,
            margin_top=margin_top,
            page_width=page_w,
            page_height=page_h,
        )
    finally:
        doc.close()


def prepare_template_background(
    pdf_bytes: bytes, *, content_top: float, content_bottom: float,
) -> bytes:
    """Return ONE cleaned design sheet reused as the background of every page.

    The master's header/footer artwork is a full-page raster and must survive
    untouched, so a single clean page is copied and only its *text* and its old
    *body-area vector rules* are removed. Redactions never paint a fill, images
    are never re-encoded or re-sampled, and the footer strip is never touched.
    """
    source_doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        index = pick_design_page(source_doc)
        source = source_doc[index]
        footer_top = _raster_footer_top(source)
        cleanup_bottom = min(
            footer_top if footer_top is not None else content_bottom,
            source.rect.height,
        )

        text_redactions: list[pymupdf.Rect] = []
        for span in _collect_spans(source):
            rect = pymupdf.Rect(span["bbox"])
            padded = rect + (-0.9, -0.9, 0.9, 0.9)
            padded.y1 = min(padded.y1, cleanup_bottom)
            if padded.y1 > padded.y0:
                text_redactions.append(padded)
        band_top = min(content_top, cleanup_bottom)
        band_rect = pymupdf.Rect(0, band_top, source.rect.width, cleanup_bottom)
        drawing_redactions = _body_drawing_rects(source, band_rect, cleanup_bottom)

        out = pymupdf.open()
        try:
            out.insert_pdf(source_doc, from_page=index, to_page=index)
            page = out[0]
            image_state = _page_image_state(page)
            for rect in text_redactions:
                page.add_redact_annot(rect, fill=None, cross_out=False)
            if text_redactions:
                page.apply_redactions(
                    images=pymupdf.PDF_REDACT_IMAGE_NONE,
                    graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                    text=pymupdf.PDF_REDACT_TEXT_REMOVE,
                )
            for rect in drawing_redactions:
                page.add_redact_annot(rect, fill=None, cross_out=False)
            if drawing_redactions:
                try:
                    page.apply_redactions(
                        images=pymupdf.PDF_REDACT_IMAGE_NONE,
                        graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
                        text=pymupdf.PDF_REDACT_TEXT_REMOVE,
                    )
                except (TypeError, ValueError) as exc:
                    logger.warning(
                        "Design page could not remove covered line art; "
                        "leaving the vectors untouched: %s",
                        exc,
                    )
            image_state_unchanged = image_state == _page_image_state(page)
            if not image_state_unchanged:
                raise RuntimeError(
                    "Redaction changed the master image on the design page."
                )
            logger.debug(
                "Template design page=%d of %d text_spans=%d body_rules=%d "
                "footer_top=%s image_xref_bbox_unchanged=%s",
                index + 1, source_doc.page_count, len(text_redactions),
                len(drawing_redactions),
                round(footer_top, 2) if footer_top is not None else
                round(cleanup_bottom, 2),
                image_state_unchanged,
            )
            return out.tobytes(garbage=3, deflate=True)
        finally:
            out.close()
    finally:
        source_doc.close()


def pick_design_page(doc: "pymupdf.Document") -> int:
    """Pick the master page carrying the least own content as the design sheet."""
    best_index = 0
    best_count: int | None = None
    for index, page in enumerate(doc):
        count = len(_collect_spans(page))
        if best_count is None or count < best_count:
            best_count = count
            best_index = index
    return best_index


def _body_drawing_rects(
    page: "pymupdf.Page", band_rect: pymupdf.Rect, cleanup_bottom: float,
) -> list[pymupdf.Rect]:
    """Rects for the old body-area rules/table borders to delete (never footer)."""
    limit = pymupdf.Rect(0, 0, page.rect.width, cleanup_bottom)
    rects: list[pymupdf.Rect] = []
    for drawing in page.get_drawings():
        rect = drawing.get("rect")
        if rect is None:
            continue
        rect = pymupdf.Rect(rect)
        line_width = float(drawing.get("width") or 0.0)
        bounds = _expanded_drawing_bounds(rect, line_width)
        if not bounds.intersects(band_rect):
            continue
        fill = drawing.get("fill")
        stroke = drawing.get("color")
        is_dark = any(
            color is not None and max(color) < 0.1 for color in (fill, stroke)
        )
        is_body_rule = (
            rect.width <= 1.5
            or rect.height <= 1.5
            or (is_dark and rect.width < page.rect.width * 0.88
                and rect.height < page.rect.height * 0.25)
        )
        if not is_body_rule:
            continue
        clipped = bounds & limit
        if clipped.width > 0 and clipped.height > 0:
            rects.append(clipped)
    return _merge_rects(rects)


def _raster_footer_top(page: pymupdf.Page) -> float | None:
    """Find the start of a colored footer in a full-page raster master."""
    if not _has_full_page_image(page):
        return None

    pix = page.get_pixmap(matrix=pymupdf.Matrix(0.5, 0.5), alpha=False)
    samples = pix.samples
    channels = pix.n
    threshold = max(4, int(pix.width * 0.015))
    first_footer_row = int(pix.height * 0.72)
    colored_rows = []
    for y in range(first_footer_row, pix.height):
        offset = y * pix.width * channels
        colored = 0
        for x in range(pix.width):
            pixel = offset + x * channels
            red, green, blue = samples[pixel:pixel + 3]
            if max(red, green, blue) - min(red, green, blue) > 45 \
                    and max(red, green, blue) < 245:
                colored += 1
        colored_rows.append(colored >= threshold)

    for index in range(len(colored_rows) - 6):
        if sum(colored_rows[index:index + 7]) >= 3:
            points_per_pixel = page.rect.height / pix.height
            return max(0.0, (first_footer_row + index) * points_per_pixel)
    return None


def _body_line_bounds(page: pymupdf.Page, content_rect: pymupdf.Rect) -> list[tuple[float, ...]]:
    lines = []
    for drawing in page.get_drawings():
        rect = drawing.get("rect")
        if rect is None:
            continue
        rect = pymupdf.Rect(rect)
        rect = _expanded_drawing_bounds(rect, float(drawing.get("width") or 0.0))
        if rect.intersects(content_rect) and (rect.width <= 3 or rect.height <= 3):
            lines.append(tuple(round(value, 1) for value in rect))
    return lines


def _page_image_state(page: pymupdf.Page) -> tuple:
    return tuple(sorted(
        (
            image[0],
            tuple(
                tuple(round(value, 4) for value in rect)
                for rect in page.get_image_rects(image[0])
            ),
        )
        for image in page.get_images(full=True)
    ))


def _expanded_drawing_bounds(rect: pymupdf.Rect, line_width: float) -> pymupdf.Rect:
    padding = max(1.0, line_width + 0.2)
    return rect + (-padding, -padding, padding, padding)


def _rect_union(rects: list[pymupdf.Rect]) -> pymupdf.Rect | None:
    if not rects:
        return None
    return pymupdf.Rect(
        min(rect.x0 for rect in rects),
        min(rect.y0 for rect in rects),
        max(rect.x1 for rect in rects),
        max(rect.y1 for rect in rects),
    )


def _merge_rects(rects: list[pymupdf.Rect]) -> list[pymupdf.Rect]:
    pending = [pymupdf.Rect(rect) for rect in rects]
    merged = []
    while pending:
        candidate = pending.pop()
        changed = True
        while changed:
            changed = False
            for index, other in enumerate(pending):
                if (candidate + (-1.0, -1.0, 1.0, 1.0)).intersects(
                    other + (-1.0, -1.0, 1.0, 1.0)
                ):
                    candidate = pymupdf.Rect(
                        min(candidate.x0, other.x0), min(candidate.y0, other.y0),
                        max(candidate.x1, other.x1), max(candidate.y1, other.y1),
                    )
                    pending.pop(index)
                    changed = True
                    break
        merged.append(candidate)
    return merged


def old_master_wording_present(
    master_pdf: bytes, output_pdf: bytes, supplied_text: str = "",
) -> bool:
    """Check for master text not also present in the supplied quotation content."""
    master = pymupdf.open(stream=master_pdf, filetype="pdf")
    output = pymupdf.open(stream=output_pdf, filetype="pdf")
    try:
        output_text = " ".join(output[i].get_text() for i in range(output.page_count))
        output_text = " ".join(output_text.split()).casefold()
        supplied_text = " ".join(supplied_text.split()).casefold()
        for page in master:
            for span in _collect_spans(page):
                wording = " ".join(span["text"].split()).casefold()
                if (len(wording) >= 18 and wording in output_text
                        and wording not in supplied_text):
                    return True
        return False
    finally:
        master.close()
        output.close()


def background_image_matches(master_pdf: bytes, output_pdf: bytes) -> bool:
    """Check that every rendered page still carries the master's original raster."""
    import hashlib

    master = pymupdf.open(stream=master_pdf, filetype="pdf")
    output = pymupdf.open(stream=output_pdf, filetype="pdf")
    try:
        master_images = master[0].get_images(full=True)
        if not master_images:
            return False
        expected = {
            hashlib.sha256(master.extract_image(image[0])["image"]).digest()
            for image in master_images
        }
        for page in output:
            actual = {
                hashlib.sha256(output.extract_image(image[0])["image"]).digest()
                for image in page.get_images(full=True)
            }
            if not expected.intersection(actual):
                return False
        return True
    finally:
        master.close()
        output.close()


# -- extraction --------------------------------------------------------------


def _collect_spans(page) -> list[dict]:
    spans: list[dict] = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if not (span.get("text") or "").strip():
                    continue
                spans.append({
                    "text": span.get("text", ""),
                    "font": span.get("font", ""),
                    "family": _family_of(span.get("font", "")),
                    "size": float(span.get("size", 10.0)),
                    "bold": "bold" in span.get("font", "").lower(),
                    "color": int(span.get("color", 0)),
                    "bbox": span.get("bbox", (0, 0, 0, 0)),
                })
    return spans


def _collect_drawings(page) -> list[dict]:
    items: list[dict] = []
    try:
        raw = page.get_drawings()
    except Exception:
        return items
    for drawing in raw:
        rect = drawing.get("rect")
        if rect is None:
            continue
        if drawing.get("fill") is not None:
            items.append({"kind": "fill", "color": _rgb_int(drawing["fill"]), "rect": rect})
        if drawing.get("color") is not None and rect.height < 3:
            items.append({"kind": "rule", "color": _rgb_int(drawing["color"]), "rect": rect})
    return items


def _has_full_page_image(page) -> bool:
    page_area = page.rect.get_area()
    for image in page.get_images(full=True):
        for rect in page.get_image_rects(image[0]):
            if (rect & page.rect).get_area() >= page_area * 0.8:
                return True
    return False


def _rgb_int(seq) -> int:
    r, g, b = (seq + (0, 0, 0))[:3]
    return (int(round(r * 255)) << 16) | (int(round(g * 255)) << 8) | int(round(b * 255))


# -- heuristics --------------------------------------------------------------


def _mode(values):
    if not values:
        return None
    try:
        return statistics.mode(list(values))
    except statistics.StatisticsError:
        return values[0]


def _lighten(color: int) -> int:
    color = int(color) & 0xFFFFFF
    r = int(_clamp((color >> 16 & 0xFF) + 70, 0, 255))
    g = int(_clamp((color >> 8 & 0xFF) + 70, 0, 255))
    b = int(_clamp((color & 0xFF) + 70, 0, 255))
    return r << 16 | g << 8 | b


def _header_height(spans, body_size: float) -> float:
    if not spans:
        return 50.0
    top = min(s["bbox"][1] for s in spans)
    cluster_bottom = max((s["bbox"][3] for s in spans if s["bbox"][1] <= top + body_size * 3.2),
                         default=top + body_size)
    height = (cluster_bottom - top) + 16
    return _clamp(height, 44, 78)


def _header_style(drawings, spans, body_size: float, page_w: float, page_h: float) -> str:
    for item in drawings:
        rect = item["rect"]
        if item["kind"] == "fill" and rect.width > page_w * 0.6 and 24 < rect.height < page_h * 0.25:
            if rect.y0 < page_h * 0.3 and _luminance(item["color"]) <= _DARK:
                return "band"
    for item in drawings:
        rect = item["rect"]
        if item["kind"] in ("fill", "rule") and rect.width > page_w * 0.55 and rect.height <= 4:
            if rect.y0 < page_h * 0.35:
                return "rule"
    if spans:
        top_spans = [s for s in spans if s["bbox"][1] < page_h * 0.18]
        if top_spans:
            centers = [(s["bbox"][0] + s["bbox"][2]) / 2 for s in top_spans]
            if abs(statistics.median(centers) - page_w / 2) < page_w * 0.08:
                return "centered"
    return "rule"


def _title_alignment(spans, page_w: float) -> str:
    if not spans:
        return "left"
    top = min(span["bbox"][1] for span in spans)
    title_spans = [span for span in spans if abs(span["bbox"][1] - top) < 1.0]
    centers = [(span["bbox"][0] + span["bbox"][2]) / 2.0 for span in title_spans]
    return "center" if centers and abs(statistics.median(centers) - page_w / 2) < page_w * 0.08 else "left"


def _min_left(spans) -> float:
    return min((s["bbox"][0] for s in spans), default=60.0)


def _max_right(spans) -> float:
    return max((s["bbox"][2] for s in spans), default=550.0)


def _max_bottom(spans) -> float:
    return max((s["bbox"][3] for s in spans), default=760.0)
