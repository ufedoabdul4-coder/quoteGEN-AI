import { useRef, useState } from 'react';
import { FileUp, LoaderCircle, Trash, Upload } from 'lucide-react';
import type { TemplateMeta } from '../types';
import { api, assetUrl } from '../services/api';

interface Props {
  activeTemplate: TemplateMeta | null;
  onChanged: () => Promise<void>;
}

export function MasterTemplatePage({ activeTemplate, onChanged }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState('');

  const upload = async (file: File) => {
    setUploading(true);
    setError('');
    try {
      if (activeTemplate) await api.replaceTemplate(activeTemplate.id, file);
      else await api.uploadTemplate(file);
      await onChanged();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setUploading(false);
    }
  };

  const remove = async () => {
    if (!activeTemplate) return;
    setError('');
    try {
      await api.deleteTemplate(activeTemplate.id);
      await onChanged();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const acceptFiles = (files: FileList | null) => {
    const file = files?.[0];
    if (file) void upload(file);
  };

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">Master document</h1>
          <p className="text-xs text-[var(--text-muted)]">
            Your uploaded PDF supplies the design for every generated quotation.
          </p>
        </div>
        {activeTemplate && (
          <button type="button" className="btn btn-primary"
            onClick={() => inputRef.current?.click()} disabled={uploading}>
            {uploading ? <LoaderCircle size={15} className="spin" /> : <Upload size={15} />}
            Change document
          </button>
        )}
        <input ref={inputRef} type="file" accept="application/pdf,.pdf" className="hidden"
          onChange={(event) => {
            acceptFiles(event.target.files);
            event.target.value = '';
          }} />
      </header>

      {!activeTemplate ? (
        <button type="button"
          className={`card w-full border-dashed p-10 text-center transition ${dragging ? 'border-[var(--gold)] bg-[var(--gold-soft)]' : ''}`}
          onClick={() => inputRef.current?.click()}
          onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            acceptFiles(event.dataTransfer.files);
          }}>
          {uploading
            ? <LoaderCircle size={28} className="mx-auto mb-2 spin text-[var(--gold)]" />
            : <FileUp size={28} className="mx-auto mb-2 text-[var(--gold)]" />}
          <span className="text-sm font-semibold">
            {uploading ? 'Uploading your master document…' : 'Drop your master PDF here or browse'}
          </span>
          <span className="block mt-1 text-xs text-[var(--text-dim)]">
            It will be used automatically for new quotations.
          </span>
        </button>
      ) : (
        <article className="card overflow-hidden">
          <div className="flex flex-wrap items-center gap-2 p-4">
            <div className="min-w-0 flex-1">
              <h2 className="truncate text-sm font-semibold">{activeTemplate.name}</h2>
              <p className="mt-1 truncate text-xs text-[var(--text-dim)]">
                {activeTemplate.source_filename} · {formatSize(activeTemplate.size_bytes)} ·{' '}
                {activeTemplate.page_count} page(s)
              </p>
            </div>
            <span className={`chip ${activeTemplate.status === 'ready' ? 'chip-ok' : 'chip-error'}`}>
              {activeTemplate.status}
            </span>
            <button type="button" className="btn btn-danger px-2"
              onClick={() => void remove()} aria-label="Remove master document">
              <Trash size={14} />
            </button>
          </div>
          <div className="border-y border-[var(--border)] bg-[var(--surface-2)]">
            <iframe title={`Preview of ${activeTemplate.name}`}
              src={assetUrl(`/templates/${activeTemplate.id}/pdf`)}
              className="h-[min(75vh,900px)] w-full" />
          </div>
          <button type="button"
            className={`w-full border-dashed p-4 text-center transition ${dragging ? 'bg-[var(--gold-soft)]' : ''}`}
            onClick={() => inputRef.current?.click()}
            onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              acceptFiles(event.dataTransfer.files);
            }}
            disabled={uploading}>
            <span className="text-xs text-[var(--text-dim)]">
              {uploading ? 'Replacing master document…' : 'Drop a replacement PDF here'}
            </span>
          </button>
        </article>
      )}

      {error && <p role="alert" className="text-xs text-[var(--error)]">{error}</p>}
    </div>
  );
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
