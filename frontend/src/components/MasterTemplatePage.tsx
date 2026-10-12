import { useEffect, useRef, useState } from 'react';
import { ExternalLink, FileUp, LoaderCircle, Trash, Upload } from 'lucide-react';
import type { TemplateMeta } from '../types';
import { api } from '../services/api';

interface Props {
  activeTemplate: TemplateMeta | null;
  templatesLoaded: boolean;
  onChanged: () => Promise<void>;
}

export function MasterTemplatePage({ activeTemplate, templatesLoaded, onChanged }: Props) {
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

      {!templatesLoaded ? (
        <div className="card flex items-center justify-center gap-3 p-10 text-sm text-[var(--text-muted)]">
          <LoaderCircle size={20} className="spin text-[var(--gold)]" />
          Checking for your saved master document…
        </div>
      ) : !activeTemplate ? (
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
            <AuthenticatedTemplatePreview
              key={`${activeTemplate.id}:${activeTemplate.updated_at}`}
              template={activeTemplate}
            />
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

function AuthenticatedTemplatePreview({ template }: { template: TemplateMeta }) {
  const [pages, setPages] = useState<string[]>([]);
  const [openUrl, setOpenUrl] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    let objectUrl = '';
    api.templatePdf(template.id).then(async (pdf) => {
      const [pdfjs, worker] = await Promise.all([
        import('pdfjs-dist'),
        import('pdfjs-dist/build/pdf.worker.min.mjs?url'),
      ]);
      pdfjs.GlobalWorkerOptions.workerSrc = worker.default;
      const data = await pdf.arrayBuffer();
      const document = await pdfjs.getDocument({ data }).promise;
      const renderedPages: string[] = [];
      for (let pageNumber = 1; pageNumber <= document.numPages; pageNumber += 1) {
        if (!active) return;
        const page = await document.getPage(pageNumber);
        const baseViewport = page.getViewport({ scale: 1 });
        const scale = Math.min(1.5, 1000 / baseViewport.width);
        const viewport = page.getViewport({ scale });
        const canvas = window.document.createElement('canvas');
        canvas.width = Math.ceil(viewport.width);
        canvas.height = Math.ceil(viewport.height);
        const context = canvas.getContext('2d');
        if (!context) throw new Error('Unable to render the master PDF preview.');
        await page.render({ canvas, canvasContext: context, viewport }).promise;
        renderedPages.push(canvas.toDataURL('image/png'));
      }
      if (!active) return;
      objectUrl = URL.createObjectURL(pdf);
      setPages(renderedPages);
      setOpenUrl(objectUrl);
    }).catch((err: unknown) => {
      if (active) setError(err instanceof Error ? err.message : 'Unable to load master PDF.');
    });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [template.id]);

  if (error) {
    return <p role="alert" className="p-6 text-center text-sm text-[var(--error)]">{error}</p>;
  }
  if (pages.length === 0) {
    return <p className="p-6 text-center text-sm text-[var(--text-muted)]">Loading master PDF…</p>;
  }
  return (
    <div className="max-h-[75vh] overflow-auto p-3 sm:p-5">
      <div className="mb-3 flex justify-end">
        <a className="btn" href={openUrl} target="_blank" rel="noreferrer">
          <ExternalLink size={14} /> Open PDF
        </a>
      </div>
      <div className="mx-auto flex max-w-4xl flex-col items-center gap-4">
        {pages.map((page, index) => (
          <img
            key={index}
            src={page}
            alt={`${template.name}, page ${index + 1}`}
            className="h-auto max-w-full border border-[var(--border)] bg-white shadow-lg"
          />
        ))}
      </div>
    </div>
  );
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
