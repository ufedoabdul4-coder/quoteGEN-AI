"""Shared document schema for quoteGEN.

The frontend, the AI understanding stage, the deterministic financial checker,
the layout engine and the PDF renderer all agree on the shapes declared here.
Nothing downstream re-infers a block's type: the type is decided once, when the
document is understood, and carried as data from then on.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# semantic vocabulary
# ---------------------------------------------------------------------------
#
# The names below are the single vocabulary the whole pipeline speaks. The
# understanding stage may only emit one of these; anything else is refused and
# reported rather than silently rendered as a paragraph.
#
# This is mirrored in services/classify.py, which is the module that actually
# decides a type. The tuple is exported so tests can assert the two agree.

SEMANTIC_TYPES: tuple[str, ...] = (
    "document_title",
    "subtitle",
    "provider_name",
    "provider_contact",
    "client_name",
    "client_address",
    "service_address",
    "quotation_number",
    "quotation_date",
    "validity_period",
    "introduction",
    "heading",
    "major_section_heading",
    "subsection_heading",
    "paragraph",
    "bullet_list",
    "numbered_list",
    "scope_item",
    "table_header",
    "table_row",
    "cost_description",
    "cost_amount",
    "subtotal",
    "grand_total",
    "amount_in_words",
    "equipment_item",
    "material_item",
    "safety_item",
    "duration",
    "term",
    "signature",
    "client_acceptance",
    "contact_information",
)

#: Types that carry money. Kept explicit so the financial checker and the layout
#: engine never disagree about what has to add up.
FINANCIAL_TYPES: tuple[str, ...] = ("cost_amount", "subtotal", "grand_total")


class SemanticBlock(BaseModel):
    """One classified piece of the document, in the order the provider wrote it."""

    id: str = ""
    type: str
    text: str = ""
    #: Heading depth (1 = major section, 2 = subsection) or list nesting.
    level: int = 1
    #: Child lines of a list / contact block.
    items: List[str] = Field(default_factory=list)
    #: Numeric value for a financial block, when one could be proven.
    value: Optional[float] = None
    #: The figure exactly as the provider wrote it (currency symbol, separators).
    figure: Optional[str] = None
    #: Grouping key: a table and its rows share one; a list keeps its own.
    group: str = ""
    order: int = 0
    #: Free-form detail (column index, source path) that never decides a type.
    meta: Dict[str, Any] = Field(default_factory=dict)


class FinancialRow(BaseModel):
    description: str = ""
    amount: Optional[float] = None
    figure: str = ""
    group: str = ""


class FinancialSummary(BaseModel):
    currency: str = ""
    subtotal: Optional[float] = None
    tax_amount: float = 0.0
    discount_amount: float = 0.0
    grand_total: Optional[float] = None
    deposit_percent: Optional[float] = None
    deposit_amount: Optional[float] = None
    balance_amount: Optional[float] = None
    #: Sum of the priced rows the provider actually wrote.
    rows_total: Optional[float] = None
    #: What the provider said the total was, if they said.
    stated_total: Optional[float] = None
    #: rows_total - stated_total. Non-zero means the quote does not add up.
    difference: Optional[float] = None
    consistent: bool = True
    note: str = ""


class Understanding(BaseModel):
    """What was understood about a document, and what could not be trusted."""

    title: str = ""
    subtitle: str = ""
    blocks: List[SemanticBlock] = Field(default_factory=list)
    financials: FinancialSummary = Field(default_factory=FinancialSummary)
    #: Figures dropped because the provider's own text does not contain them.
    unverified_amounts: List[str] = Field(default_factory=list)
    #: Types outside the vocabulary that were refused.
    unknown_types: List[str] = Field(default_factory=list)
    #: Ordering contradictions that were recorded rather than corrected.
    ordering_problems: List[str] = Field(default_factory=list)
    #: Missing information spotted without inventing it.
    missing: List[str] = Field(default_factory=list)
    blocks_seen: int = 0
    source_kind: str = ""
    failed: bool = False
    failure_reason: str = ""
    #: Human-readable notes raised while understanding (e.g. financial mismatches).
    notes: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# output validation report
# ---------------------------------------------------------------------------


class ValidationFinding(BaseModel):
    level: str = "info"  # info | warning | error
    code: str = ""
    message: str = ""
    detail: List[str] = Field(default_factory=list)


class ValidationReport(BaseModel):
    ok: bool = True
    page_count: int = 0
    pricing_rows: int = 0
    computed_total: Optional[float] = None
    stated_total: Optional[float] = None
    blocks_built: int = 0
    blocks_mapped: int = 0
    blocks_rejected: int = 0
    stale_old_wording: List[str] = Field(default_factory=list)
    literal_markdown: List[str] = Field(default_factory=list)
    missing_blocks: List[str] = Field(default_factory=list)
    partial_blocks: List[str] = Field(default_factory=list)
    findings: List[ValidationFinding] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# designs
# ---------------------------------------------------------------------------


class DesignTokens(BaseModel):
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


class DesignInfo(BaseModel):
    id: str
    name: str
    description: str = ""
    kind: str = "curated"  # curated | reference
    tokens: DesignTokens = Field(default_factory=DesignTokens)
    font_body: str = "Helvetica"
    font_heading: str = "Helvetica"
    accent_rule: bool = True
    preview_url: Optional[str] = None
    reference_of: Optional[str] = None
    created_at: str = ""


class TemplateMeta(BaseModel):
    """A saved master template: the analysed design plus file information.

    A template is what an uploaded master document becomes once its structure has
    been read. The stored ``design`` holds only reusable styling — fonts, colours,
    margins, header treatment — never the source document's wording or prices.
    """

    id: str
    name: str = "Master template"
    source_filename: str = ""
    size_bytes: int = 0
    page_count: int = 0
    status: str = "ready"  # uploaded | analysing | ready | failed
    error: str = ""
    created_at: str = ""
    updated_at: str = ""
    is_active: bool = False
    design: DesignInfo = Field(default_factory=DesignInfo)
    kind: str = "template"


class Settings(BaseModel):
    active_template_id: Optional[str] = None


class TemplateRenameRequest(BaseModel):
    name: str


class ActiveTemplateRequest(BaseModel):
    template_id: Optional[str] = None


# ---------------------------------------------------------------------------
# client / provider
# ---------------------------------------------------------------------------


class ClientInfo(BaseModel):
    name: str = ""
    address: str = ""
    phone: str = ""
    email: str = ""
    contact_person: str = ""


class BusinessProfile(BaseModel):
    name: str = ""
    business_type: str = ""
    tagline: str = ""
    email: str = ""
    phone: str = ""
    website: str = ""
    address: str = ""
    registration: str = ""
    logo_data_url: str = ""
    brand_primary: str = "#1A1A1A"
    brand_accent: str = "#C6A15B"
    preferred_design_id: str = "premium_business"


# ---------------------------------------------------------------------------
# documents
# ---------------------------------------------------------------------------


class DocumentRecord(BaseModel):
    id: str
    title: str = "Untitled quotation"
    status: str = "draft"  # draft | needs_review | ready
    created_at: str = ""
    updated_at: str = ""
    design_id: str = "premium_business"
    input_kind: str = "describe"  # describe | paste | reference | job
    raw_input: str = ""
    job_missing_info: List[str] = Field(default_factory=list)
    client: ClientInfo = Field(default_factory=ClientInfo)
    profile: BusinessProfile = Field(default_factory=BusinessProfile)
    understanding: Understanding = Field(default_factory=Understanding)
    validation: Optional[ValidationReport] = None
    reference_id: Optional[str] = None
    pdf_url: Optional[str] = None
    preview_url: Optional[str] = None
    page_count: int = 0


# ---------------------------------------------------------------------------
# requests / responses
# ---------------------------------------------------------------------------


class UnderstandRequest(BaseModel):
    text: str = ""
    kind: str = "auto"  # auto | describe | paste
    model: Optional[str] = None
    profile: Optional[BusinessProfile] = None
    client: Optional[ClientInfo] = None


class UnderstandResponse(BaseModel):
    understanding: Understanding
    used_ai: bool = False
    model: str = ""
    notes: List[str] = Field(default_factory=list)


class JobDraftRequest(BaseModel):
    job_description: str = Field(min_length=1, max_length=10000)
    quotation_goal: str = Field(min_length=1, max_length=2000)
    target_total_ngn: int = Field(gt=0, le=999999999999, strict=True)
    profile: BusinessProfile = Field(default_factory=BusinessProfile)
    client: ClientInfo = Field(default_factory=ClientInfo)

    @field_validator("job_description", "quotation_goal")
    @classmethod
    def require_nonempty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank.")
        return value


class JobDraftResponse(BaseModel):
    quotation_text: str
    understanding: Understanding
    missing_info: List[str] = Field(default_factory=list)
    target_total_ngn: int
    suggested_total_ngn: int
    model: str
    notice: str


class GenerateRequest(BaseModel):
    title: str = ""
    design_id: str = "premium_business"
    understanding: Understanding
    profile: BusinessProfile = Field(default_factory=BusinessProfile)
    client: ClientInfo = Field(default_factory=ClientInfo)
    reference_id: Optional[str] = None
    raw_input: str = ""
    document_id: Optional[str] = None
    input_kind: Literal["paste", "job"] = "paste"
    job_missing_info: List[str] = Field(default_factory=list, max_length=20)


class GenerateResponse(BaseModel):
    document_id: str
    page_count: int
    pdf_url: str
    preview_urls: List[str] = Field(default_factory=list)
    validation: ValidationReport
    warnings: List[str] = Field(default_factory=list)
