import { useEffect, useState } from 'react';
import { ChevronLeft, ChevronRight, Download, Eye } from 'lucide-react';
import {
  authenticatedAsset, downloadAuthenticatedAsset,
} from '../services/api';

interface Props {
  pages: string[];
  pdfUrl?: string;
  title?: string;
  emptyHint?: string;
}

export function PreviewPane({ pages, pdfUrl, title, emptyHint }: Props) {
  const [index, setIndex] = useState(0);
  const [loadedPages, setLoadedPages] = useState<{ key: string; urls: string[] } | null>(null);
  const [assetError, setAssetError] = useState<{ key: string; message: string } | null>(null);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const pageKey = pages.join('|');
  const currentPages = loadedPages?.key === pageKey ? loadedPages.urls : [];
  const currentError = assetError?.key === pageKey ? assetError.message : '';
  const total = pages.length;
  const safeIndex = Math.min(index, Math.max(0, total - 1));

  useEffect(() => {
    let active = true;
    const objectUrls: string[] = [];
    const paths = pageKey ? pageKey.split('|') : [];
    Promise.all(paths.map(async (path) => {
      const blob = await authenticatedAsset(path);
      if (!active) return '';
      const url = URL.createObjectURL(blob);
      objectUrls.push(url);
      return url;
    })).then((urls) => {
      if (active) setLoadedPages({ key: pageKey, urls });
    }).catch((error: unknown) => {
      if (active) {
        setAssetError({
          key: pageKey,
          message: error instanceof Error ? error.message : 'Unable to load document preview.',
        });
      }
    });
    return () => {
      active = false;
      objectUrls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [pageKey]);

  const downloadPdf = async () => {
    if (!pdfUrl) return;
    setDownloadingPdf(true);
    setAssetError(null);
    try {
      await downloadAuthenticatedAsset(pdfUrl, `${title || 'quoteGEN-proposal'}.pdf`);
    } catch (error) {
      setAssetError({
        key: pageKey,
        message: error instanceof Error ? error.message : 'Unable to download the PDF.',
      });
    } finally {
      setDownloadingPdf(false);
    }
  };

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
            <button type="button" className="btn px-2 py-1 ml-1" onClick={() => { void downloadPdf(); }}
              disabled={downloadingPdf}>
              <Download size={15} />
              <span className="hidden sm:inline">PDF</span>
            </button>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-auto bg-[var(--bg)] p-4 flex justify-center">
        {currentError ? (
          <p role="alert" className="text-sm text-[var(--error)]">{currentError}</p>
        ) : total === 0 ? (
          <div className="flex flex-col items-center justify-center text-center text-[var(--text-dim)] gap-2 h-full min-h-[240px]">
            <Eye size={26} />
            <p className="text-sm max-w-xs">{emptyHint || 'A preview will appear here.'}</p>
          </div>
        ) : currentPages.length !== total ? (
          <p className="text-sm text-[var(--text-muted)]">Loading quotation preview…</p>
        ) : (
          <img
            key={safeIndex}
            src={currentPages[safeIndex]}
            alt={`Page ${safeIndex + 1}`}
            className="max-w-full h-auto border border-[var(--border)] shadow-lg"
            style={{ background: '#fff' }}
          />
        )}
      </div>
    </div>
  );
}
