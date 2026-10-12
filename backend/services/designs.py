"""Curated document designs.

A design owns three things: the colours and type the rendered PDF uses, the
rectangle new content flows into, and the letterhead and footer painted on every
sheet. Keeping those together means a design is genuinely different from another
one, not a colour swap.

Curated designs are drawn from scratch with PyMuPDF. Reference designs (an
uploaded PDF) are handled by :mod:`services.reference`, which reuses the
uploaded page as the background; both paths produce the same
:class:`services.flow.StyleSet` and :class:`services.flow.ContentArea` so the
layout engine needs no special case.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pymupdf

from services.fonts import FontRegistry
from services.flow import ContentArea, Style, StyleSet

# US Letter, in points, matching the reference masters.
PAGE_W = 612.0
PAGE_H = 792.0

MARGIN_X = 56.0
MARGIN_TOP = 78.0
MARGIN_BOTTOM = 70.0


def hex_rgb(value: str) -> tuple[float, float, float]:
    value = (value or "#000000").lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    try:
        r, g, b = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, IndexError):
        r = g = b = 0
    return (r / 255.0, g / 255.0, b / 255.0)


@dataclass
class DesignTokens:
    primary: str = "#1A1A1A"
    accent: str = "#C6A15B"
    text: str = "#1B1B1B"
    muted: str = "#6B6B6B"
    border: str = "#D9D4C7"
    page_bg: str = "#FFFFFF"
    header_bg: str = "#1A1A1A"
    header_text: str = "#F5F3EE"
    table_header_bg: str = "#1A1A1A"
    table_header_text: str = "#F5F3EE"
    zebra: str = "#F6F4EF"


@dataclass
class Design:
    id: str
    name: str
    description: str
    kind: str = "curated"
    tokens: DesignTokens = field(default_factory=DesignTokens)
    font_body: str = "Arial"
    font_heading: str = "Arial"
    body_size: float = 10.5
    title_size: float | None = None
    heading_size: float | None = None
    subheading_size: float | None = None
    subsubheading_size: float | None = None
    table_header_size: float | None = None
    #: Heading sizes as multipliers of the body size, so a design scales as one
    #: unit and a reference master's hierarchy is rebuilt from its own body size.
    title_scale: float = 1.9
    heading_scale: float = 1.36
    subheading_scale: float = 1.2
    subsubheading_scale: float = 1.08
    title_bold: bool = True
    heading_bold: bool = True
    table_header_bold: bool = True
    heading_align: str = "left"
    title_align: str = "center"
    header_style: str = "band"  # band | rule | centered | bar | none
    header_height: float = 58.0
    accent_rule: bool = True
    display_footer: bool = True
    #: Optional PDF to use as the page background (reference designs only).
    background_pdf: bytes | None = None
    reference_of: str = ""
    #: Optional margin overrides (used to honour an analysed reference layout).
    margin_left: float | None = None
    margin_right: float | None = None
    margin_bottom: float | None = None
    margin_top: float | None = None
    page_width: float = PAGE_W
    page_height: float = PAGE_H

    @property
    def content_area(self) -> ContentArea:
        left = MARGIN_X if self.margin_left is None else self.margin_left
        right = (self.page_width - MARGIN_X) if self.margin_right is None else (self.page_width - self.margin_right)
        bottom = (self.page_height - MARGIN_BOTTOM) if self.margin_bottom is None else (self.page_height - self.margin_bottom)
        top = self.margin_top or (
            MARGIN_TOP + (self.header_height if self.header_style != "none" else 0.0)
        )
        return ContentArea(
            width=self.page_width, height=self.page_height,
            left=left, top=top, right=right, bottom=bottom,
        )

    def styles(self, registry: FontRegistry) -> StyleSet:
        t = self.tokens
        reference = self.kind == "reference"
        title_size = self.title_size or self.body_size * self.title_scale
        heading_size = self.heading_size or self.body_size * self.heading_scale
        subheading_size = self.subheading_size or self.body_size * self.subheading_scale
        subsubheading_size = self.subsubheading_size or self.body_size * self.subsubheading_scale
        table_header_size = self.table_header_size or (
            self.body_size if reference else self.body_size * 0.98
        )
        return StyleSet(
            title=Style(font=self.font_heading, size=title_size, bold=self.title_bold,
                        color=t.primary, align=self.title_align, leading=1.18),
            subtitle=Style(font=self.font_body, size=self.body_size if reference else self.body_size * 1.05,
                           color=t.muted, align=self.title_align, leading=1.25),
            heading=Style(font=self.font_heading, size=heading_size, bold=self.heading_bold,
                          color=t.primary, align=self.heading_align, leading=1.2),
            subheading=Style(font=self.font_heading, size=subheading_size, bold=self.heading_bold,
                             color=t.primary, align=self.heading_align, leading=1.22),
            subsubheading=Style(font=self.font_heading, size=subsubheading_size,
                                bold=self.heading_bold, color=t.primary,
                                align=self.heading_align, leading=1.24),
            body=Style(font=self.font_body, size=self.body_size, color=t.text, leading=1.36),
            list_item=Style(font=self.font_body, size=self.body_size, color=t.text, leading=1.34),
            table_header=Style(font=self.font_heading, size=table_header_size,
                               bold=self.table_header_bold,
                               color=t.table_header_text, leading=1.2),
            table_cell=Style(font=self.font_body,
                             size=self.body_size if reference else self.body_size * 0.98,
                             color=t.text, leading=1.28),
            total=Style(font=self.font_heading,
                        size=self.body_size if reference else self.body_size * 1.02,
                        bold=self.heading_bold,
                        color=t.primary, leading=1.25),
            signature=Style(font=self.font_body, size=self.body_size, color=t.text, leading=1.36),
            contact=Style(font=self.font_body,
                          size=self.body_size if reference else self.body_size * 0.96,
                          color=t.muted, leading=1.3),
            provider=Style(font=self.font_body, size=self.body_size, bold=True,
                           color=t.text, leading=1.36),
            bullet_text="\u2022",
            bullet_gap=3.0 if not reference else 0.0,
            cell_padding_x=5.0,
            cell_padding_y=3.5 if not reference else 2.5,
            row_gap=2.0 if not reference else 0.0,
            column_ratios=[3.0, 1.0],
            row_rule=0.0,
        )


# -- the curated set ---------------------------------------------------------


def _clean_corporate() -> Design:
    return Design(
        id="clean_corporate",
        name="Clean corporate",
        description="Navy and steel, a single rule under the letterhead, tight professional type.",
        tokens=DesignTokens(
            primary="#1F2A44", accent="#2E6F9E", text="#22272E", muted="#6B7480",
            border="#D7DCE3", header_bg="#FFFFFF", header_text="#1F2A44",
            table_header_bg="#1F2A44", table_header_text="#FFFFFF", zebra="#F4F6F9",
        ),
        font_body="Arial", font_heading="Arial", title_align="left",
        heading_align="left", header_style="rule", header_height=56.0,
    )


def _premium_business() -> Design:
    return Design(
        id="premium_business",
        name="Premium business",
        description="Dark letterhead band with a fine gold rule, serif headings, generous spacing.",
        tokens=DesignTokens(
            primary="#1A1A1A", accent="#C6A15B", text="#1B1B1B", muted="#6B6B6B",
            border="#DCD6C8", header_bg="#1A1A1A", header_text="#F5F3EE",
            table_header_bg="#1A1A1A", table_header_text="#F5F3EE", zebra="#F7F5F0",
        ),
        font_body="Segoe UI", font_heading="Georgia", title_align="center",
        heading_align="left", header_style="band", header_height=64.0,
    )


def _formal_proposal() -> Design:
    return Design(
        id="formal_proposal",
        name="Formal proposal",
        description="Centred Times letterhead between double rules, restrained and traditional.",
        tokens=DesignTokens(
            primary="#14213D", accent="#9A7B4F", text="#1B1B1B", muted="#555B63",
            border="#C9C2B6", header_bg="#FFFFFF", header_text="#14213D",
            table_header_bg="#14213D", table_header_text="#FFFFFF", zebra="#F6F4EF",
        ),
        font_body="Times New Roman", font_heading="Times New Roman",
        title_align="center", heading_align="left", header_style="centered",
        header_height=62.0,
    )


def _branded_service(profile_primary: str = "#111111", accent: str = "#C6A15B") -> Design:
    return Design(
        id="branded_service",
        name="Branded service quotation",
        description="Your brand colours as a bold side bar with heavy headings and ruled rows.",
        tokens=DesignTokens(
            primary="#111111", accent=accent, text="#1B1B1B", muted="#646464",
            border="#E2DDD2", header_bg="#111111", header_text="#F5F3EE",
            table_header_bg="#111111", table_header_text="#F5F3EE", zebra="#F8F6F1",
        ),
        font_body="Arial", font_heading="Arial", title_align="left",
        heading_align="left", header_style="bar", header_height=60.0, accent_rule=True,
    )


CURATED_BUILDERS = {
    "clean_corporate": _clean_corporate,
    "premium_business": _premium_business,
    "formal_proposal": _formal_proposal,
    "branded_service": _branded_service,
}

DEFAULT_DESIGN = "premium_business"


def get_design(design_id: str) -> Design:
    builder = CURATED_BUILDERS.get(design_id) or CURATED_BUILDERS[DEFAULT_DESIGN]
    return builder()


def list_designs() -> list[Design]:
    return [builder() for builder in CURATED_BUILDERS.values()]


def to_design_info(design: Design):
    """Serialise a design for the API without leaking renderer-only fields."""
    from models import DesignInfo, DesignTokens as ModelTokens

    t = design.tokens
    return DesignInfo(
        id=design.id,
        name=design.name,
        description=design.description,
        kind=design.kind,
        tokens=ModelTokens(
            primary=t.primary, accent=t.accent, text=t.text, muted=t.muted,
            border=t.border, page_bg=t.page_bg, header_bg=t.header_bg,
            header_text=t.header_text, table_header_bg=t.table_header_bg,
            table_header_text=t.table_header_text, zebra=t.zebra,
        ),
        font_body=design.font_body,
        font_heading=design.font_heading,
        accent_rule=design.accent_rule,
        reference_of=design.reference_of,
    )


# -- painting ----------------------------------------------------------------


@dataclass
class PaintContext:
    profile_name: str = ""
    profile_contact: list[str] = field(default_factory=list)
    logo_bytes: bytes | None = None
    doc_title: str = "QUOTATION"
    doc_number: str = ""
    page_number: int = 1
    page_count: int = 1
    side_label: str = "QUOTATION"


def _draw_text(page, x, y, text, fontname, size, color, *, bold=False, align="left",
               registry=None, family="Arial", max_width=None):
    if not text:
        return
    face = registry.resolve(family, bold=bold) if registry else None
    name = registry.register(page, face) if (registry and face) else ("hebo" if bold else "helv")
    text = face.sanitize(text) if face else text
    page.insert_text((x, y), text, fontname=name, fontsize=size,
                     color=hex_rgb(color), render_mode=0)


def paint_design(page: "pymupdf.Page", design: Design, ctx: PaintContext,
                 registry: FontRegistry) -> None:
    """Paint the letterhead and footer for one sheet of a curated design."""
    t = design.tokens
    # Page background.
    page.draw_rect(pymupdf.Rect(0, 0, PAGE_W, PAGE_H), color=None,
                   fill=hex_rgb(t.page_bg), overlay=True)

    name = ctx.profile_name or "Your company"
    contact_line = "  |  ".join(c for c in ctx.profile_contact if c)

    style = design.header_style
    if style == "band":
        page.draw_rect(pymupdf.Rect(0, 0, PAGE_W, design.header_height), color=None,
                       fill=hex_rgb(t.header_bg), overlay=True)
        _draw_text(page, MARGIN_X, 30, name, None, 16, t.header_text, bold=True,
                   registry=registry, family=design.font_heading)
        if contact_line:
            _draw_text(page, MARGIN_X, 45, contact_line, None, 8.5, t.header_text,
                       registry=registry, family=design.font_body)
        _draw_text(page, PAGE_W - MARGIN_X - _text_w(ctx.doc_title, registry, design, 10, True),
                   30, ctx.doc_title.upper(), None, 10, t.accent, bold=True,
                   registry=registry, family=design.font_heading)
        page.draw_rect(pymupdf.Rect(0, design.header_height - 2.5, PAGE_W, design.header_height),
                       color=None, fill=hex_rgb(t.accent), overlay=True)
    elif style == "rule":
        _draw_text(page, MARGIN_X, 34, name, None, 17, t.header_text, bold=True,
                   registry=registry, family=design.font_heading)
        if contact_line:
            _draw_text(page, MARGIN_X, 48, contact_line, None, 8, t.muted,
                       registry=registry, family=design.font_body)
        tw = _text_w(ctx.side_label, registry, design, 11, True)
        _draw_text(page, PAGE_W - MARGIN_X - tw, 34, ctx.side_label.upper(), None, 11,
                   t.accent, bold=True, registry=registry, family=design.font_heading)
        page.draw_rect(pymupdf.Rect(MARGIN_X, design.header_height, PAGE_W - MARGIN_X,
                                    design.header_height + 1.4),
                       color=None, fill=hex_rgb(t.primary), overlay=True)
    elif style == "centered":
        _draw_text(page, PAGE_W / 2 - _text_w(name, registry, design, 17, True) / 2, 32,
                   name, None, 17, t.header_text, bold=True, registry=registry,
                   family=design.font_heading)
        if contact_line:
            _draw_text(page, PAGE_W / 2 - _text_w(contact_line, registry, design, 8, False) / 2, 46,
                       contact_line, None, 8, t.muted, registry=registry, family=design.font_body)
        page.draw_rect(pymupdf.Rect(MARGIN_X, design.header_height, PAGE_W - MARGIN_X,
                                    design.header_height + 1.6),
                       color=None, fill=hex_rgb(t.primary), overlay=True)
        page.draw_rect(pymupdf.Rect(MARGIN_X, design.header_height + 3.4, PAGE_W - MARGIN_X,
                                    design.header_height + 4.2),
                       color=None, fill=hex_rgb(t.accent), overlay=True)
    elif style == "bar":
        page.draw_rect(pymupdf.Rect(0, 0, 12, PAGE_H), color=None,
                       fill=hex_rgb(t.primary), overlay=True)
        page.draw_rect(pymupdf.Rect(12, 0, 15, PAGE_H), color=None,
                       fill=hex_rgb(t.accent), overlay=True)
        _draw_text(page, MARGIN_X, 34, name, None, 18, t.primary, bold=True,
                   registry=registry, family=design.font_heading)
        if contact_line:
            _draw_text(page, MARGIN_X, 48, contact_line, None, 8, t.muted,
                       registry=registry, family=design.font_body)
        tw = _text_w(ctx.side_label.upper(), registry, design, 11, True)
        _draw_text(page, PAGE_W - MARGIN_X - tw, 34, ctx.side_label.upper(), None, 11,
                   t.accent, bold=True, registry=registry, family=design.font_heading)

    # Logo, when the provider uploaded one.
    if ctx.logo_bytes:
        try:
            rect = pymupdf.Rect(PAGE_W - MARGIN_X - 90, 12, PAGE_W - MARGIN_X, 44)
            page.insert_image(rect, stream=ctx.logo_bytes, keep_proportion=True)
        except Exception:
            pass

    # Footer.
    if design.display_footer:
        page.draw_rect(pymupdf.Rect(MARGIN_X, PAGE_H - MARGIN_BOTTOM + 16, PAGE_W - MARGIN_X,
                                    PAGE_H - MARGIN_BOTTOM + 16.6),
                       color=None, fill=hex_rgb(t.border), overlay=True)
        _draw_text(page, MARGIN_X, PAGE_H - MARGIN_BOTTOM + 30,
                   (ctx.profile_name or "Generated with quoteGEN"), None, 8, t.muted,
                   registry=registry, family=design.font_body)
        label = f"Page {ctx.page_number} of {ctx.page_count}"
        _draw_text(page, PAGE_W - MARGIN_X - _text_w(label, registry, design, 8, False),
                   PAGE_H - MARGIN_BOTTOM + 30, label, None, 8, t.muted,
                   registry=registry, family=design.font_body)


def _text_w(text: str, registry: FontRegistry, design: Design, size: float, bold: bool) -> float:
    face = registry.resolve(design.font_heading if bold else design.font_body, bold=bold)
    return face.text_length(text or "", size)
