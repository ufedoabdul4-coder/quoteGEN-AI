import { useState } from 'react';
import { ChevronLeft, ChevronRight, Download, Eye } from 'lucide-react';

interface Props {
  pages: string[];
  pdfUrl?: string;
  title?: string;
  emptyHint?: string;
}

export function PreviewPane({ pages, pdfUrl, title, emptyHint }: Props) {
  const [index, setIndex] = useState(0);
  const total = pages.length;
  const safeIndex = Math.min(index, Math.max(0, total - 1));

  return (
    <div className="panel flex flex-col h-full overflow-hidden">
      <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-[var(--border)]">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Eye size={15} />
          <span>Preview</span>
          {total > 0 && <span className="chip">{title || 'Document'}</span>}
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            className="btn btn-ghost px-2 py-1"
            onClick={() => setIndex((i) => Math.max(0, i - 1))}
            disabled={safeIndex <= 0}
            aria-label="Previous page"
          >
            <ChevronLeft size={16} />
          </button>
          <span className="text-xs text-[var(--text-muted)] tabular-nums">
            {total === 0 ? '0 / 0' : `${safeIndex + 1} / ${total}`}
          </span>
          <button
            type="button"
            className="btn btn-ghost px-2 py-1"
            onClick={() => setIndex((i) => Math.min(total - 1, i + 1))}
            disabled={safeIndex >= total - 1}
            aria-label="Next page"
          >
            <ChevronRight size={16} />
          </button>
          {pdfUrl && (
            <a className="btn px-2 py-1 ml-1" href={pdfUrl} target="_blank" rel="noreferrer">
              <Download size={15} />
              <span className="hidden sm:inline">PDF</span>
            </a>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-auto bg-[var(--bg)] p-4 flex justify-center">
        {total === 0 ? (
          <div className="flex flex-col items-center justify-center text-center text-[var(--text-dim)] gap-2 h-full min-h-[240px]">
            <Eye size={26} />
            <p className="text-sm max-w-xs">{emptyHint || 'A preview will appear here.'}</p>
          </div>
        ) : (
          <img
            key={safeIndex}
            src={pages[safeIndex]}
            alt={`Page ${safeIndex + 1}`}
            className="max-w-full h-auto border border-[var(--border)] shadow-lg"
            style={{ background: '#fff' }}
          />
        )}
      </div>
    </div>
  );
}
