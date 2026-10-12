import { ChevronLeft, ChevronRight, Trash, Plus } from 'lucide-react';
import type { SemanticBlock } from '../types';
import { formatMoney, syncBlockValue } from '../utils/money';

const TYPES = [
  'document_title', 'subtitle', 'client_name', 'client_address', 'service_address',
  'quotation_number', 'quotation_date', 'validity_period', 'introduction',
  'major_section_heading', 'subsection_heading', 'paragraph', 'bullet_list',
  'numbered_list', 'scope_item', 'table_header', 'table_row', 'cost_amount',
  'subtotal', 'grand_total', 'amount_in_words', 'duration', 'term', 'signature',
  'client_acceptance', 'contact_information',
] as const;

export function BlockEditor({ blocks, onChange }: { blocks: SemanticBlock[]; onChange: (b: SemanticBlock[]) => void }) {
  const update = (index: number, patch: Partial<SemanticBlock>) => {
    const next = blocks.map((block, i) =>
      i === index ? syncBlockValue({ ...block, ...patch }) : block);
    onChange(reindex(next));
  };

  const remove = (index: number) => onChange(reindex(blocks.filter((_, i) => i !== index)));

  const move = (index: number, delta: number) => {
    const target = index + delta;
    if (target < 0 || target >= blocks.length) return;
    const next = [...blocks];
    [next[index], next[target]] = [next[target], next[index]];
    onChange(reindex(next));
  };

  const add = (type: string) => {
    const block: SemanticBlock = {
      id: `new-${Date.now()}`, type, text: '', level: 1, items: [],
      value: null, figure: null, group: '', order: blocks.length,
    };
    onChange(reindex([...blocks, block]));
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="eyebrow">Document blocks ({blocks.length})</span>
        <AddBlock onAdd={add} />
      </div>

      <div className="space-y-1.5">
        {blocks.map((block, index) => (
          <div key={block.id || index} className="panel p-2.5 space-y-2">
            <div className="flex items-center gap-2">
              <select
                className="select"
                style={{ width: 'auto', padding: '0.25rem 0.4rem', fontSize: '0.72rem' }}
                value={block.type}
                onChange={(e) => update(index, { type: e.target.value })}
              >
                {TYPES.map((t) => <option key={t} value={t}>{formatType(t)}</option>)}
              </select>

              {block.value !== null && (
                <span className="chip chip-gold tabular-nums">{formatMoney(block.value)}</span>
              )}

              <div className="ml-auto flex items-center gap-0.5">
                <IconBtn label="Move up" onClick={() => move(index, -1)} disabled={index === 0}>
                  <ChevronLeft size={14} className="rotate-90" />
                </IconBtn>
                <IconBtn label="Move down" onClick={() => move(index, 1)} disabled={index === blocks.length - 1}>
                  <ChevronRight size={14} className="rotate-90" />
                </IconBtn>
                <button
                  type="button"
                  className="btn btn-danger px-1.5 py-1"
                  onClick={() => remove(index)}
                  aria-label="Delete block"
                >
                  <Trash size={14} />
                </button>
              </div>
            </div>

            {block.items.length > 0 ? (
              <ItemsEditor block={block} onChange={(items) => update(index, { items })} />
            ) : (
              <input
                className="input"
                value={block.text}
                placeholder="Block text…"
                onChange={(e) => update(index, { text: e.target.value })}
              />
            )}
            {block.items.length > 0 && (
              <input
                className="input"
                value={block.text}
                placeholder="Optional lead-in text…"
                onChange={(e) => update(index, { text: e.target.value })}
              />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function ItemsEditor({ block, onChange }: {
  block: SemanticBlock;
  onChange: (items: string[]) => void;
}) {
  const isTable = ['table_header', 'table_row', 'subtotal', 'grand_total'].includes(block.type);
  const value = isTable ? block.items.join(' | ') : block.items.join('\n');

  return (
    <textarea
      className="textarea"
      style={{ minHeight: isTable ? 40 : 70 }}
      value={value}
      placeholder={isTable ? 'Column | Column | Amount' : 'One item per line'}
      onChange={(e) => {
        const raw = e.target.value;
        onChange(isTable
          ? raw.split('|').map((cell) => cell.trim())
          : raw.split('\n').map((line) => line.trim()).filter(Boolean));
      }}
    />
  );
}

function AddBlock({ onAdd }: { onAdd: (type: string) => void }) {
  return (
    <div className="flex items-center gap-1">
      <Plus size={13} className="text-[var(--text-dim)]" />
      <select
        className="select"
        style={{ width: 'auto', padding: '0.25rem 0.4rem', fontSize: '0.72rem' }}
        value=""
        onChange={(e) => { if (e.target.value) onAdd(e.target.value); }}
      >
        <option value="">Add block…</option>
        {TYPES.map((t) => <option key={t} value={t}>{formatType(t)}</option>)}
      </select>
    </div>
  );
}

function formatType(type: string): string {
  return type.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function IconBtn({ children, label, onClick, disabled }: {
  children: React.ReactNode;
  label: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      className="btn btn-ghost px-1.5 py-1"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
    >
      {children}
    </button>
  );
}

function reindex(blocks: SemanticBlock[]): SemanticBlock[] {
  return blocks.map((block, index) => ({ ...block, order: index }));
}
