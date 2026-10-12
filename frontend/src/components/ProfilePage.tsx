import { useState } from 'react';
import { Save, LoaderCircle, Upload, CircleCheck, Trash } from 'lucide-react';
import type { BusinessProfile } from '../types';
import { api } from '../services/api';

interface Props {
  profile: BusinessProfile;
  onSaved: (profile: BusinessProfile) => void;
}

export function ProfilePage({ profile, onSaved }: Props) {
  const [draft, setDraft] = useState<BusinessProfile>(profile);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');

  const update = (patch: Partial<BusinessProfile>) => {
    setDraft({ ...draft, ...patch });
    setSaved(false);
  };

  const chooseLogo = (file: File) => {
    const reader = new FileReader();
    reader.onload = () => update({ logo_data_url: String(reader.result) });
    reader.readAsDataURL(file);
  };

  const save = async () => {
    setSaving(true);
    setError('');
    try {
      const result = await api.saveProfile(draft);
      onSaved(result);
      setSaved(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-2xl space-y-4">
      <header>
        <h1 className="text-lg font-semibold">Business profile</h1>
        <p className="text-xs text-[var(--text-muted)]">
          These details appear on the letterhead of every document you generate.
        </p>
      </header>

      <div className="card p-4 sm:p-5 space-y-4">
        <div className="flex items-center gap-4">
          <div className="w-16 h-16 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] flex items-center justify-center overflow-hidden">
            {draft.logo_data_url
              ? <img src={draft.logo_data_url} alt="Logo" className="w-full h-full object-contain" />
              : <span className="text-[10px] text-[var(--text-dim)]">No logo</span>}
          </div>
          <div className="flex items-center gap-2">
            <label className="btn cursor-pointer">
              <Upload size={14} /> Upload logo
              <input type="file" accept="image/*" className="hidden"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) chooseLogo(f); }} />
            </label>
            {draft.logo_data_url && (
              <button type="button" className="btn btn-danger px-2 py-1"
                onClick={() => update({ logo_data_url: null })} aria-label="Remove logo">
                <Trash size={14} />
              </button>
            )}
          </div>
        </div>

        <Text label="Business name" value={draft.name} onChange={(v) => update({ name: v })} />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Text label="Phone" value={draft.phone} onChange={(v) => update({ phone: v })} />
          <Text label="Email" value={draft.email} onChange={(v) => update({ email: v })} />
        </div>
        <Text label="Website" value={draft.website} onChange={(v) => update({ website: v })} />
        <Text label="Address" value={draft.address} onChange={(v) => update({ address: v })} />

        <div className="flex items-center gap-3 divide-hair pt-4">
          <button type="button" className="btn btn-primary" onClick={save} disabled={saving}>
            {saving ? <LoaderCircle size={15} className="spin" /> : <Save size={15} />}
            Save profile
          </button>
          {saved && <span className="chip chip-ok"><CircleCheck size={12} /> Saved</span>}
          {error && <span className="text-xs text-[var(--error)]">{error}</span>}
        </div>
      </div>
    </div>
  );
}

function Text({ label, value, onChange }: {
  label: string; value: string; onChange: (value: string) => void;
}) {
  return (
    <div>
      <label className="label">{label}</label>
      <input className="input" value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}
