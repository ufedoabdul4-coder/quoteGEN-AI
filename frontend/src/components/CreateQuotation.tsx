import { useRef, useState } from 'react';
import {
  Sparkles, LoaderCircle, Download, ScanText, Pencil, X, Check,
} from 'lucide-react';
import type {
  BusinessProfile, ServiceType, ClientInfo, DocumentRecord, GenerateRequest, TemplateMeta,
  SemanticBlock, Understanding,
} from '../types';
import {
  api, ApiError, downloadAuthenticatedAsset,
} from '../services/api';
import { PreviewPane } from './PreviewPane';
import { BlockEditor } from './BlockEditor';
import { PlanBenefits } from './PlanBenefits';
import { SERVICE_SUGGESTIONS } from '../utils/services';
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
  cleaningType: ServiceType | null = null,
  quotationGoal = '',
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
    quotation_goal: quotationGoal,
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
  const [cleaningType, setCleaningType] = useState<ServiceType>(
    initialDocument?.cleaning_type || '',
  );
  const [quotationGoal, setQuotationGoal] = useState(initialDocument?.quotation_goal || '');
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
  const formRef = useRef<HTMLDivElement>(null);
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState('');
  const [quotaExhausted, setQuotaExhausted] = useState(false);
  const [monthlyPrice, setMonthlyPrice] = useState<number | null>(null);
  const [monthlyAutoRenew, setMonthlyAutoRenew] = useState(false);
  const [showPlanBenefits, setShowPlanBenefits] = useState(false);
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
          generatedFromJob ? quotationGoal : '',
        ));
      setDocumentId(response.document_id);
      setPdfUrl(response.pdf_url);
      setPages(response.preview_urls);
      onSaved();
    } catch (e) {
      if (e instanceof ApiError && e.status === 402) {
        setQuotaExhausted(true);
        if (typeof e.detail === 'object') {
          if (e.detail?.monthly_price_ngn) setMonthlyPrice(e.detail.monthly_price_ngn);
          setMonthlyAutoRenew(Boolean(e.detail?.monthly_plan_auto_renew));
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
          draft.missing_info, jobDescription.trim(), cleaningType, quotationGoal.trim(),
        ),
      );
      setDocumentId(response.document_id);
      setPdfUrl(response.pdf_url);
      setPages(response.preview_urls);
      onSaved();
    } catch (e) {
      if (e instanceof ApiError && e.status === 402) {
        setQuotaExhausted(true);
        if (typeof e.detail === 'object') {
          if (e.detail?.monthly_price_ngn) setMonthlyPrice(e.detail.monthly_price_ngn);
          setMonthlyAutoRenew(Boolean(e.detail?.monthly_plan_auto_renew));
        }
        setError('');
      } else {
        setError((e as Error).message);
      }
    } finally {
      setBusy(null);
    }
  };

  const editAndRegenerate = () => {
    setError('');
    setInputMode('paste');
    setGeneratedFromJob(false);
    setDraftUnderstanding(null);
    window.requestAnimationFrame(() => {
      formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
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
        buildPayload(
          draftUnderstanding, profile, client, text, documentId,
          generatedFromJob ? 'job' : inputMode, jobMissingInfo,
          generatedFromJob ? jobDescription : '',
          generatedFromJob ? cleaningType : null,
          generatedFromJob ? quotationGoal : '',
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
      <div ref={formRef} className="space-y-4 min-w-0">
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
                  Get unlimited proposals for{' '}
                  {monthlyPrice === null ? '₦13,310' : `₦${monthlyPrice.toLocaleString('en-NG')}`}
                  /month{monthlyAutoRenew ? ', renewed automatically until you cancel' : ''}.
                </p>
              </div>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => setShowPlanBenefits(true)}
                disabled={checkoutBusy}
              >
                <Sparkles size={15} /> See the Unlimited plan
              </button>
              {error && <p role="alert" className="text-xs text-[var(--error)]">{error}</p>}
            </div>
          )}

          <PlanBenefits
            open={showPlanBenefits}
            price={monthlyPrice ?? 13310}
            autoRenew={monthlyAutoRenew}
            busy={checkoutBusy}
            error={error}
            onClose={() => setShowPlanBenefits(false)}
            onConfirm={() => { void startMonthlyCheckout(); }}
          />

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
                <label htmlFor="service-type" className="label">Service or profession</label>
                <input
                  id="service-type"
                  className="input"
                  list="service-type-suggestions"
                  value={cleaningType}
                  onChange={(event) => setCleaningType(event.target.value)}
                  placeholder="e.g. Electrical installation, Plumbing, Cleaning"
                  maxLength={80}
                  autoComplete="off"
                  disabled={Boolean(busy)}
                />
                <datalist id="service-type-suggestions">
                  {SERVICE_SUGGESTIONS.map((service) => (
                    <option key={service} value={service} />
                  ))}
                </datalist>
                <p className="mt-1 text-xs text-[var(--text-muted)]">
                  Type your trade or service. This guides the scope for any profession.
                </p>
              </div>
              <div>
                <label htmlFor="job-description" className="label">Job description</label>
                <textarea
                  id="job-description"
                  className="textarea"
                  value={jobDescription}
                  onChange={(e) => setJobDescription(e.target.value)}
                  placeholder={'Describe the work, areas, items, quantities, and requirements…\n\nFor example: 3 bedrooms with toilets, kitchen, and BQ — or: supply and install 12 LED fittings across 3 offices.'}
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
              <button type="button" className="btn"
                onClick={editAndRegenerate} disabled={Boolean(busy)}>
                <Pencil size={15} /> Edit &amp; Regenerate
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
    </>
  );
}
