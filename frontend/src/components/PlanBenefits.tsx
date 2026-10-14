import { useEffect } from 'react';
import { Check, LoaderCircle, Sparkles, X, Zap } from 'lucide-react';

interface Props {
  open: boolean;
  price: number;
  autoRenew: boolean;
  busy: boolean;
  error: string;
  onClose: () => void;
  onConfirm: () => void;
}

const BENEFITS = [
  'Unlimited proposal generation — no daily or 30-day free limits',
  'Every proposal rendered with your master template',
  'Download unlimited proposal PDFs',
  'Cancel anytime from your Flutterwave subscription',
];

export function PlanBenefits({
  open, price, autoRenew, busy, error, onClose, onConfirm,
}: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="plan-benefits-title"
      onClick={onClose}
    >
      <div
        className="card w-full max-w-md space-y-4 p-5"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 id="plan-benefits-title" className="flex items-center gap-2 text-lg font-semibold">
              <Sparkles size={18} className="text-[var(--gold)]" /> Go Unlimited
            </h2>
            <p className="mt-1 text-xs text-[var(--text-muted)]">
              Everything you get with the monthly plan.
            </p>
          </div>
          <button
            type="button"
            className="btn btn-ghost px-2 py-1"
            onClick={onClose}
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>

        <div className="flex items-baseline gap-1">
          <span className="text-2xl font-semibold tabular-nums">
            ₦{price.toLocaleString('en-NG')}
          </span>
          <span className="text-sm text-[var(--text-muted)]">/month</span>
        </div>

        <ul className="space-y-2">
          {BENEFITS.map((benefit) => (
            <li key={benefit} className="flex items-start gap-2 text-sm">
              <Check size={16} className="mt-0.5 shrink-0 text-[var(--ok)]" />
              <span>{benefit}</span>
            </li>
          ))}
        </ul>

        <p className="text-xs text-[var(--text-muted)]">
          {autoRenew
            ? 'Billed automatically every month on today’s date until you cancel. Flutterwave emails a reminder before each charge. Card payment only.'
            : 'One-time payment for one month of unlimited proposals. No auto-renew.'}
        </p>

        {error && (
          <p role="alert" className="text-xs text-[var(--error)]">{error}</p>
        )}

        <button
          type="button"
          className="btn btn-primary w-full"
          onClick={onConfirm}
          disabled={busy}
        >
          {busy ? <LoaderCircle size={15} className="spin" /> : <Zap size={15} />}
          {busy
            ? 'Opening checkout…'
            : `Subscribe — ₦${price.toLocaleString('en-NG')}/month`}
        </button>
      </div>
    </div>
  );
}
