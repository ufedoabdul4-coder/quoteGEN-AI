import { useState } from 'react';
import { FileText, FileStack, Sparkles, Download, ArrowRight } from 'lucide-react';
import type { DocumentSummary } from '../types';
import { openAuthenticatedAsset } from '../services/api';

interface Props {
  documents: DocumentSummary[];
  templateCount: number;
  onCreate: () => void;
  onOpenDocuments: () => void;
  onOpenTemplates: () => void;
}

export function OverviewPage({
  documents, templateCount, onCreate, onOpenDocuments, onOpenTemplates,
}: Props) {
  const [error, setError] = useState('');
  const recent = documents.slice(0, 5);
  const openPdf = async (path: string) => {
    setError('');
    try {
      await openAuthenticatedAsset(path);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to open the PDF.');
    }
  };

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">Overview</h1>
          <p className="text-xs text-[var(--text-muted)]">
            Turn your quotation content into a document using your master template.
          </p>
        </div>
        <button type="button" className="btn btn-primary" onClick={onCreate}>
          <Sparkles size={15} /> New quotation
        </button>
      </header>
      {error && <p role="alert" className="text-sm text-[var(--error)]">{error}</p>}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <StatCard icon={FileText} label="Documents" value={documents.length}
          action={onOpenDocuments} actionLabel="View all" />
        <StatCard icon={FileStack} label="Master templates" value={templateCount}
          action={onOpenTemplates} actionLabel="Manage" />
      </div>

      <div className="card overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border)]">
          <span className="text-sm font-semibold">Recent documents</span>
          <button type="button" className="btn btn-ghost" onClick={onOpenDocuments}>
            All documents <ArrowRight size={14} />
          </button>
        </div>
        {recent.length === 0 ? (
          <div className="px-4 py-10 text-center text-sm text-[var(--text-dim)]">
            Nothing here yet. Your saved quotations will appear in this list.
          </div>
        ) : (
          <div className="divide-y divide-[var(--border)]">
            {recent.map((doc) => (
              <div key={doc.id} className="flex items-center gap-3 px-4 py-3">
                <FileText size={16} className="text-[var(--text-dim)]" />
                <div className="min-w-0 flex-1">
                  <div className="text-sm truncate">{doc.title}</div>
                  <div className="text-xs text-[var(--text-dim)]">
                    {doc.client || 'No client'} · {doc.page_count} page(s)
                  </div>
                </div>
                {doc.pdf_url && (
                  <button type="button" className="btn px-2 py-1"
                    onClick={() => { void openPdf(doc.pdf_url!); }} aria-label="Open PDF">
                    <Download size={14} />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({ icon: Icon, label, value, action, actionLabel }: {
  icon: typeof FileText;
  label: string;
  value: number;
  action?: () => void;
  actionLabel?: string;
}) {
  return (
    <div className="card p-4 space-y-2">
      <div className="flex items-center justify-between">
        <Icon size={16} className="text-[var(--gold)]" />
        {action && actionLabel && (
          <button type="button" className="btn btn-ghost px-2 py-0.5 text-xs" onClick={action}>
            {actionLabel}
          </button>
        )}
      </div>
      <div className="text-2xl font-semibold tabular-nums">{value}</div>
      <div className="text-xs text-[var(--text-dim)]">{label}</div>
    </div>
  );
}
