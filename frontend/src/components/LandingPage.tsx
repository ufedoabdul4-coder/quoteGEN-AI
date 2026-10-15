import {
  ArrowRight, Check, ClipboardList, FileStack, FileText, MailPlus, PencilLine,
  ShieldCheck, Sparkles, Smartphone,
} from 'lucide-react';
import type { Route } from './Sidebar';

export type GatedIntent = Route | 'upgrade';

interface Props {
  onSignIn: () => void;
  onGetStarted: () => void;
  onProtected: (intent: GatedIntent, label: string) => void;
}

const STEPS = [
  {
    icon: FileStack,
    title: '1. Add your master template',
    body: 'Upload one branded master document once. Every quotation is rendered in that exact style — logo, colours and layout preserved.',
  },
  {
    icon: ClipboardList,
    title: '2. Describe a job',
    body: 'Have the scope of the project but not a full prompt? Describe the rooms, areas and work. We draft the quotation for you.',
  },
  {
    icon: PencilLine,
    title: '3. Write a proposal',
    body: 'Already have the full text? Paste your notes or Markdown and we turn it into an accurate, client-ready quotation PDF.',
  },
];

const FEATURES = [
  { icon: FileStack, title: 'Master templates', body: 'Keep your brand consistent across every proposal.' },
  { icon: ClipboardList, title: 'Describe a job', body: 'Turn a scope into a priced quotation automatically.' },
  { icon: PencilLine, title: 'Write a proposal', body: 'Paste raw notes or Markdown and get a polished PDF.' },
  { icon: FileText, title: 'My documents', body: 'Every proposal saved and ready to resend.' },
];

export function LandingPage({ onSignIn, onGetStarted, onProtected }: Props) {
  return (
    <div className="min-h-screen bg-[var(--bg)]">
      <header className="sticky top-0 z-20 border-b border-[var(--border)] bg-[var(--surface)]/95 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-3 px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-lg">quoteGEN</span>
            <span className="chip chip-gold">AI</span>
          </div>
          <div className="flex items-center gap-2">
            <button type="button" className="btn btn-ghost text-sm" onClick={onSignIn}>Sign in</button>
            <button type="button" className="btn btn-primary text-sm" onClick={onGetStarted}>
              Get started
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4">
        <section className="py-12 sm:py-20 text-center">
          <span className="chip chip-gold mb-4"><Sparkles size={12} /> AI quotation studio</span>
          <h1 className="text-3xl sm:text-5xl font-semibold tracking-tight max-w-3xl mx-auto">
            From raw notes to a client-ready quotation in minutes
          </h1>
          <p className="mt-4 text-[var(--text-muted)] max-w-2xl mx-auto">
            quoteGEN AI understands your job scope or pasted text and renders accurate, branded
            quotation PDFs — in your own master design.
          </p>
          <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => onProtected('create', 'Create a free account to start your first proposal.')}
            >
              Create your first proposal <ArrowRight size={16} />
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => onProtected('templates', 'Create a free account to upload your master template.')}
            >
              Upload a master template
            </button>
          </div>
          <p className="mt-4 text-xs text-[var(--text-dim)]">
            Free plan includes 3 quotations per day. No card required.
          </p>
        </section>

        <section className="pb-12 sm:pb-16">
          <div className="eyebrow text-center mb-5">How it works</div>
          <div className="grid gap-4 sm:grid-cols-3">
            {STEPS.map((step) => {
              const Icon = step.icon;
              return (
                <div key={step.title} className="card p-5">
                  <span className="chip chip-gold mb-3"><Icon size={14} /></span>
                  <h2 className="font-semibold">{step.title}</h2>
                  <p className="mt-1 text-sm text-[var(--text-muted)] leading-relaxed">{step.body}</p>
                </div>
              );
            })}
          </div>
        </section>

        <section className="pb-12 sm:pb-16">
          <div className="eyebrow text-center mb-5">Everything you need</div>
          <div className="grid gap-4 sm:grid-cols-2">
            {FEATURES.map((feature) => {
              const Icon = feature.icon;
              const intent: GatedIntent = feature.title === 'Master templates' ? 'templates'
                : feature.title === 'My documents' ? 'documents' : 'create';
              return (
                <button
                  key={feature.title}
                  type="button"
                  className="card p-5 text-left hover:border-[var(--border-strong)] transition"
                  onClick={() => onProtected(intent, `Create a free account to use ${feature.title}.`)}
                >
                  <div className="flex items-center gap-2">
                    <Icon size={16} className="text-[var(--gold)]" />
                    <span className="font-semibold">{feature.title}</span>
                    <ArrowRight size={14} className="ml-auto text-[var(--text-dim)]" />
                  </div>
                  <p className="mt-1 text-sm text-[var(--text-muted)]">{feature.body}</p>
                </button>
              );
            })}
          </div>
        </section>

        <section className="pb-12 sm:pb-16">
          <div className="card p-6 sm:p-8 grid gap-6 sm:grid-cols-[1.4fr_1fr] sm:items-center">
            <div>
              <h2 className="text-xl font-semibold">Need more than 3 quotes a day?</h2>
              <p className="mt-2 text-sm text-[var(--text-muted)]">
                The Unlimited plan removes daily limits and renews monthly. You will always see the
                full price and confirm before any payment is taken.
              </p>
              <ul className="mt-4 space-y-1.5 text-sm text-[var(--text-muted)]">
                <li className="flex items-center gap-2"><Check size={15} className="text-[var(--ok)]" /> Unlimited quotations</li>
                <li className="flex items-center gap-2"><Check size={15} className="text-[var(--ok)]" /> Priority generation</li>
                <li className="flex items-center gap-2"><Check size={15} className="text-[var(--ok)]" /> Cancel anytime</li>
              </ul>
            </div>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => onProtected('upgrade', 'Create an account to see the Unlimited plan.')}
            >
              See the Unlimited plan
            </button>
          </div>
        </section>

        <section className="pb-16 grid gap-4 sm:grid-cols-3 text-sm text-[var(--text-muted)]">
          <div className="flex items-start gap-2">
            <ShieldCheck size={16} className="text-[var(--gold)] shrink-0 mt-0.5" />
            <span>Your documents stay private to your account.</span>
          </div>
          <div className="flex items-start gap-2">
            <Smartphone size={16} className="text-[var(--gold)] shrink-0 mt-0.5" />
            <span>Installable on your phone as a full-screen app.</span>
          </div>
          <div className="flex items-start gap-2">
            <MailPlus size={16} className="text-[var(--gold)] shrink-0 mt-0.5" />
            <span>Free to start — sign up with just your email.</span>
          </div>
        </section>
      </main>

      <footer className="border-t border-[var(--border)] py-6">
        <div className="mx-auto max-w-5xl px-4 flex flex-wrap items-center justify-between gap-3 text-xs text-[var(--text-dim)]">
          <span>quoteGEN AI — Premium proposal studio</span>
          <button type="button" className="btn btn-ghost text-xs" onClick={onGetStarted}>
            Create free account
          </button>
        </div>
      </footer>
    </div>
  );
}
