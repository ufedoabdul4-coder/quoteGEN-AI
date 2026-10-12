export interface SemanticBlock {
  id: string;
  type: string;
  text: string;
  level: number;
  items: string[];
  value: number | null;
  figure: string | null;
  group: string;
  order: number;
}

export interface FinancialSummary {
  currency: string;
  rows_total: number | null;
  subtotal: number | null;
  grand_total: number | null;
  stated_total: number | null;
  difference: number | null;
  consistent: boolean;
  note: string;
}

export interface Understanding {
  title: string;
  subtitle: string;
  blocks: SemanticBlock[];
  financials: FinancialSummary;
  missing: string[];
  blocks_seen: number;
  source_kind: string;
  notes: string[];
}

export interface BusinessProfile {
  name: string;
  phone: string;
  email: string;
  website: string;
  address: string;
  logo_data_url: string | null;
}

export interface ClientInfo {
  name: string;
  email: string;
  phone: string;
  address: string;
}

export interface DesignTokens {
  primary: string;
  accent: string;
  text: string;
  muted: string;
  border: string;
  page_bg: string;
  header_bg: string;
  header_text: string;
  table_header_bg: string;
  table_header_text: string;
  zebra: string;
}

export interface DesignInfo {
  id: string;
  name: string;
  description: string;
  kind: 'curated' | 'reference';
  tokens: DesignTokens;
  font_body: string;
  font_heading: string;
  accent_rule: boolean;
  reference_of: string;
}

export interface ValidationFinding {
  level: 'info' | 'warning' | 'error';
  code: string;
  message: string;
  detail: string[];
}

export interface ValidationReport {
  ok: boolean;
  page_count: number;
  pricing_rows: number;
  computed_total: number | null;
  stated_total: number | null;
  literal_markdown: string[];
  missing_blocks: string[];
  findings: ValidationFinding[];
}

export interface UnderstandResponse {
  understanding: Understanding;
  used_ai: boolean;
  model: string;
  notes: string[];
}

export interface PreviewResponse {
  page_count: number;
  previews: string[];
  validation: ValidationReport;
}

export interface GenerateResponse {
  document_id: string;
  page_count: number;
  pdf_url: string;
  preview_urls: string[];
  validation: ValidationReport;
  warnings: string[];
}

export interface DocumentSummary {
  id: string;
  title: string;
  status: 'draft' | 'needs_review' | 'ready';
  client: string;
  page_count: number;
  design_id: string;
  created_at: string;
  updated_at: string;
  pdf_url: string | null;
  preview_url: string | null;
}

export interface DocumentRecord {
  id: string;
  title: string;
  status: 'draft' | 'needs_review' | 'ready';
  created_at: string;
  updated_at: string;
  design_id: string;
  input_kind: string;
  raw_input: string;
  client: ClientInfo;
  profile: BusinessProfile;
  understanding: Understanding;
  validation: ValidationReport | null;
  reference_id: string | null;
  pdf_url: string | null;
  preview_url: string | null;
  page_count: number;
}

export interface ReferenceMeta {
  id: string;
  name: string;
  created_at: string;
  design: DesignInfo;
  size_bytes?: number;
  page_count?: number;
  status?: string;
}

export interface TemplateMeta {
  id: string;
  name: string;
  source_filename: string;
  size_bytes: number;
  page_count: number;
  status: 'uploaded' | 'analysing' | 'ready' | 'failed';
  error: string;
  created_at: string;
  updated_at: string;
  is_active: boolean;
  design: DesignInfo;
}

export interface GenerateRequest {
  title: string;
  design_id: string;
  understanding: Understanding;
  profile: BusinessProfile;
  client: ClientInfo;
  reference_id: string | null;
  raw_input: string;
  document_id?: string | null;
}
