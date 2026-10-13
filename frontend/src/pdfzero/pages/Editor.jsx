import React, { useEffect, useCallback, useState } from 'react'
import { X } from 'lucide-react'
import toast from 'react-hot-toast'
import { usePdfStore } from '../store/pdfStore.js'
import { loadPdf, getPageBaseSize } from '../lib/pdfRenderer.js'
import EditorToolbar from '../components/editor/EditorToolbar.jsx'
import PageThumbnails from '../components/editor/PageThumbnails.jsx'
import PdfCanvas from '../components/editor/PdfCanvas.jsx'
import PropertiesPanel from '../components/editor/PropertiesPanel.jsx'
import styles from './Editor.module.css'

export default function Editor() {
  const {
    file, setFile, setPageCount, fileName, zoom, currentPage, setCurrentPage, pageCount,
    mobilePagesOpen, mobilePropertiesOpen,
    setMobilePagesOpen, closeMobilePanels,
    setZoom,
  } = usePdfStore()

  useEffect(() => {
    const send = (message) => {
      if (window.parent !== window) {
        window.parent.postMessage(message, window.location.origin)
      }
    }
    const onMessage = (event) => {
      if (event.origin !== window.location.origin || event.source !== window.parent) return
      if (event.data?.type === 'pdfzero:load'
        && event.data.bytes instanceof ArrayBuffer) {
        setFile(
          new Uint8Array(event.data.bytes),
          typeof event.data.fileName === 'string' ? event.data.fileName : 'proposal.pdf',
          event.data.bytes.byteLength,
        )
      } else if (event.data?.type === 'pdfzero:downloaded') {
        toast.success('Corrected PDF downloaded.', { id: 'pdfzero-export' })
      } else if (event.data?.type === 'pdfzero:download-error') {
        toast.error('The corrected PDF could not be downloaded.', { id: 'pdfzero-export' })
      }
    }
    window.addEventListener('message', onMessage)
    send({ type: 'pdfzero:ready' })
    return () => window.removeEventListener('message', onMessage)
  }, [setFile])
  // pdfReady gates PdfCanvas — only render after loadPdf() fully resolves
  const [pdfReady, setPdfReady] = useState(false)

  useEffect(() => {
    if (!file) { setPdfReady(false); return }
    setPdfReady(false)  // reset so PdfCanvas remounts cleanly

    loadPdf(file)
      .then(async (doc) => {
        setPageCount(doc.numPages)

        // On narrow screens, the default 100% zoom renders pages wider than
        // the viewport, forcing horizontal scroll just to read a line of text.
        // Auto-fit zoom to the available canvas width before the first paint
        // so mobile users land on a comfortably-readable view immediately.
        if (window.innerWidth <= 768) {
          try {
            const { width } = await getPageBaseSize(1)
            // .canvas has ~32px total horizontal padding (see Editor.module.css .wrapper)
            const available = window.innerWidth - 40
            const fitZoom = available / width
            setZoom(fitZoom)
          } catch (_) { /* fall back to default zoom if measurement fails */ }
        }

        // Small rAF delay so React can flush the pageCount/zoom state
        // before PdfCanvas triggers its first renderPage()
        requestAnimationFrame(() => {
          requestAnimationFrame(() => setPdfReady(true))
        })
        toast.success(`Loaded ${doc.numPages} page${doc.numPages > 1 ? 's' : ''}`)
      })
      .catch((e) => {
        toast.error('Failed to parse PDF: ' + e.message)
        if (window.parent !== window) {
          window.parent.postMessage({
            type: 'pdfzero:error',
            message: `The generated PDF could not be opened: ${e.message}`,
          }, window.location.origin)
        }
      })
  }, [file, setPageCount])

  const handleKeyDown = useCallback((e) => {
    // Don't steal keys while user is typing in a text block
    if (e.target.isContentEditable) return

    // Page navigation
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      if (currentPage < pageCount) setCurrentPage(currentPage + 1)
    }
    if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      if (currentPage > 1) setCurrentPage(currentPage - 1)
    }
  }, [currentPage, pageCount, setCurrentPage])

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  return (
    <div className={styles.page}>
      <header style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '8px 16px', background: 'var(--bg-nav)', borderBottom: '1px solid var(--brd)',
      }}>
        <strong>PDFZero · PDF editor</strong>
        <button
          onClick={() => {
            if (window.parent !== window) {
              window.parent.postMessage({ type: 'pdfzero:close' }, window.location.origin)
            }
          }}
          aria-label="Close PDF editor"
          style={{ color: 'var(--tx-1)', padding: '6px 10px' }}
        >
          <X size={16} />
        </button>
      </header>
      <EditorToolbar />

      <div className={styles.workspace}>
        {file ? (
          <>
            {/* Backdrop — tapping it closes whichever mobile drawer is open */}
            <div
              className={`${styles.backdrop} ${(mobilePagesOpen || mobilePropertiesOpen) ? styles.backdropShow : ''}`}
              onClick={closeMobilePanels}
            />

            <aside className={`${styles.leftPanel} ${mobilePagesOpen ? styles.mobileOpen : ''}`}>
              <button
                className={styles.drawerClose}
                onClick={closeMobilePanels}
                aria-label="Close pages panel"
              >
                <X size={16} />
              </button>
              <PageThumbnails />
            </aside>

            <main className={styles.canvas}>
              {/* Only mount PdfCanvas after loadPdf() has resolved */}
              {pdfReady && <PdfCanvas />}
              {!pdfReady && (
                <div className={styles.loadingCanvas}>
                  <div className={styles.loadingSpinner} />
                  <span>Loading PDF…</span>
                </div>
              )}
            </main>

            <aside className={`${styles.rightPanel} ${mobilePropertiesOpen ? styles.mobileOpen : ''}`}>
              <button
                className={styles.drawerClose}
                onClick={closeMobilePanels}
                aria-label="Close properties panel"
              >
                <X size={16} />
              </button>
              <PropertiesPanel />
            </aside>
          </>
        ) : (
          <div className={styles.emptyState}>
            <div className={styles.emptyContent}>
              <h2 className={styles.emptyTitle}>Open a PDF to start editing</h2>
              <p className={styles.emptySub}>
                The generated PDF could not be loaded. Close this editor and try again.
              </p>
            </div>
          </div>
        )}
      </div>

      {file && (
        <div className={styles.statusBar}>
          <span className={styles.statusFile}>📄 {fileName}</span>
          <span className={styles.statusCenter}>Page {currentPage} of {pageCount}</span>
          <span className={styles.statusRight}>
            <span className={styles.privacyDot} />
            <span className={styles.statusRightText}>Processed locally — never uploaded</span>
          </span>
        </div>
      )}
    </div>
  )
}
