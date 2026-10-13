import { useEffect, useRef, useState } from 'react';
import {
  Sparkles, LoaderCircle, Download, ScanText, Pencil, X, Check,
} from 'lucide-react';
import type {
  BusinessProfile, CleaningServiceType, ClientInfo, DocumentRecord, GenerateRequest, TemplateMeta,
  SemanticBlock, Understanding,
} from '../types';
import {
  api, ApiError, authenticatedAsset, downloadAuthenticatedAsset,
} from '../services/api';
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

const CLEANING_SERVICES: { value: CleaningServiceType; label: string }[] = [
  { value: 'residential_deep_cleaning', label: 'Residential deep cleaning' },
  { value: 'regular_house_cleaning', label: 'Regular house cleaning' },
  { value: 'post_construction_cleaning', label: 'Post-construction cleaning' },
  { value: 'office_cleaning', label: 'Office cleaning' },
  { value: 'commercial_facility_cleaning', label: 'Commercial facility cleaning' },
  { value: 'move_in_move_out_cleaning', label: 'Move-in or move-out cleaning' },
  { value: 'upholstery_cleaning', label: 'Upholstery cleaning' },
  { value: 'fumigation_pest_control', label: 'Fumigation or pest control' },
];

function isCleaningServiceType(value: string): value is CleaningServiceType {
  return CLEANING_SERVICES.some((service) => service.value === value);
}

type Busy = 'draft' | 'understand' | 'generate' | null;

interface Props {
  profile: BusinessProfile;
  activeTemplate: TemplateMeta | null;
  onManageTemplates: () => void;
  onSaved: () => void;
  initialDocument?: DocumentRecord | null;
}

function buildPayload(
  understanding: Understanding, profile: BusinessProfile, client: ClientInfo, rawInput: string,
  documentId?: string | null, inputKind: 'paste' | 'job' = 'paste',
  jobMissingInfo: string[] = [],
  jobDescription = '',
  cleaningType: CleaningServiceType | null = null,
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
    input_kind: inputKind,
    job_description: jobDescription,
    cleaning_type: cleaningType,
    job_missing_info: jobMissingInfo,
  };
}

export function CreateQuotation({
  profile, activeTemplate, onManageTemplates, onSaved, initialDocument,
}: Props) {
  const { email, session } = useAuth();
  const [text, setText] = useState(initialDocument?.raw_input || '');
  const [inputMode, setInputMode] = useState<'paste' | 'job'>(
    initialDocument?.input_kind === 'job' ? 'job' : 'paste',
  );
  const [generatedFromJob, setGeneratedFromJob] = useState(
    initialDocument?.input_kind === 'job',
  );
  const [jobDescription, setJobDescription] = useState(initialDocument?.job_description || '');
  const [cleaningType, setCleaningType] = useState<CleaningServiceType>(
    initialDocument?.cleaning_type || 'residential_deep_cleaning',
  );
  const [quotationGoal, setQuotationGoal] = useState('');
  const [targetTotalNgn, setTargetTotalNgn] = useState(() => {
    const savedTotal = initialDocument?.understanding.financials.grand_total;
    return initialDocument?.input_kind === 'job' && savedTotal
      ? String(Math.round(savedTotal))
      : '';
  });
  const [jobMissingInfo, setJobMissingInfo] = useState<string[]>(
    initialDocument?.job_missing_info ?? [],
  );
  const [jobTotals, setJobTotals] = useState<{ total: number; target: number } | null>(null);
  const [jobEstimateNotice, setJobEstimateNotice] = useState(
    initialDocument?.input_kind === 'job'
      ? 'The proposal total is fixed at the amount entered when this draft was created.'
      : '',
  );
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
  const [pdfEditorOpen, setPdfEditorOpen] = useState(false);
  const [pdfEditorError, setPdfEditorError] = useState('');
  const pdfEditorFrame = useRef<HTMLIFrameElement>(null);
  const pdfEditorFileSent = useRef(false);
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
        buildPayload(
          currentUnderstanding, profile, client, text, documentId,
          generatedFromJob ? 'job' : 'paste', jobMissingInfo,
          generatedFromJob ? jobDescription : '',
          generatedFromJob ? cleaningType : null,
        ));
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

  const generateFromJob = async () => {
    const targetTotal = Number(targetTotalNgn);
    if (!jobDescription.trim() || !quotationGoal.trim()
      || !Number.isSafeInteger(targetTotal) || targetTotal <= 0) {
      setError('Enter the job description, quotation objective, and a valid proposal total in Naira.');
      return;
    }
    setBusy('draft');
    setError('');
    setJobMissingInfo([]);
    try {
      const draft = await api.draftJobQuotation({
        cleaning_type: cleaningType,
        job_description: jobDescription.trim(),
        quotation_goal: quotationGoal.trim(),
        target_total_ngn: targetTotal,
        profile,
        client,
      });
      if (
        draft.target_total_ngn !== targetTotal
        || draft.suggested_total_ngn !== targetTotal
        || draft.understanding.financials.grand_total !== targetTotal
        || !draft.understanding.financials.consistent
      ) {
        throw new Error(
          'The draft did not preserve your exact proposal total. Nothing was generated; please try again.',
        );
      }
      setText(draft.quotation_text);
      setGeneratedFromJob(true);
      setJobMissingInfo(draft.missing_info);
      setJobTotals({ total: draft.suggested_total_ngn, target: draft.target_total_ngn });
      setJobEstimateNotice(draft.notice);
      setEngine({ usedAi: true, model: draft.model });
      setUnderstanding(draft.understanding);
      setBusy('generate');
      const response = await api.generate(
        buildPayload(
          draft.understanding, profile, client, draft.quotation_text, documentId, 'job',
          draft.missing_info, jobDescription.trim(), cleaningType,
        ),
      );
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

  useEffect(() => {
    if (!pdfEditorOpen) return undefined;
    let sendingFile = false;
    const onEditorMessage = async (event: MessageEvent) => {
      if (event.origin !== window.location.origin
        || event.source !== pdfEditorFrame.current?.contentWindow
        || !event.data || typeof event.data !== 'object') return;
      if (event.data.type === 'pdfzero:ready' && !sendingFile && !pdfEditorFileSent.current) {
        sendingFile = true;
        try {
          const pdf = await authenticatedAsset(pdfUrl);
          const bytes = await pdf.arrayBuffer();
          if (pdfEditorFrame.current?.contentWindow) {
            pdfEditorFileSent.current = true;
            pdfEditorFrame.current.contentWindow.postMessage({
              type: 'pdfzero:load',
              bytes,
              fileName: `${understanding?.title || 'quoteGEN-proposal'}.pdf`,
            }, window.location.origin, [bytes]);
          }
        } catch (cause) {
          setPdfEditorError(cause instanceof Error ? cause.message : 'Unable to load the PDF editor.');
        } finally {
          sendingFile = false;
        }
      } else if (event.data.type === 'pdfzero:export') {
        const bytes = event.data.bytes;
        if (!(bytes instanceof ArrayBuffer) || bytes.byteLength < 5
          || new TextDecoder().decode(new Uint8Array(bytes, 0, 5)) !== '%PDF-') {
          setPdfEditorError('The editor did not return a valid PDF. The original remains unchanged.');
          pdfEditorFrame.current?.contentWindow?.postMessage({
            type: 'pdfzero:download-error',
          }, window.location.origin);
          return;
        }
        const blob = new Blob([bytes], { type: 'application/pdf' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = event.data.fileName
          || `${understanding?.title || 'quoteGEN-proposal'}-corrected.pdf`;
        link.click();
        window.setTimeout(() => URL.revokeObjectURL(url), 1000);
        setPdfEditorError('');
        pdfEditorFrame.current?.contentWindow?.postMessage({
          type: 'pdfzero:downloaded',
        }, window.location.origin);
      } else if (event.data.type === 'pdfzero:close') {
        setPdfEditorOpen(false);
      } else if (event.data.type === 'pdfzero:error') {
        setPdfEditorError(typeof event.data.message === 'string'
          ? event.data.message : 'The PDF editor could not complete that operation.');
      }
    };
    window.addEventListener('message', onEditorMessage);
    return () => window.removeEventListener('message', onEditorMessage);
  }, [pdfEditorOpen, pdfUrl, understanding?.title]);

  const updateDraftBlocks = (blocks: SemanticBlock[]) => {
    setDraftUnderstanding((current) => current ? { ...current, blocks } : current);
  };

  const regenerateEditedQuotation = async () => {
    if (!draftUnderstanding) return;
    setBusy('generate');
    setError('');
    try {
      const response = await api.generate(
        buildPayload(
          draftUnderstanding, profile, client, text, documentId,
          generatedFromJob ? 'job' : inputMode, jobMissingInfo,
          generatedFromJob ? jobDescription : '',
          generatedFromJob ? cleaningType : null,
        ),
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
    <>
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
      <div className="space-y-4 min-w-0">
        <div className="card p-4 sm:p-5 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 className="text-lg font-semibold">Create a proposal</h1>
              <p className="text-xs text-[var(--text-muted)]">
                Build a detailed, client-ready proposal using your master document.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap gap-2" role="group" aria-label="Proposal input mode">
            <button
              type="button"
              className={`btn ${inputMode === 'paste' ? 'btn-primary' : ''}`}
              onClick={() => setInputMode('paste')}
              disabled={Boolean(busy)}
            >
              Write a proposal
            </button>
            <button
              type="button"
              className={`btn ${inputMode === 'job' ? 'btn-primary' : ''}`}
              onClick={() => setInputMode('job')}
              disabled={Boolean(busy)}
            >
              Describe a job
            </button>
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
                  The free plan allows 10 proposals in any rolling 30 days, with up to 3 per UTC day.
                  Get unlimited proposals for one month for{' '}
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
                <h2 className="text-sm font-semibold">Edit proposal content</h2>
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
          ) : inputMode === 'job' ? (
            <div className="space-y-3">
              <div>
                <label htmlFor="cleaning-type" className="label">Cleaning service type</label>
                <select
                  id="cleaning-type"
                  className="select"
                  value={cleaningType}
                  onChange={(event) => {
                    if (isCleaningServiceType(event.target.value)) {
                      setCleaningType(event.target.value);
                    }
                  }}
                  disabled={Boolean(busy)}
                >
                  {CLEANING_SERVICES.map((service) => (
                    <option key={service.value} value={service.value}>{service.label}</option>
                  ))}
                </select>
                <p className="mt-1 text-xs text-[var(--text-muted)]">
                  This selection guides the scope and keeps unrelated services out of the proposal.
                </p>
              </div>
              <div>
                <label htmlFor="job-description" className="label">Job description</label>
                <textarea
                  id="job-description"
                  className="textarea"
                  value={jobDescription}
                  onChange={(e) => setJobDescription(e.target.value)}
                  placeholder={'Describe the rooms, areas, quantities, and work required…\n\nFor example: 3 bedrooms with toilets, sitting room, guest room with toilet, open kitchen, dining room, family lounge with balcony, and BQ.'}
                  maxLength={10000}
                  style={{ minHeight: 190 }}
                  disabled={Boolean(busy)}
                />
              </div>
              <div>
                <label htmlFor="quotation-goal" className="label">
                  What should the proposal cover?
                </label>
                <textarea
                  id="quotation-goal"
                  className="textarea"
                  value={quotationGoal}
                  onChange={(e) => setQuotationGoal(e.target.value)}
                  placeholder="For example: a detailed proposal with a clear work sequence, agreed scope, and relevant exclusions."
                  maxLength={2000}
                  style={{ minHeight: 88 }}
                  disabled={Boolean(busy)}
                />
              </div>
              <div>
                <label htmlFor="job-budget" className="label">Target proposal total (₦)</label>
                <input
                  id="job-budget"
                  className="input"
                  type="number"
                  min="1"
                  max="999999999999"
                  step="1"
                  inputMode="numeric"
                  value={targetTotalNgn}
                  onChange={(e) => setTargetTotalNgn(e.target.value)}
                  placeholder="850000"
                  disabled={Boolean(busy)}
                />
                <p className="mt-1 text-xs text-[var(--text-muted)]">
                  This is the final proposal total. The server distributes this exact amount across the work items and will not change it.
                </p>
              </div>
              {jobEstimateNotice && (
                <div className="panel p-3 text-xs" role="status">{jobEstimateNotice}</div>
              )}
              {jobTotals && (
                <div className="panel p-3 text-xs" role="status">
                  Proposal total: <strong>₦{jobTotals.total.toLocaleString('en-NG')}</strong>
                </div>
              )}
              {jobMissingInfo.length > 0 && (
                <div className="panel p-3 text-xs" role="status">
                  <div className="font-semibold mb-1">Confirm these details before sending:</div>
                  <ul className="list-disc pl-5 space-y-1">
                    {jobMissingInfo.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}
                  </ul>
                </div>
              )}
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => { void generateFromJob(); }}
                disabled={quotaExhausted || Boolean(busy) || !activeTemplate}
              >
                {busy
                  ? <LoaderCircle size={15} className="spin" />
                  : <Sparkles size={15} />}
                {busy === 'draft' ? 'Drafting proposal…'
                  : busy === 'understand' ? 'Preparing proposal…'
                    : busy === 'generate' ? 'Generating document…'
                      : error.includes('HTTP 429') ? 'Retry proposal generation'
                        : pdfUrl ? 'Draft again & generate' : 'Draft & generate proposal'}
              </button>
              {engine?.usedAi && (
                <p className="text-xs text-[var(--text-muted)]">Drafted by {engine.model || 'AI'}</p>
              )}
            </div>
          ) : (
            <div className="space-y-2">
              <textarea
                className="textarea"
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Paste or write the proposal exactly as it should read, including its details, line items, prices and terms…"
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
              {jobEstimateNotice && (
                <div className="panel p-3 text-xs" role="status">{jobEstimateNotice}</div>
              )}
              {engine && (
                <p className="text-xs text-[var(--text-muted)]">
                  {generatedFromJob
                    ? `Drafted by ${engine.model || 'AI'}`
                    : engine.usedAi
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
            emptyHint="Add the proposal details, then generate the document to see it here." />
        </div>
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            {pdfUrl && (
              <>
              {understanding && (
                <button type="button" className="btn"
                  onClick={startEditing} disabled={Boolean(busy)}>
                  <Pencil size={15} /> Edit proposal content
                </button>
              )}
              <button type="button" className="btn"
                onClick={() => {
                  pdfEditorFileSent.current = false;
                  setPdfEditorError('');
                  setPdfEditorOpen(true);
                }}>
                <Pencil size={15} /> Edit PDF
              </button>
              <button type="button" className="btn ml-auto"
                onClick={() => { void downloadAuthenticatedAsset(
                  pdfUrl,
                  `${understanding?.title || 'quoteGEN-proposal'}.pdf`,
                ).catch((e: unknown) => {
                  setError(e instanceof Error ? e.message : 'Unable to download the PDF.');
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
    {pdfEditorOpen && (
      <div className="fixed inset-0 z-50 bg-black/70 p-3 sm:p-6"
        role="dialog" aria-modal="true" aria-label="Edit generated PDF">
        <div className="mx-auto flex h-full max-w-[1600px] flex-col overflow-hidden rounded-xl bg-[var(--surface)] shadow-2xl">
          <div className="flex items-center justify-between gap-4 border-b border-[var(--border)] px-4 py-3">
            <div>
              <h2 className="font-semibold">Edit generated PDF</h2>
              <p className="text-xs text-[var(--text-muted)]">
                Edits stay in this browser. Review every page before downloading; complex backgrounds and fonts may not reproduce exactly.
              </p>
            </div>
            <button type="button" className="btn" onClick={() => setPdfEditorOpen(false)}
              aria-label="Close PDF editor">
              <X size={16} /> Close
            </button>
          </div>
          {pdfEditorError && (
            <p className="px-4 py-2 text-sm text-[var(--error)]" role="alert">{pdfEditorError}</p>
          )}
          <iframe
            ref={pdfEditorFrame}
            title="PDFZero editor"
            src="/pdf-editor/"
            className="min-h-0 w-full flex-1 border-0"
          />
        </div>
      </div>
    )}
    </>
  );
}
