import type { SemanticBlock } from '../types';

const MONEY = /(?<![\w.])(?:\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d{1,3}(?:\s\d{3})+(?:\.\d{1,2})?|\d+\.\d{2})(?![\w])/;

export function parseMoney(text: string): number | null {
  const match = text.match(MONEY);
  if (!match) return null;
  const digits = match[0].replace(/[^\d.]/g, '');
  const value = Number(digits);
  return Number.isFinite(value) ? value : null;
}

export function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

const PRICED = new Set(['table_row', 'cost_amount', 'subtotal', 'grand_total']);

/** The amount string a priced block should be read from. */
function amountSource(block: SemanticBlock): string {
  if (block.type === 'table_row' && block.items.length > 0) {
    return block.items[block.items.length - 1];
  }
  return block.text || block.figure || '';
}

/**
 * Keep a priced block's numeric value in sync with its visible text, so the
 * totals the user sees reflect exactly what they typed. Mirrors the backend's
 * rule: only a grouped or two-decimal figure is treated as money.
 */
export function syncBlockValue(block: SemanticBlock): SemanticBlock {
  if (!PRICED.has(block.type)) return block;
  const source = amountSource(block);
  const value = parseMoney(source);
  return { ...block, value, figure: source || block.figure };
}
