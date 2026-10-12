import { useState } from 'react';
import { Upload, Trash, LoaderCircle, Palette, Download } from 'lucide-react';
import type { ReferenceMeta } from '../types';
import { api, openAuthenticatedAsset } from '../services/api';

interface Props {
  references: ReferenceMeta[];
  onChanged: () => void;
  onUse: (id: string) => void;
}

export function ReferencesPage({ references, onChanged, onUse }: Props) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const openPdf = async (id: string) => {
    setError('');
    try {
      await openAuthenticatedAsset(`/references/${id}/pdf`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to open the reference PDF.');
    }
  };

  const upload = async (file: File) => {
    setUploading(true);
    setError('');
    try {
      await api.uploadReference(file);
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUploading(false);
    }
  };

  const remove = async (id: string) => {
    try {
      await api.deleteReference(id);
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">Reference designs</h1>
          <p className="text-xs text-[var(--text-muted)]">
            Upload a document and quoteGEN rebuilds a clean letterhead in its style — never its wording.
          </p>
        </div>
        <label className="btn btn-primary cursor-pointer">
          {uploading ? <LoaderCircle size={15} className="spin" /> : <Upload size={15} />}
          Upload PDF
          <input type="file" accept="application/pdf" className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) void upload(f); }} />
        </label>
      </header>

      {error && <p className="text-xs text-[var(--error)]">{error}</p>}

      {references.length === 0 ? (
        <div className="card p-10 text-center text-[var(--text-dim)] space-y-2">
          <Palette size={28} className="mx-auto" />
          <p className="text-sm max-w-md mx-auto">
            Upload a reference quotation or letterhead. quoteGEN reads its colours, typography and
            layout, then rebuilds a clean design around your own business details.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {references.map((ref) => (
            <div key={ref.id} className="card p-4 space-y-3">
              <div className="flex items-start gap-2">
                <Palette size={16} className="text-[var(--accent)] mt-0.5" />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold truncate">{ref.name}</div>
                  <div className="text-xs text-[var(--text-dim)]">{fmt(ref.created_at)}</div>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <Swatch color={ref.design.tokens.primary} label="Primary" />
                <Swatch color={ref.design.tokens.accent} label="Accent" />
                <Swatch color={ref.design.tokens.text} label="Text" />
              </div>
              <div className="text-xs text-[var(--text-dim)]">
                {ref.design.font_heading} · {ref.design.font_body}
              </div>

              <div className="flex items-center gap-2">
                <button type="button" className="btn flex-1" onClick={() => onUse(ref.id)}>
                  Use design
                </button>
                <button type="button" className="btn px-2 py-1"
                  onClick={() => { void openPdf(ref.id); }} aria-label="Open reference PDF">
                  <Download size={14} />
                </button>
                <button type="button" className="btn btn-danger px-2 py-1"
                  onClick={() => void remove(ref.id)}
                  aria-label="Delete reference">
                  <Trash size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Swatch({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="w-4 h-4 rounded border border-black/20" style={{ background: color }} />
      <span className="text-[10px] text-[var(--text-dim)]">{label}</span>
    </div>
  );
}

function fmt(iso: string): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleDateString();
  } catch {
    return iso;
  }
}
