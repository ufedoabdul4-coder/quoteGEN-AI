import { useEffect, useState } from 'react';
import {
  LayoutDashboard, FileText, CirclePlus, Building, FileStack, Menu, X, Sparkles,
} from 'lucide-react';
import type {
  BillingStatus, BusinessProfile, DocumentRecord, DocumentSummary, TemplateMeta,
} from './types';
import { api, ApiError } from './services/api';
import { Sidebar, StatusRow } from './components/Sidebar';
import type { Route } from './components/Sidebar';
import { OverviewPage } from './components/OverviewPage';
import { DocumentsPage } from './components/DocumentsPage';
import { CreateQuotation } from './components/CreateQuotation';
import { ProfilePage } from './components/ProfilePage';
import { MasterTemplatePage } from './components/MasterTemplatePage';
import { LoginPage } from './components/LoginPage';
import { PaymentReturnPage } from './components/PaymentReturnPage';
import { LandingPage, type GatedIntent } from './components/LandingPage';
import { OnboardingTour } from './components/OnboardingTour';
import { InstallPrompt } from './components/InstallPrompt';
import { useAuth } from './services/auth';

const EMPTY_PROFILE: BusinessProfile = {
  name: '', business_type: '', phone: '', email: '', website: '', address: '', logo_data_url: '',
};

// A visitor's chosen feature is remembered so they land on it once signed in,
// even after the email-confirmation round-trip.
const PENDING_INTENT_KEY = 'quotegen:pending-intent';
const INTENT_ROUTES: Route[] = ['overview', 'documents', 'create', 'templates', 'profile'];

function savePendingIntent(intent: GatedIntent) {
  try {
    window.localStorage.setItem(PENDING_INTENT_KEY, intent);
  } catch {
    /* storage may be unavailable */
  }
}

function takePendingIntent(): GatedIntent | null {
  try {
    const value = window.localStorage.getItem(PENDING_INTENT_KEY);
    window.localStorage.removeItem(PENDING_INTENT_KEY);
    if (value === 'upgrade') return 'upgrade';
    return value && (INTENT_ROUTES as string[]).includes(value) ? (value as Route) : null;
  } catch {
    return null;
  }
}

function clearPendingIntent() {
  try {
    window.localStorage.removeItem(PENDING_INTENT_KEY);
  } catch {
    /* ignore */
  }
}

function hasOnboarded(userId: string): boolean {
  try {
    return window.localStorage.getItem(`quotegen:onboarded:${userId}`) === '1';
  } catch {
    return false;
  }
}

function markOnboarded(userId: string | undefined) {
  if (!userId) return;
  try {
    window.localStorage.setItem(`quotegen:onboarded:${userId}`, '1');
  } catch {
    /* ignore */
  }
}

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
  const [confirmedEmail, setConfirmedEmail] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('confirmed') !== '1') return null;
    return params.get('email') || '';
  });
  const [paymentReturn, setPaymentReturn] = useState(
    () => new URLSearchParams(window.location.search).get('payment') === 'complete',
  );
  const [route, setRoute] = useState<Route>('overview');
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [online, setOnline] = useState<boolean | null>(null);
  const [healthAttempt, setHealthAttempt] = useState(0);
  const [profile, setProfile] = useState<BusinessProfile>(EMPTY_PROFILE);
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [billingStatus, setBillingStatus] = useState<BillingStatus | null>(null);
  const [billingLoadError, setBillingLoadError] = useState('');
  const [templates, setTemplates] = useState<TemplateMeta[]>([]);
  const [templatesLoaded, setTemplatesLoaded] = useState(false);
  const [templateLoadError, setTemplateLoadError] = useState('');
  const [activeTemplate, setActiveTemplate] = useState<TemplateMeta | null>(null);
  const [activeDocument, setActiveDocument] = useState<DocumentRecord | null>(null);
  const [signOutError, setSignOutError] = useState('');
  const [upgradeBusy, setUpgradeBusy] = useState(false);
  const [upgradeError, setUpgradeError] = useState('');
  const [authGate, setAuthGate] = useState<{ label: string; mode: 'signin' | 'signup' } | null>(null);
  const [showTour, setShowTour] = useState(false);

  const handleSignOut = async () => {
    setSignOutError('');
    try {
      await signOut();
    } catch (error) {
      setSignOutError(error instanceof Error ? error.message : 'Unable to sign out.');
    }
  };

  const continueToSignIn = async () => {
    setSignOutError('');
    try {
      if (session) await signOut();
      const loginUrl = new URL('/', window.location.origin);
      if (confirmedEmail) loginUrl.searchParams.set('email', confirmedEmail);
      window.history.replaceState(null, '', `${loginUrl.pathname}${loginUrl.search}`);
      setConfirmedEmail(null);
    } catch (error) {
      setSignOutError(error instanceof Error ? error.message : 'Unable to continue to sign in.');
    }
  };

  const loadDocuments = async () => {
    try {
      setDocuments(await api.documents());
    } catch {
      setDocuments([]);
    }
  };

  const loadBillingStatus = async () => {
    setBillingLoadError('');
    try {
      setBillingStatus(await api.billingStatus());
    } catch (error) {
      console.error('Unable to load quotation usage.', error);
      setBillingStatus(null);
      setBillingLoadError(
        'Usage is unavailable. If you have not applied the latest Supabase schema, run it and retry.',
      );
    }
  };

  const loadTemplates = async () => {
    setTemplateLoadError('');
    let lastError: unknown;
    for (let attempt = 0; attempt < 3; attempt += 1) {
      try {
        const loadedTemplates = await api.templates();
        setTemplates(loadedTemplates);
        setActiveTemplate(
          loadedTemplates.find((template) => template.is_active)
          ?? loadedTemplates.find((template) => template.status === 'ready')
          ?? null,
        );
        setTemplatesLoaded(true);
        return;
      } catch (error) {
        lastError = error;
        if (error instanceof ApiError && error.status < 500) break;
        if (attempt < 2) {
          await new Promise((resolve) => window.setTimeout(resolve, 500 * (attempt + 1)));
        }
      }
    }
    setTemplateLoadError(
      'We couldn’t load your master templates. Your saved templates have not been removed. Try again.',
    );
    console.error('Unable to load master templates.', lastError);
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

    const pendingIntent = takePendingIntent();
    setRoute(pendingIntent && pendingIntent !== 'upgrade' ? pendingIntent : 'overview');
    setAuthGate(null);
    setShowTour(!hasOnboarded(userId ?? 'local'));
    setProfile(EMPTY_PROFILE);
    setDocuments([]);
    setTemplates([]);
    setTemplatesLoaded(false);
    setTemplateLoadError('');
    setActiveTemplate(null);
    setActiveDocument(null);
    setBillingStatus(null);
    setBillingLoadError('');

    (async () => {
      try {
        const loaded = await api.profile();
        setProfile({ ...EMPTY_PROFILE, ...loaded });
      } catch {
        /* keep defaults */
      }
      await Promise.allSettled([loadDocuments(), loadTemplates(), loadBillingStatus()]);
    })();
  }, [ready, configured, userId, online]);

  if (!ready) {
    return (
      <div className="min-h-screen flex items-center justify-center text-sm text-[var(--text-muted)]">
        Restoring your session…
      </div>
    );
  }
  if (confirmedEmail !== null) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4 bg-[var(--bg)]">
        <div className="card w-full max-w-sm text-center">
          <div className="flex items-center justify-center gap-2 mb-4">
            <span className="font-semibold text-lg">quoteGEN</span>
            <span className="chip chip-gold">AI</span>
          </div>
          <h1 className="text-lg font-semibold mb-2">Thanks for registering!</h1>
          <p className="text-sm text-[var(--text-muted)] mb-5">
            Your email is confirmed. Continue to sign in to your quoteGEN account.
          </p>
          {signOutError && (
            <p role="alert" className="text-sm text-[var(--danger,#c0392b)] mb-3">
              {signOutError}
            </p>
          )}
          <button type="button" className="btn btn-primary w-full" onClick={() => { void continueToSignIn(); }}>
            Go to sign in
          </button>
        </div>
      </div>
    );
  }
  if (configured && !session) {
    const initialEmail = new URLSearchParams(window.location.search).get('email') || '';
    if (authGate || initialEmail) {
      return (
        <>
          <LoginPage
            initialEmail={initialEmail}
            initialMode={authGate?.mode ?? 'signin'}
            intentLabel={authGate?.label}
            onBack={authGate ? () => { clearPendingIntent(); setAuthGate(null); } : undefined}
          />
          <InstallPrompt />
        </>
      );
    }
    return (
      <>
        <LandingPage
          onSignIn={() => setAuthGate({ label: '', mode: 'signin' })}
          onGetStarted={() => setAuthGate({ label: '', mode: 'signup' })}
          onProtected={requestAuth}
        />
        <InstallPrompt />
      </>
    );
  }
  if (paymentReturn) {
    return (
      <PaymentReturnPage
        onContinue={() => {
          window.history.replaceState(null, '', '/');
          setPaymentReturn(false);
          void loadBillingStatus();
        }}
      />
    );
  }
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

  const startUpgrade = async () => {
    if (!email) {
      setUpgradeError('Could not identify your signed-in email. Please sign in again.');
      return;
    }
    setUpgradeBusy(true);
    setUpgradeError('');
    try {
      const fullName = session?.user.user_metadata?.full_name;
      const result = await api.billingCheckout(
        email,
        typeof fullName === 'string' ? fullName : '',
      );
      window.location.assign(result.checkout_url);
    } catch (error) {
      setUpgradeError(error instanceof Error ? error.message : 'Unable to start payment.');
      setUpgradeBusy(false);
    }
  };

  const navigateMobile = (nextRoute: Route) => {
    setRoute(nextRoute);
    setMobileMenuOpen(false);
  };

  function requestAuth(
    intent: GatedIntent,
    label: string,
    mode: 'signin' | 'signup' = 'signup',
  ) {
    savePendingIntent(intent);
    setAuthGate({ label, mode });
  }

  function closeTour() {
    setShowTour(false);
    markOnboarded(userId ?? 'local');
  }

  function finishTour(nextRoute: Route) {
    closeTour();
    setRoute(nextRoute);
  }

  return (
    <div className="flex min-h-screen bg-[var(--bg)]">
      <Sidebar active={route} onNavigate={setRoute} online={online}
        documentCount={documents.length}
        templateCount={templatesLoaded ? templates.length : null}
        email={email}
        unlimited={billingStatus?.monthly_plan_active ?? false}
        onSignOut={() => { void handleSignOut(); }} />

      <div className="flex-1 min-w-0 flex flex-col">
        <header className="md:hidden sticky top-0 z-20 bg-[var(--surface)] border-b border-[var(--border)]">
          <div className="flex items-center justify-between gap-3 px-4 py-3">
            <div className="flex items-center gap-2">
              <span className="font-semibold">quoteGEN</span>
              <span className="chip chip-gold">AI</span>
              {billingStatus?.monthly_plan_active && (
                <span className="chip chip-gold"><Sparkles size={12} /> Unlimited</span>
              )}
            </div>
            <button
              type="button"
              className="btn shrink-0"
              aria-expanded={mobileMenuOpen}
              aria-controls="mobile-navigation"
              onClick={() => setMobileMenuOpen((open) => !open)}
            >
              {mobileMenuOpen ? <X size={17} /> : <Menu size={17} />}
              <span>{mobileMenuOpen ? 'Close' : 'Menu'}</span>
            </button>
          </div>
          {mobileMenuOpen && (
            <div id="mobile-navigation" className="border-t border-[var(--border)] px-3 py-3">
              <nav aria-label="Main navigation" className="space-y-1">
                {MOBILE_NAV.map((item) => {
                  const Icon = item.icon;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      className={`nav-item ${route === item.id ? 'active' : ''}`}
                      aria-current={route === item.id ? 'page' : undefined}
                      onClick={() => navigateMobile(item.id)}
                    >
                      <Icon size={17} />
                      <span>{item.label}</span>
                    </button>
                  );
                })}
              </nav>
              <div className="mt-3 space-y-2 border-t border-[var(--border)] px-2 pt-3">
                <StatusRow online={online} />
                <div className="text-xs text-[var(--text-dim)]">
                  {documents.length} document(s)
                  {' · '}
                  {templatesLoaded ? `${templates.length} template(s)` : 'Checking templates…'}
                </div>
                {configured && email && (
                  <div className="flex items-center justify-between gap-3 pt-1">
                    <span className="min-w-0 truncate text-xs text-[var(--text-dim)]">{email}</span>
                    <button
                      type="button"
                      className="btn btn-ghost shrink-0 text-xs"
                      onClick={() => {
                        setMobileMenuOpen(false);
                        void handleSignOut();
                      }}
                    >
                      Sign out
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}
        </header>

        <main className="flex-1 min-w-0 p-4 sm:p-6">
          {signOutError && (
            <p role="alert" className="mb-4 text-sm text-[var(--danger,#c0392b)]">
              {signOutError}
            </p>
          )}
          {templateLoadError && (
            <div role="alert" className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded border border-[var(--error)] p-3 text-sm">
              <span>{templateLoadError}</span>
              <button type="button" className="btn" onClick={() => { void loadTemplates(); }}>
                Retry
              </button>
            </div>
          )}
          {route === 'overview' && (
            <OverviewPage
              documents={documents}
              billingStatus={billingStatus}
              billingLoadError={billingLoadError}
              onRetryBilling={() => { void loadBillingStatus(); }}
              templateCount={templatesLoaded ? templates.length : null}
              onCreate={openCreate}
              onOpenDocuments={() => setRoute('documents')}
              onOpenTemplates={() => setRoute('templates')}
              onUpgrade={() => { void startUpgrade(); }}
              upgradeBusy={upgradeBusy}
              upgradeError={upgradeError}
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
              onSaved={async () => {
                await Promise.all([loadDocuments(), loadBillingStatus()]);
              }}
            />
          )}

          {route === 'templates' && (
            <MasterTemplatePage
              activeTemplate={activeTemplate}
              templatesLoaded={templatesLoaded}
              onChanged={loadTemplates}
            />
          )}

          {route === 'profile' && (
            <ProfilePage profile={profile} onSaved={setProfile} />
          )}
        </main>
      </div>

      <OnboardingTour key={showTour ? 'tour-open' : 'tour-closed'}
        open={showTour} onClose={closeTour} onFinish={finishTour} />
      <InstallPrompt />
    </div>
  );
}
