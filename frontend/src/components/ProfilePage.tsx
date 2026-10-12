import { useState } from 'react';
import { Save, LoaderCircle, CircleCheck } from 'lucide-react';
import type { BusinessProfile } from '../types';
import { api } from '../services/api';

const BUSINESS_TYPES = [
  'Agriculture',
  'Construction & trades',
  'Education',
  'Food & hospitality',
  'Healthcare',
  'Manufacturing',
  'Nonprofit',
  'Professional services',
  'Real estate',
  'Retail & ecommerce',
  'Technology',
  'Transportation & logistics',
  'Other',
];

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
        <Text label="Business name" value={draft.name} onChange={(v) => update({ name: v })} />
        <div>
          <label className="label" htmlFor="business-type">Business type</label>
          <select
            id="business-type"
            className="input"
            value={draft.business_type}
            onChange={(event) => update({ business_type: event.target.value })}
          >
            <option value="">Select a business type</option>
            {BUSINESS_TYPES.map((businessType) => (
              <option key={businessType} value={businessType}>{businessType}</option>
            ))}
          </select>
        </div>
        <Text label="Website" value={draft.website} onChange={(v) => update({ website: v })} />
        <Text label="Business address" value={draft.address} onChange={(v) => update({ address: v })} />

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
