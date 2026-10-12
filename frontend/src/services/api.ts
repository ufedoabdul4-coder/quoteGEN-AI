import type {
  BusinessProfile,
  BillingStatus,
  ClientInfo,
  DesignInfo,
  DocumentSummary,
  DocumentRecord,
  GenerateRequest,
  GenerateResponse,
  PreviewResponse,
  ReferenceMeta,
  TemplateMeta,
  UnderstandResponse,
} from '../types';
import { supabase } from './supabase';

// The Vite dev proxy forwards `/api/*` to the FastAPI backend (stripping the
// prefix), so every call and asset URL goes through one base path.
const API = (import.meta.env.VITE_API_URL || '/api').replace(/\/+$/, '');

async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (supabase) {
    const { data, error } = await supabase.auth.getSession();
    if (error) throw new Error(error.message);
    if (data.session?.access_token) {
      headers.set('Authorization', `Bearer ${data.session.access_token}`);
    }
  }

  const apiPath = path.startsWith('/api/') ? path.slice(4) : path;
  const response = await fetch(`${API}${apiPath}`, { ...init, headers });
  if (response.status === 401 && supabase) {
    window.dispatchEvent(new Event('quotegen:unauthorized'));
  }
  return response;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await apiFetch(path, init);
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    const message = (detail as {
      detail?: string | {
        code?: string;
        message?: string;
        monthly_price_ngn?: number;
      };
    }).detail;
    throw new ApiError(
      typeof message === 'string'
        ? message
        : message?.message || `Request failed (${response.status})`,
      response.status,
      message,
    );
  }
  return response.json() as Promise<T>;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly detail?: string | {
      code?: string;
      message?: string;
      monthly_price_ngn?: number;
    },
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

export async function authenticatedAsset(path: string): Promise<Blob> {
  const response = await apiFetch(path);
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new ApiError(
      (detail as { detail?: string }).detail || `Unable to load file (${response.status})`,
      response.status,
    );
  }
  return response.blob();
}

export async function openAuthenticatedAsset(path: string): Promise<void> {
  const popup = window.open('about:blank', '_blank');
  if (!popup) throw new Error('Allow pop-ups to open the PDF.');
  try {
    const blob = await authenticatedAsset(path);
    const url = URL.createObjectURL(blob);
    popup.location.href = url;
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
  } catch (error) {
    popup.close();
    throw error;
  }
}

export const api = {
  health: () => request<{ status: string }>('/health'),

  designs: () =>
    request<{ designs: DesignInfo[] }>('/designs').then((r) => r.designs),

  understand: (text: string, kind: string, profile: BusinessProfile, client: ClientInfo) =>
    request<UnderstandResponse>('/understand', json({ text, kind, profile, client })),

  preview: (payload: GenerateRequest) =>
    request<PreviewResponse>('/preview', json(payload)),

  generate: (payload: GenerateRequest) =>
    request<GenerateResponse>('/generate', json(payload)),

  billingStatus: () => request<BillingStatus>('/billing/status'),

  billingCheckout: (email: string, name: string) =>
    request<{ checkout_url: string }>('/billing/checkout', json({ email, name })),

  verifyPayment: (transactionId: string, txRef: string) =>
    request<BillingStatus>('/billing/verify', json({
      transaction_id: transactionId,
      tx_ref: txRef,
    })),

  documents: () =>
    request<{ documents: DocumentSummary[] }>('/documents').then((r) => r.documents),

  document: (id: string) =>
    request<DocumentRecord>(`/documents/${id}`),

  deleteDocument: (id: string) =>
    request<{ deleted: boolean }>(`/documents/${id}`, { method: 'DELETE' }),

  references: () =>
    request<{ references: ReferenceMeta[] }>('/references').then((r) => r.references),

  uploadReference: async (file: File): Promise<ReferenceMeta> => {
    const form = new FormData();
    form.append('file', file);
    const response = await apiFetch('/references/upload', { method: 'POST', body: form });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error((detail as { detail?: string }).detail || 'Upload failed');
    }
    return response.json();
  },

  deleteReference: (id: string) =>
    request<{ deleted: boolean }>(`/references/${id}`, { method: 'DELETE' }),

  templates: () =>
    request<{ templates: TemplateMeta[] }>('/templates').then((r) => r.templates),

  template: (id: string) => request<TemplateMeta>(`/templates/${id}`),

  templatePdf: async (id: string): Promise<Blob> => {
    return authenticatedAsset(`/templates/${id}/pdf`);
  },

  uploadTemplate: async (file: File): Promise<TemplateMeta> => {
    const form = new FormData();
    form.append('file', file);
    const response = await apiFetch('/templates/upload', { method: 'POST', body: form });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error((detail as { detail?: string }).detail || 'Upload failed');
    }
    return response.json();
  },

  replaceTemplate: async (id: string, file: File): Promise<TemplateMeta> => {
    const form = new FormData();
    form.append('file', file);
    const response = await apiFetch(`/templates/${id}/replace`, {
      method: 'PUT', body: form,
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error((detail as { detail?: string }).detail || 'Replacement failed');
    }
    return response.json();
  },

  renameTemplate: (id: string, name: string) =>
    request<TemplateMeta>(`/templates/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    }),

  deleteTemplate: (id: string) =>
    request<{ deleted: boolean }>(`/templates/${id}`, { method: 'DELETE' }),

  activeTemplate: () =>
    request<{ template: TemplateMeta | null }>('/templates/active').then((r) => r.template),

  setActiveTemplate: (templateId: string) =>
    request<{ template: TemplateMeta }>('/templates/active', json({ template_id: templateId }))
      .then((r) => r.template),

  clearActiveTemplate: () =>
    request<{ template: null }>('/templates/active', { method: 'DELETE' }),

  profile: () => request<BusinessProfile>('/profile'),

  saveProfile: (profile: BusinessProfile) =>
    request<BusinessProfile>('/profile', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(profile),
    }),
};
