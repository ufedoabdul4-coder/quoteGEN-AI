import { CircleCheck, CircleAlert, TriangleAlert, Info } from 'lucide-react';
import type { ValidationFinding, ValidationReport } from '../types';

const ICONS: Record<string, typeof Info> = {
  error: CircleAlert,
  warning: TriangleAlert,
  info: Info,
};

export function ValidationPanel({ report }: { report: ValidationReport | null }) {
  if (!report) return null;

  const order: Record<string, number> = { error: 0, warning: 1, info: 2 };
  const findings: ValidationFinding[] = [...report.findings]
    .sort((a, b) => (order[a.level] ?? 3) - (order[b.level] ?? 3));

  return (
    <div className="panel p-4 space-y-3">
      <div className="flex items-center justify-between">
        <span className="eyebrow">Checks</span>
        {report.ok ? (
          <span className="chip chip-ok"><CircleCheck size={12} /> Ready</span>
        ) : (
          <span className="chip chip-error"><CircleAlert size={12} /> Needs review</span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Stat label="Pages" value={String(report.page_count)} />
        <Stat label="Priced lines" value={String(report.pricing_rows)} />
        <Stat label="Computed" value={formatMoney(report.computed_total)} />
        <Stat label="Stated" value={formatMoney(report.stated_total)} />
      </div>

      {findings.length === 0 ? (
        <p className="text-xs text-[var(--ok)] flex items-center gap-1.5">
          <CircleCheck size={13} /> No problems found in the rendered PDF.
        </p>
      ) : (
        <ul className="space-y-2.5">
          {findings.map((finding, index) => {
            const Icon = ICONS[finding.level] || Info;
            return (
              <li key={`${finding.code}-${index}`} className="flex gap-2 text-xs">
                <Icon size={14} className="mt-0.5 shrink-0" />
                <div>
                  <p className="leading-snug">{finding.message}</p>
                  {finding.detail.length > 0 && (
                    <ul className="mt-1 space-y-0.5 text-[var(--text-dim)]">
                      {finding.detail.map((line, i) => (
                        <li key={i} className="truncate" title={line}>{line}</li>
                      ))}
                    </ul>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-[var(--border)] bg-[var(--surface)] px-2.5 py-1.5">
      <div className="text-[10px] uppercase tracking-wide text-[var(--text-dim)]">{label}</div>
      <div className="text-sm font-semibold tabular-nums">{value}</div>
    </div>
  );
}

function formatMoney(value: number | null): string {
  if (value === null || value === undefined) return '—';
  return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
