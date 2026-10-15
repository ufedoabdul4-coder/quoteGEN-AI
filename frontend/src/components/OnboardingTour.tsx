import { useEffect, useState } from 'react';
import { ClipboardList, FileStack, PencilLine, Sparkles, X } from 'lucide-react';
import type { Route } from './Sidebar';

interface Props {
  open: boolean;
  onClose: () => void;
  /** Called on the final step so the user lands on the right page. */
  onFinish: (route: Route) => void;
}

const STEPS = [
  {
    icon: Sparkles,
    title: 'Welcome to quoteGEN AI',
    body: 'You turn job notes into branded quotation PDFs. This short tour shows the three ways to get started — it takes 30 seconds.',
  },
  {
    icon: FileStack,
    title: 'First: add your master template',
    body: 'Upload one master document (your branded quotation). Every proposal you generate is rendered in that exact design, so set this up first.',
  },
  {
    icon: ClipboardList,
    title: 'Then: Describe a job',
    body: 'If you have the scope of the project but not a full prompt — rooms, areas, quantities — pick "Describe a job" and we draft the quotation for you.',
  },
  {
    icon: PencilLine,
    title: 'Or: Write a proposal',
    body: 'If you already have a full text prompt you want turned into a quotation document, use "Write a proposal" and paste it in.',
  },
];

export function OnboardingTour({ open, onClose, onFinish }: Props) {
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  const current = STEPS[step];
  const Icon = current.icon;
  const isLast = step === STEPS.length - 1;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Getting started tour"
      onClick={onClose}
    >
      <div className="card w-full max-w-md p-5" onClick={(event) => event.stopPropagation()}>
        <div className="flex items-start justify-between gap-3">
          <span className="chip chip-gold"><Icon size={14} /></span>
          <button type="button" className="btn btn-ghost p-1" aria-label="Close tour" onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        <h2 className="mt-4 text-lg font-semibold">{current.title}</h2>
        <p className="mt-2 text-sm text-[var(--text-muted)] leading-relaxed">{current.body}</p>

        <div className="mt-5 flex items-center gap-1.5" aria-hidden="true">
          {STEPS.map((_, index) => (
            <span
              key={index}
              className="h-1.5 flex-1 rounded-full"
              style={{ background: index <= step ? 'var(--gold)' : 'var(--border-strong)' }}
            />
          ))}
        </div>

        <div className="mt-5 flex items-center justify-between gap-3">
          <button type="button" className="btn btn-ghost text-sm" onClick={onClose}>
            Skip
          </button>
          <div className="flex items-center gap-2">
            {step > 0 && (
              <button type="button" className="btn text-sm" onClick={() => setStep(step - 1)}>
                Back
              </button>
            )}
            {isLast ? (
              <button type="button" className="btn btn-primary text-sm" onClick={() => onFinish('templates')}>
                Set up my template
              </button>
            ) : (
              <button type="button" className="btn btn-primary text-sm" onClick={() => setStep(step + 1)}>
                Next
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
