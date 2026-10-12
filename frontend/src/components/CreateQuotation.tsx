import { useState } from 'react';
import {
  Sparkles, LoaderCircle, Download, ScanText, Pencil, X, Check,
} from 'lucide-react';
import type {
  BusinessProfile, ClientInfo, DocumentRecord, GenerateRequest, TemplateMeta,
  SemanticBlock, Understanding,
} from '../types';
import { api, ApiError, openAuthenticatedAsset } from '../services/api';
import { PreviewPane } from './PreviewPane';
import { BlockEditor } from './BlockEditor';
import { useAuth } from '../services/auth';

const SAMPLE = `Quotation for Acme Facilities Ltd
Prepared for: Acme Facilities Ltd
Quotation No: Q-2026-0042
Date: 2026-02-01

Scope of works
- Site survey and full measurement
- Removal and disposal of existing fixtures
- Supply and installation of new units
- Final testing and handover

| Description | Amount |
| --- | --- |
| Supply and install unit A | 250,000 |
| Supply and install unit B | 150,000 |
| Subtotal | 400,000 |
| Grand Total | 400,000 |

Payment terms: 70% deposit on award, balance on completion.
Signature: ______________________`;

type Busy = 'understand' | 'generate' | null;

interface Props {
  profile: BusinessProfile;
  activeTemplate: TemplateMeta | null;
  onManageTemplates: () => void;
  onSaved: () => void;
  initialDocument?: DocumentRecord | null;
}

function buildPayload(
  understanding: Understanding, profile: BusinessProfile, client: ClientInfo, rawInput: string,
  documentId?: string | null,
): GenerateRequest {
  return {
    title: understanding.title || 'Quotation',
    design_id: 'premium_business',
    understanding,
    profile,
    client,
    reference_id: null,
    raw_input: rawInput,
    document_id: documentId ?? null,
  };
}

export function CreateQuotation({
  profile, activeTemplate, onManageTemplates, onSaved, initialDocument,
}: Props) {
  const { email, session } = useAuth();
  const [text, setText] = useState(initialDocument?.raw_input || '');
  const client: ClientInfo = initialDocument?.client
    ?? { name: '', email: '', phone: '', address: '' };
  const [documentId, setDocumentId] = useState<string | null>(initialDocument?.id ?? null);
  const [understanding, setUnderstanding] = useState<Understanding | null>(
    initialDocument?.understanding ?? null,
  );
  const [draftUnderstanding, setDraftUnderstanding] = useState<Understanding | null>(null);
  const [pages, setPages] = useState<string[]>(
    initialDocument?.preview_url ? [initialDocument.preview_url] : [],
  );
  const [pdfUrl, setPdfUrl] = useState(initialDocument?.pdf_url || '');
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState('');
  const [quotaExhausted, setQuotaExhausted] = useState(false);
  const [monthlyPrice, setMonthlyPrice] = useState<number | null>(null);
  const [checkoutBusy, setCheckoutBusy] = useState(false);
  const [engine, setEngine] = useState<{ usedAi: boolean; model: string } | null>(null);

  const generateQuotation = async () => {
    setBusy('understand');
    setError('');
    try {
      let currentUnderstanding = understanding;
      if (text.trim()) {
        const response = await api.understand(text, 'paste', profile, client);
        currentUnderstanding = response.understanding;
        setUnderstanding(currentUnderstanding);
        setEngine({ usedAi: response.used_ai, model: response.model });
      }
      if (!currentUnderstanding) {
        throw new Error('Add the quotation details before generating the document.');
      }

      setBusy('generate');
      const response = await api.generate(
        buildPayload(currentUnderstanding, profile, client, text, documentId));
      setDocumentId(response.document_id);
      setPdfUrl(response.pdf_url);
      setPages(response.preview_urls);
      onSaved();
    } catch (e) {
      if (e instanceof ApiError && e.status === 402) {
        setQuotaExhausted(true);
        if (typeof e.detail === 'object' && e.detail?.monthly_price_ngn) {
          setMonthlyPrice(e.detail.monthly_price_ngn);
        }
        setError('');
      } else {
        setError((e as Error).message);
      }
    } finally {
      setBusy(null);
    }
  };

  const startEditing = () => {
    if (!understanding) return;
    setDraftUnderstanding({
      ...understanding,
      blocks: understanding.blocks.map((block) => ({ ...block, items: [...block.items] })),
    });
  };

  const updateDraftBlocks = (blocks: SemanticBlock[]) => {
    setDraftUnderstanding((current) => current ? { ...current, blocks } : current);
  };

  const regenerateEditedQuotation = async () => {
    if (!draftUnderstanding) return;
    setBusy('generate');
    setError('');
    try {
      const response = await api.generate(
        buildPayload(draftUnderstanding, profile, client, text, documentId),
      );
      setUnderstanding(draftUnderstanding);
      setDraftUnderstanding(null);
      setDocumentId(response.document_id);
      setPdfUrl(response.pdf_url);
      setPages(response.preview_urls);
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to regenerate the quotation.');
    } finally {
      setBusy(null);
    }
  };

  const startMonthlyCheckout = async () => {
    if (!email) {
      setError('Could not identify your signed-in email. Please sign in again.');
      return;
    }
    setCheckoutBusy(true);
    setError('');
    try {
      const fullName = session?.user.user_metadata?.full_name;
      const result = await api.billingCheckout(
        email,
        typeof fullName === 'string' ? fullName : '',
      );
      window.location.assign(result.checkout_url);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to start payment.');
      setCheckoutBusy(false);
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
      <div className="space-y-4 min-w-0">
        <div className="card p-4 sm:p-5 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 className="text-lg font-semibold">Create a quotation</h1>
              <p className="text-xs text-[var(--text-muted)]">
                Add the quotation content. It will be placed in your master template.
              </p>
            </div>
          </div>

          {activeTemplate && (
            <div className="panel flex flex-wrap items-center justify-between gap-3 p-3">
              <div className="min-w-0">
                <div className="text-xs font-semibold">Master document</div>
                <div className="truncate text-xs text-[var(--text-dim)]">
                  {activeTemplate.name} · {activeTemplate.page_count} page(s)
                </div>
              </div>
              <button type="button" className="btn" onClick={onManageTemplates}>
                Change document
              </button>
            </div>
          )}

          {!activeTemplate && (
            <div className="panel flex flex-wrap items-center justify-between gap-3 p-3">
              <p className="text-xs text-[var(--text-muted)]">
                Add a master document before generating. Its uploaded design will be preserved.
              </p>
              <button type="button" className="btn" onClick={onManageTemplates}>
                Add master document
              </button>
            </div>
          )}

          {quotaExhausted && (
            <div className="panel p-4 space-y-3" role="status">
              <div>
                <h2 className="font-semibold">You’ve reached your free generation limit</h2>
                <p className="text-sm text-[var(--text-muted)] mt-1">
                  The free plan allows 10 quotations in any rolling 30 days, with up to 3 per UTC day.
                  Get unlimited quotations for one month for{' '}
                  {monthlyPrice === null ? '₦13,310' : `₦${monthlyPrice.toLocaleString('en-NG')}`}.
                  This is a one-time monthly payment; it does not auto-renew.
                </p>
              </div>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => { void startMonthlyCheckout(); }}
                disabled={checkoutBusy}
              >
                {checkoutBusy
                  ? <LoaderCircle size={15} className="spin" />
                  : <Sparkles size={15} />}
                Continue to Flutterwave
              </button>
              {error && <p role="alert" className="text-xs text-[var(--error)]">{error}</p>}
            </div>
          )}

          {draftUnderstanding ? (
            <div className="space-y-3">
              <div className="panel p-3">
                <h2 className="text-sm font-semibold">Edit quotation content</h2>
                <p className="text-xs text-[var(--text-muted)] mt-1">
                  Change, remove, or reorder content, then regenerate. Your master design is preserved.
                </p>
              </div>
              <BlockEditor blocks={draftUnderstanding.blocks} onChange={updateDraftBlocks} />
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => { void regenerateEditedQuotation(); }}
                  disabled={Boolean(busy) || draftUnderstanding.blocks.length === 0}
                >
                  {busy === 'generate'
                    ? <LoaderCircle size={15} className="spin" />
                    : <Check size={15} />}
                  {busy === 'generate' ? 'Regenerating…' : 'Apply changes & regenerate'}
                </button>
                <button
                  type="button"
                  className="btn"
                  onClick={() => setDraftUnderstanding(null)}
                  disabled={Boolean(busy)}
                >
                  <X size={15} /> Cancel
                </button>
              </div>
            </div>
          ) : (
          <div className="space-y-2">
              <textarea
                className="textarea"
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Paste or write the quotation exactly as it should read, including its details, line items, prices and terms…"
                style={{ minHeight: 280 }}
              />
              <div className="flex items-center gap-2">
                <button type="button" className="btn btn-primary" onClick={() => void generateQuotation()}
                  disabled={quotaExhausted || (!text.trim() && !understanding) || Boolean(busy) || !activeTemplate}>
                  {busy
                    ? <LoaderCircle size={15} className="spin" />
                    : <Sparkles size={15} />}
                  {busy === 'understand' ? 'Understanding…'
                    : busy === 'generate' ? 'Generating…'
                      : pdfUrl ? 'Generate again' : 'Generate document'}
                </button>
                <button type="button" className="btn" onClick={() => setText(SAMPLE)}
                  disabled={Boolean(busy)}>
                  <ScanText size={15} /> Load sample
                </button>
              </div>
              {engine && (
                <p className="text-xs text-[var(--text-muted)]">
                  {engine.usedAi
                    ? `Understood by ${engine.model || 'AI'}`
                    : 'Understood without AI'}
                </p>
              )}
          </div>
          )}
        </div>

      </div>

      <div className="lg:sticky lg:top-4 h-[calc(100vh-6rem)] min-h-[560px] flex flex-col gap-4">
        <div className="flex-1 min-h-0">
          <PreviewPane pages={pages} pdfUrl={pdfUrl || undefined}
            title={understanding?.title}
            emptyHint="Add the quotation details, then generate the document to see it here." />
        </div>
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            {pdfUrl && (
              <>
              {understanding && (
                <button type="button" className="btn"
                  onClick={startEditing} disabled={Boolean(busy)}>
                  <Pencil size={15} /> Edit content
                </button>
              )}
              <button type="button" className="btn ml-auto"
                onClick={() => { void openAuthenticatedAsset(pdfUrl).catch((e: unknown) => {
                  setError(e instanceof Error ? e.message : 'Unable to open the PDF.');
                }); }}>
                <Download size={15} /> Download
              </button>
              </>
            )}
          </div>
          {error && <p className="text-xs text-[var(--error)]">{error}</p>}
        </div>
      </div>
    </div>
  );
}
