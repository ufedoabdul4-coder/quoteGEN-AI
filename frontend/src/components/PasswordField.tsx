import { useId, useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';

interface Props {
  label: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete?: string;
  placeholder?: string;
  minLength?: number;
  autoFocus?: boolean;
  invalid?: boolean;
}

/** A password input with its own show/hide eye toggle. */
export function PasswordField({
  label, value, onChange, autoComplete, placeholder, minLength, autoFocus, invalid,
}: Props) {
  const id = useId();
  const [visible, setVisible] = useState(false);

  return (
    <label className="flex flex-col gap-1" htmlFor={id}>
      <span className="label">{label}</span>
      <span className="relative block">
        <input
          id={id}
          className="input pr-11"
          type={visible ? 'text' : 'password'}
          autoComplete={autoComplete}
          required
          minLength={minLength}
          autoFocus={autoFocus}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          style={invalid ? { borderColor: 'var(--error)' } : undefined}
        />
        <button
          type="button"
          className="absolute inset-y-0 right-1 my-auto flex h-8 w-8 items-center justify-center rounded text-[var(--text-muted)] hover:text-[var(--text)]"
          aria-label={visible ? `Hide ${label}` : `Show ${label}`}
          aria-pressed={visible}
          onClick={() => setVisible((shown) => !shown)}
        >
          {visible ? <EyeOff size={16} /> : <Eye size={16} />}
        </button>
      </span>
    </label>
  );
}
