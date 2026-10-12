import { useState } from 'react';
import { FileText, Download, Trash, Pencil, CircleCheck, TriangleAlert, CircleAlert } from 'lucide-react';
import type { DocumentSummary } from '../types';
import { openAuthenticatedAsset } from '../services/api';

const STATUS: Record<string, { label: string; cls: string; icon: typeof CircleCheck }> = {
  ready: { label: 'Ready', cls: 'chip-ok', icon: CircleCheck },
  needs_review: { label: 'Needs review', cls: 'chip-warn', icon: TriangleAlert },
  draft: { label: 'Draft', cls: '', icon: CircleAlert },
};

interface Props {
  documents: DocumentSummary[];
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
  onCreate: () => void;
}

export function DocumentsPage({ documents, onOpen, onDelete, onCreate }: Props) {
  const [error, setError] = useState('');
  const openPdf = async (path: string) => {
    setError('');
    try {
      await openAuthenticatedAsset(path);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to open the PDF.');
    }
  };

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">My documents</h1>
          <p className="text-xs text-[var(--text-muted)]">
            {documents.length} saved quotation{documents.length === 1 ? '' : 's'}
          </p>
        </div>
        <button type="button" className="btn btn-primary" onClick={onCreate}>
          New quotation
        </button>
      </header>
      {error && <p role="alert" className="text-sm text-[var(--error)]">{error}</p>}

      {documents.length === 0 ? (
        <div className="card p-10 text-center text-[var(--text-dim)] space-y-2">
          <FileText size={28} className="mx-auto" />
          <p className="text-sm">No documents yet. Create your first quotation to see it here.</p>
        </div>
      ) : (
        <div className="card divide-y divide-[var(--border)] overflow-hidden">
          {documents.map((doc) => {
            const status = STATUS[doc.status] || STATUS.draft;
            const StatusIcon = status.icon;
            return (
              <div key={doc.id}
                className="flex items-center gap-3 px-4 py-3 hover:bg-[var(--surface-2)] transition">
                <FileText size={18} className="text-[var(--text-dim)] shrink-0" />
                <button type="button" onClick={() => onOpen(doc.id)}
                  className="min-w-0 flex-1 text-left" aria-label={`Edit ${doc.title}`}>
                  <div className="text-sm font-semibold truncate">{doc.title}</div>
                  <div className="text-xs text-[var(--text-dim)] truncate">
                    {doc.client || 'No client'} · {doc.page_count} page(s) · {fmt(doc.updated_at)}
                  </div>
                </button>
                <span className={`chip ${status.cls}`}>
                  <StatusIcon size={12} /> {status.label}
                </span>
                <button type="button" className="btn px-2 py-1"
                  onClick={() => onOpen(doc.id)} aria-label="Edit quotation">
                  <Pencil size={14} />
                </button>
                {doc.pdf_url && (
                  <button type="button" className="btn px-2 py-1"
                    onClick={() => { void openPdf(doc.pdf_url!); }} aria-label="Open PDF">
                    <Download size={14} />
                  </button>
                )}
                <button type="button" className="btn btn-danger px-2 py-1"
                  onClick={() => onDelete(doc.id)} aria-label="Delete document">
                  <Trash size={14} />
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function fmt(iso: string): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}
