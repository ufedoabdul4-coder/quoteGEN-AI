import { useState } from 'react';
import { FileText, FileStack, Sparkles, Download, ArrowRight, LoaderCircle, Zap } from 'lucide-react';
import type { BillingStatus, DocumentSummary } from '../types';
import { openAuthenticatedAsset } from '../services/api';
import { PlanBenefits } from './PlanBenefits';

interface Props {
  documents: DocumentSummary[];
  billingStatus: BillingStatus | null;
  billingLoadError: string;
  onRetryBilling: () => void;
  templateCount: number | null;
  onCreate: () => void;
  onOpenDocuments: () => void;
  onOpenTemplates: () => void;
  onUpgrade: () => void;
  upgradeBusy: boolean;
  upgradeError: string;
}

export function OverviewPage({
  documents, billingStatus, billingLoadError, onRetryBilling, templateCount,
  onCreate, onOpenDocuments, onOpenTemplates,
  onUpgrade, upgradeBusy, upgradeError,
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
            Turn a job brief into a detailed, priced proposal using your master template.
          </p>
        </div>
        <button type="button" className="btn btn-primary" onClick={onCreate}>
          <Sparkles size={15} /> New proposal
        </button>
      </header>
      {error && <p role="alert" className="text-sm text-[var(--error)]">{error}</p>}

      <UsageCard
        status={billingStatus}
        error={billingLoadError}
        onRetry={onRetryBilling}
        onUpgrade={onUpgrade}
        upgradeBusy={upgradeBusy}
        upgradeError={upgradeError}
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <StatCard icon={FileText} label="Documents" value={documents.length}
          action={onOpenDocuments} actionLabel="View all" />
        <StatCard icon={FileStack} label="Master templates" value={templateCount ?? '—'}
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
            Nothing here yet. Your saved proposals will appear in this list.
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

function UsageCard({
  status, error, onRetry, onUpgrade, upgradeBusy, upgradeError,
}: {
  status: BillingStatus | null;
  error: string;
  onRetry: () => void;
  onUpgrade: () => void;
  upgradeBusy: boolean;
  upgradeError: string;
}) {
  const [showBenefits, setShowBenefits] = useState(false);
  const autoRenew = status?.monthly_plan_auto_renew ?? false;

  if (!status) {
    return (
      <section className="card flex flex-wrap items-center justify-between gap-3 p-4 text-sm text-[var(--text-muted)]" aria-label="PDF generation usage">
        <span>{error || 'Loading PDF generation usage…'}</span>
        {error && <button type="button" className="btn" onClick={onRetry}>Retry</button>}
      </section>
    );
  }
  return (
    <section className="card p-4 space-y-3" aria-label="PDF generation usage">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold">PDF generation usage</h2>
          <p className="mt-1 text-xs text-[var(--text-muted)]">
            {status.pdfs_generated_today} PDF{status.pdfs_generated_today === 1 ? '' : 's'} generated today
          </p>
        </div>
        {status.monthly_plan_active && (
          <span className="chip chip-gold"><Sparkles size={12} /> Unlimited</span>
        )}
      </div>
      {status.monthly_plan_active ? (
        <p className="text-sm text-[var(--ok)]">
          Unlimited generations active until{' '}
          {status.paid_until ? new Date(status.paid_until).toLocaleDateString() : 'the end of your plan'}
          {autoRenew ? ' — renews monthly.' : '.'}
        </p>
      ) : (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-[var(--text-muted)]">
            <span>
              Rolling 30-day free usage: {status.free_used} / {status.free_limit}
            </span>
            <span>
              Free PDFs today (UTC): {status.free_used_today} / {status.free_daily_limit}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => setShowBenefits(true)}
              disabled={upgradeBusy}
            >
              {upgradeBusy ? <LoaderCircle size={15} className="spin" /> : <Zap size={15} />}
              {upgradeBusy ? 'Opening checkout…' : 'Want unlimited? Click here'}
            </button>
            <span className="text-xs text-[var(--text-muted)]">
              ₦{status.monthly_price_ngn.toLocaleString('en-NG')}/month
              {autoRenew ? ' · renews monthly' : ' · one-time, no auto-renew'}.
            </span>
          </div>
          {upgradeError && !showBenefits && (
            <p role="alert" className="text-xs text-[var(--error)]">{upgradeError}</p>
          )}
        </div>
      )}

      <PlanBenefits
        open={showBenefits}
        price={status.monthly_price_ngn}
        autoRenew={autoRenew}
        busy={upgradeBusy}
        error={upgradeError}
        onClose={() => setShowBenefits(false)}
        onConfirm={onUpgrade}
      />
    </section>
  );
}

function StatCard({ icon: Icon, label, value, action, actionLabel }: {
  icon: typeof FileText;
  label: string;
  value: number | string;
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
