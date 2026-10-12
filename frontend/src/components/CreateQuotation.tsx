import { useState } from 'react';
import {
  Sparkles, LoaderCircle, Download, ScanText,
} from 'lucide-react';
import type {
  BusinessProfile, ClientInfo, DocumentRecord, GenerateRequest, TemplateMeta,
  Understanding,
} from '../types';
import { api, assetUrl } from '../services/api';
import { PreviewPane } from './PreviewPane';

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
  const [text, setText] = useState(initialDocument?.raw_input || '');
  const client: ClientInfo = initialDocument?.client
    ?? { name: '', email: '', phone: '', address: '' };
  const [documentId, setDocumentId] = useState<string | null>(initialDocument?.id ?? null);
  const [understanding, setUnderstanding] = useState<Understanding | null>(
    initialDocument?.understanding ?? null,
  );
  const [pages, setPages] = useState<string[]>(
    initialDocument?.preview_url ? [assetUrl(initialDocument.preview_url)] : [],
  );
  const [pdfUrl, setPdfUrl] = useState(initialDocument?.pdf_url || '');
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState('');

  const generateQuotation = async () => {
    setBusy('understand');
    setError('');
    try {
      let currentUnderstanding = understanding;
      if (text.trim()) {
        const response = await api.understand(text, 'paste', profile, client);
        currentUnderstanding = response.understanding;
        setUnderstanding(currentUnderstanding);
      }
      if (!currentUnderstanding) {
        throw new Error('Add the quotation details before generating the document.');
      }

      setBusy('generate');
      const response = await api.generate(
        buildPayload(currentUnderstanding, profile, client, text, documentId));
      setDocumentId(response.document_id);
      setPdfUrl(response.pdf_url);
      setPages(response.preview_urls.map((url) => assetUrl(url)));
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
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
                  disabled={(!text.trim() && !understanding) || Boolean(busy) || !activeTemplate}>
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
          </div>
        </div>

      </div>

      <div className="lg:sticky lg:top-4 h-[calc(100vh-6rem)] min-h-[560px] flex flex-col gap-4">
        <div className="flex-1 min-h-0">
          <PreviewPane pages={pages} pdfUrl={pdfUrl ? assetUrl(pdfUrl) : undefined}
            title={understanding?.title}
            emptyHint="Add the quotation details, then generate the document to see it here." />
        </div>
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            {pdfUrl && (
              <a className="btn ml-auto" href={assetUrl(pdfUrl)} target="_blank" rel="noreferrer">
                <Download size={15} /> Download
              </a>
            )}
          </div>
          {error && <p className="text-xs text-[var(--error)]">{error}</p>}
        </div>
      </div>
    </div>
  );
}
