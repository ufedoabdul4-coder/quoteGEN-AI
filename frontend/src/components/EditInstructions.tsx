import { useState } from 'react';
import { LoaderCircle, RotateCcw, Sparkles, X } from 'lucide-react';
import type { CleaningServiceType } from '../types';
import { CLEANING_SERVICES, isCleaningServiceType } from '../utils/cleaning';

export interface InstructionValues {
  kind: 'paste' | 'job';
  text: string;
  jobDescription: string;
  quotationGoal: string;
  cleaningType: CleaningServiceType;
  targetTotalNgn: string;
}

interface Props {
  original: InstructionValues;
  busy: boolean;
  error: string;
  onCancel: () => void;
  onRegenerate: (values: InstructionValues) => void;
}

export function EditInstructions({ original, busy, error, onCancel, onRegenerate }: Props) {
  const [draft, setDraft] = useState<InstructionValues>(() => ({ ...original }));

  const isJob = draft.kind === 'job';
  const target = Number(draft.targetTotalNgn);
  const targetValid = Number.isSafeInteger(target) && target > 0;
  const canRegenerate = isJob
    ? Boolean(draft.jobDescription.trim() && draft.quotationGoal.trim() && targetValid)
    : Boolean(draft.text.trim());
  const changed = JSON.stringify(draft) !== JSON.stringify(original);

  const set = <K extends keyof InstructionValues,>(key: K, value: InstructionValues[K]) =>
    setDraft((current) => ({ ...current, [key]: value }));

  return (
    <div className="fixed inset-0 z-50 bg-black/70 p-3 sm:p-6"
      role="dialog" aria-modal="true" aria-label="Edit document instructions">
      <div className="mx-auto flex h-full max-w-3xl flex-col overflow-hidden rounded-xl bg-[var(--surface)] shadow-2xl">
        <div className="flex items-start justify-between gap-4 border-b border-[var(--border)] px-4 py-3">
          <div>
            <h2 className="font-semibold">Edit Document Instructions</h2>
            <p className="text-xs text-[var(--text-muted)] mt-1">
              These are the instructions used to create this document. Correct any prices, quantities,
              dates, names, descriptions, or wording, then regenerate. The document is rebuilt with the
              same master design and template — you are not editing the PDF directly.
            </p>
          </div>
          <button type="button" className="btn" onClick={onCancel} disabled={busy}
            aria-label="Close instructions editor">
            <X size={16} /> Close
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-4 overflow-auto px-4 py-4">
          {isJob ? (
            <>
              <div>
                <label htmlFor="edit-cleaning-type" className="label">Cleaning service type</label>
                <select
                  id="edit-cleaning-type"
                  className="select"
                  value={draft.cleaningType}
                  onChange={(event) => {
                    if (isCleaningServiceType(event.target.value)) {
                      set('cleaningType', event.target.value);
                    }
                  }}
                  disabled={busy}
                >
                  {CLEANING_SERVICES.map((service) => (
                    <option key={service.value} value={service.value}>{service.label}</option>
                  ))}
                </select>
              </div>

              <div>
                <label htmlFor="edit-job-description" className="label">Job description</label>
                <textarea
                  id="edit-job-description"
                  className="textarea"
                  value={draft.jobDescription}
                  onChange={(e) => set('jobDescription', e.target.value)}
                  maxLength={10000}
                  style={{ minHeight: 190 }}
                  disabled={busy}
                />
              </div>

              <div>
                <label htmlFor="edit-quotation-goal" className="label">What should the proposal cover?</label>
                <textarea
                  id="edit-quotation-goal"
                  className="textarea"
                  value={draft.quotationGoal}
                  onChange={(e) => set('quotationGoal', e.target.value)}
                  maxLength={2000}
                  style={{ minHeight: 88 }}
                  disabled={busy}
                />
              </div>

              <div>
                <label htmlFor="edit-target-total" className="label">Target proposal total (₦)</label>
                <input
                  id="edit-target-total"
                  className="input"
                  type="number"
                  min="1"
                  max="999999999999"
                  step="1"
                  inputMode="numeric"
                  value={draft.targetTotalNgn}
                  onChange={(e) => set('targetTotalNgn', e.target.value)}
                  disabled={busy}
                />
                <p className="mt-1 text-xs text-[var(--text-muted)]">
                  This exact total is preserved; the server distributes it across the work items and
                  recalculates the line and grand totals.
                </p>
              </div>
            </>
          ) : (
            <div>
              <label htmlFor="edit-proposal-text" className="label">Proposal instructions</label>
              <textarea
                id="edit-proposal-text"
                className="textarea"
                value={draft.text}
                onChange={(e) => set('text', e.target.value)}
                placeholder="Paste or write the proposal exactly as it should read, including line items, prices and terms…"
                style={{ minHeight: 320 }}
                disabled={busy}
              />
            </div>
          )}

          {error && <p role="alert" className="text-sm text-[var(--error)]">{error}</p>}
        </div>

        <div className="flex flex-wrap items-center gap-2 border-t border-[var(--border)] px-4 py-3">
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => onRegenerate({ ...draft })}
            disabled={busy || !canRegenerate}
          >
            {busy ? <LoaderCircle size={15} className="spin" /> : <Sparkles size={15} />}
            {busy ? 'Regenerating…' : 'Regenerate PDF'}
          </button>
          <button type="button" className="btn" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-ghost ml-auto"
            onClick={() => setDraft({ ...original })}
            disabled={busy || !changed}
          >
            <RotateCcw size={15} /> Reset to original
          </button>
        </div>
      </div>
    </div>
  );
}
