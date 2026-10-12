import {
  LayoutDashboard,
  FileText,
  CirclePlus,
  FileStack,
  Building,
  CircleCheck,
  CircleAlert,
} from 'lucide-react';

export type Route = 'overview' | 'documents' | 'create' | 'templates' | 'profile';

const NAV_ITEMS = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard, group: 'Overview' },
  { id: 'documents', label: 'My documents', icon: FileText, group: 'Overview' },
  { id: 'create', label: 'Create quotation', icon: CirclePlus, group: 'Create' },
  { id: 'templates', label: 'Master templates', icon: FileStack, group: 'Create' },
  { id: 'profile', label: 'Business profile', icon: Building, group: 'Account' },
] as const;

const GROUPS = ['Overview', 'Create', 'Account'] as const;

interface Props {
  active: Route;
  onNavigate: (id: Route) => void;
  online: boolean | null;
  documentCount: number;
  templateCount: number;
  email: string | null;
  onSignOut: () => void;
}

export function Sidebar({
  active, onNavigate, online, documentCount, templateCount, email, onSignOut,
}: Props) {
  return (
    <aside className="hidden md:flex md:flex-col w-64 shrink-0 h-screen sticky top-0 border-r border-[var(--border)] bg-[var(--surface)]">
      <div className="px-5 py-5 border-b border-[var(--border)]">
        <div className="flex items-center gap-2">
          <span className="text-lg font-semibold tracking-tight">quoteGEN</span>
          <span className="chip chip-gold">AI</span>
        </div>
        <p className="text-xs text-[var(--text-dim)] mt-1">Premium quotation studio</p>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-5">
        {GROUPS.map((group) => (
          <div key={group}>
            <div className="eyebrow px-2 mb-1.5">{group}</div>
            <div className="space-y-1">
              {NAV_ITEMS.filter((item) => item.group === group).map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => onNavigate(item.id)}
                    className={`nav-item ${active === item.id ? 'active' : ''}`}
                  >
                    <Icon size={17} />
                    <span>{item.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      <div className="px-4 py-4 border-t border-[var(--border)] space-y-2">
        <StatusRow online={online} />
        <div className="text-xs text-[var(--text-dim)]">{documentCount} document(s)</div>
        <div className="text-xs text-[var(--text-dim)]">{templateCount} template(s)</div>
        {email && (
          <div className="flex items-center justify-between gap-2 pt-2">
            <span className="text-xs text-[var(--text-dim)] truncate">{email}</span>
            <button type="button" className="btn btn-ghost text-xs" onClick={onSignOut}>
              Sign out
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}

export function StatusRow({ online }: { online: boolean | null }) {
  if (online === null) {
    return <span className="chip"><CircleAlert size={12} /> Checking backend…</span>;
  }
  return online ? (
    <span className="chip chip-ok"><CircleCheck size={12} /> Backend online</span>
  ) : (
    <span className="chip chip-error"><CircleAlert size={12} /> Backend offline</span>
  );
}
