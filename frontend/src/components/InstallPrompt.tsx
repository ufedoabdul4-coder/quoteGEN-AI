import { useEffect, useState } from 'react';
import { Download, Share, Smartphone, X } from 'lucide-react';

const DISMISS_KEY = 'quotegen:install-dismissed';

/** The non-standard event Chrome/Edge fire when the app becomes installable. */
interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

const isStandalone = (): boolean => {
  if (typeof window === 'undefined') return false;
  return (
    window.matchMedia?.('(display-mode: standalone)').matches
    || (window.navigator as { standalone?: boolean }).standalone === true
  );
};

const isIos = (): boolean => {
  if (typeof navigator === 'undefined') return false;
  const ua = navigator.userAgent;
  const iOS = /iPad|iPhone|iPod/.test(ua)
    || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  // Safari (not Chrome/Firefox on iOS, which cannot add to home screen).
  const safari = /Safari/.test(ua) && !/CriOS|FxiOS|EdgiOS|OPiOS/.test(ua);
  return iOS && safari;
};

export function InstallPrompt() {
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(null);
  const [iosHint, setIosHint] = useState(false);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (isStandalone()) return;
    let dismissed = false;
    try {
      dismissed = window.localStorage.getItem(DISMISS_KEY) === '1';
    } catch {
      dismissed = false;
    }
    if (dismissed) return;

    const onBeforeInstall = (event: Event) => {
      event.preventDefault();
      setDeferred(event as BeforeInstallPromptEvent);
      setVisible(true);
    };
    const onInstalled = () => {
      setVisible(false);
      setDeferred(null);
      try {
        window.localStorage.setItem(DISMISS_KEY, '1');
      } catch {
        /* ignore */
      }
    };

    window.addEventListener('beforeinstallprompt', onBeforeInstall);
    window.addEventListener('appinstalled', onInstalled);

    // iOS never fires beforeinstallprompt, so offer manual instructions.
    const timer = window.setTimeout(() => {
      if (isIos()) {
        setIosHint(true);
        setVisible(true);
      }
    }, 4000);

    return () => {
      window.removeEventListener('beforeinstallprompt', onBeforeInstall);
      window.removeEventListener('appinstalled', onInstalled);
      window.clearTimeout(timer);
    };
  }, []);

  const dismiss = () => {
    setVisible(false);
    try {
      window.localStorage.setItem(DISMISS_KEY, '1');
    } catch {
      /* ignore */
    }
  };

  const install = async () => {
    if (!deferred) return;
    await deferred.prompt();
    await deferred.userChoice;
    setVisible(false);
    setDeferred(null);
  };

  if (!visible) return null;

  return (
    <div className="fixed inset-x-0 bottom-0 z-40 p-3 pointer-events-none">
      <div className="mx-auto max-w-md card p-3 shadow-lg pointer-events-auto">
        <div className="flex items-start gap-3">
          <span className="chip chip-gold shrink-0 mt-0.5"><Smartphone size={14} /></span>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold">Add quoteGEN to your home screen</p>
            {iosHint ? (
              <p className="text-xs text-[var(--text-muted)] mt-1 leading-relaxed">
                Tap the <Share size={12} className="inline -mt-0.5" /> <strong>Share</strong> icon in
                Safari, then choose <strong>Add to Home Screen</strong>.
              </p>
            ) : (
              <p className="text-xs text-[var(--text-muted)] mt-1">
                Install the app for quick, full-screen access to your quotations.
              </p>
            )}
            {!iosHint && (
              <button type="button" className="btn btn-primary mt-2" onClick={() => { void install(); }}>
                <Download size={15} /> Add to home screen
              </button>
            )}
          </div>
          <button
            type="button"
            aria-label="Dismiss"
            className="btn btn-ghost shrink-0 p-1"
            onClick={dismiss}
          >
            <X size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
