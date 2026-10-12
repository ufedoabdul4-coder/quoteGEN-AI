import { useEffect, useState } from 'react';
import {
  LayoutDashboard, FileText, CirclePlus, Building, FileStack,
} from 'lucide-react';
import type {
  BusinessProfile, DocumentRecord, DocumentSummary, TemplateMeta,
} from './types';
import { api } from './services/api';
import { Sidebar, StatusRow } from './components/Sidebar';
import type { Route } from './components/Sidebar';
import { OverviewPage } from './components/OverviewPage';
import { DocumentsPage } from './components/DocumentsPage';
import { CreateQuotation } from './components/CreateQuotation';
import { ProfilePage } from './components/ProfilePage';
import { MasterTemplatePage } from './components/MasterTemplatePage';
import { LoginPage } from './components/LoginPage';
import { useAuth } from './services/auth';

const EMPTY_PROFILE: BusinessProfile = {
  name: '', phone: '', email: '', website: '', address: '', logo_data_url: null,
};

const MOBILE_NAV: { id: Route; label: string; icon: typeof LayoutDashboard }[] = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'documents', label: 'Documents', icon: FileText },
  { id: 'create', label: 'Create', icon: CirclePlus },
  { id: 'templates', label: 'Templates', icon: FileStack },
  { id: 'profile', label: 'Profile', icon: Building },
];

export default function App() {
  const { configured, ready, session, email, signOut } = useAuth();
  const userId = session?.user.id;
  const [route, setRoute] = useState<Route>('overview');
  const [online, setOnline] = useState<boolean | null>(null);
  const [healthAttempt, setHealthAttempt] = useState(0);
  const [profile, setProfile] = useState<BusinessProfile>(EMPTY_PROFILE);
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [templates, setTemplates] = useState<TemplateMeta[]>([]);
  const [activeTemplate, setActiveTemplate] = useState<TemplateMeta | null>(null);
  const [activeDocument, setActiveDocument] = useState<DocumentRecord | null>(null);
  const [signOutError, setSignOutError] = useState('');

  const handleSignOut = async () => {
    setSignOutError('');
    try {
      await signOut();
    } catch (error) {
      setSignOutError(error instanceof Error ? error.message : 'Unable to sign out.');
    }
  };

  const loadDocuments = async () => {
    try {
      setDocuments(await api.documents());
    } catch {
      setDocuments([]);
    }
  };

  const loadTemplates = async () => {
    try {
      const [loadedTemplates, active] = await Promise.all([
        api.templates(), api.activeTemplate(),
      ]);
      setTemplates(loadedTemplates);
      setActiveTemplate(active);
    } catch {
      setTemplates([]);
      setActiveTemplate(null);
    }
  };

  useEffect(() => {
    let active = true;
    api.health().then(() => {
      if (active) setOnline(true);
    }).catch(() => {
      if (active) setOnline(false);
    });
    return () => { active = false; };
  }, [healthAttempt]);

  useEffect(() => {
    if (!ready || (configured && online !== true) || online === null || (configured && !userId)) return;

    setRoute('overview');
    setProfile(EMPTY_PROFILE);
    setDocuments([]);
    setTemplates([]);
    setActiveTemplate(null);
    setActiveDocument(null);

    (async () => {
      try {
        const loaded = await api.profile();
        setProfile({ ...EMPTY_PROFILE, ...loaded });
      } catch {
        /* keep defaults */
      }
      await Promise.all([loadDocuments(), loadTemplates()]);
    })();
  }, [ready, configured, userId, online]);

  if (!ready) {
    return (
      <div className="min-h-screen flex items-center justify-center text-sm text-[var(--text-muted)]">
        Restoring your session…
      </div>
    );
  }
  if (configured && !session) return <LoginPage />;
  if (configured && online !== true) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-3 p-6 text-center">
        <p className="text-sm text-[var(--text-muted)]">
          {online === null
            ? 'Connecting to the quotation server… It may take about a minute to wake up after being idle.'
            : 'The quotation server could not be reached.'}
        </p>
        {online === false && (
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              setOnline(null);
              setHealthAttempt((attempt) => attempt + 1);
            }}
          >
            Try again
          </button>
        )}
        {configured && (
          <button type="button" className="btn btn-ghost text-sm" onClick={() => { void handleSignOut(); }}>
            Sign out
          </button>
        )}
        {signOutError && <p role="alert" className="text-sm text-[var(--danger,#c0392b)]">{signOutError}</p>}
      </div>
    );
  }

  const openCreate = () => {
    setActiveDocument(null);
    setRoute('create');
  };

  const openDocument = async (id: string) => {
    try {
      const record = await api.document(id);
      setActiveDocument(record);
      setRoute('create');
    } catch {
      /* leave the user where they are */
    }
  };

  const deleteDocument = async (id: string) => {
    await api.deleteDocument(id).catch(() => undefined);
    if (activeDocument?.id === id) setActiveDocument(null);
    await loadDocuments();
  };

  return (
    <div className="flex min-h-screen bg-[var(--bg)]">
      <Sidebar active={route} onNavigate={setRoute} online={online}
        documentCount={documents.length} templateCount={templates.length}
        email={email} onSignOut={() => { void handleSignOut(); }} />

      <div className="flex-1 min-w-0 flex flex-col">
        <header className="md:hidden sticky top-0 z-20 bg-[var(--surface)] border-b border-[var(--border)]">
          <div className="flex items-center justify-between px-4 py-3">
            <div className="flex items-center gap-2">
              <span className="font-semibold">quoteGEN</span>
              <span className="chip chip-gold">AI</span>
            </div>
            <div className="flex items-center gap-2">
              <StatusRow online={online} />
              {configured && (
                <button type="button" className="btn btn-ghost text-xs" onClick={() => { void handleSignOut(); }}>
                  Sign out
                </button>
              )}
            </div>
          </div>
          <nav className="flex gap-1 px-2 pb-2 overflow-x-auto">
            {MOBILE_NAV.map((item) => {
              const Icon = item.icon;
              return (
                <button key={item.id} type="button"
                  className={`nav-item w-auto ${route === item.id ? 'active' : ''}`}
                  onClick={() => setRoute(item.id)}>
                  <Icon size={16} />
                  <span>{item.label}</span>
                </button>
              );
            })}
          </nav>
        </header>

        <main className="flex-1 min-w-0 p-4 sm:p-6">
          {signOutError && (
            <p role="alert" className="mb-4 text-sm text-[var(--danger,#c0392b)]">
              {signOutError}
            </p>
          )}
          {route === 'overview' && (
            <OverviewPage
              documents={documents}
              templateCount={templates.length}
              onCreate={openCreate}
              onOpenDocuments={() => setRoute('documents')}
              onOpenTemplates={() => setRoute('templates')}
            />
          )}

          {route === 'documents' && (
            <DocumentsPage
              documents={documents}
              onOpen={openDocument}
              onDelete={deleteDocument}
              onCreate={openCreate}
            />
          )}

          {route === 'create' && (
            <CreateQuotation
              key={activeDocument?.id || 'new'}
              profile={profile}
              activeTemplate={activeTemplate}
              onManageTemplates={() => setRoute('templates')}
              initialDocument={activeDocument}
              onSaved={loadDocuments}
            />
          )}

          {route === 'templates' && (
            <MasterTemplatePage
              activeTemplate={activeTemplate}
              onChanged={loadTemplates}
            />
          )}

          {route === 'profile' && (
            <ProfilePage profile={profile} onSaved={setProfile} />
          )}
        </main>
      </div>
    </div>
  );
}
