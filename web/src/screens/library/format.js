// Formatting shared by the library screen and its rows.

export const STATUS_TONE = { done: 'current', running: 'claimed', queued: 'neutral', failed: 'expired' };

export const MONO = "'IBM Plex Mono', monospace";

/** Sub-cent sums are the normal case here, so two decimals would read as "free". */
export function money(amount) {
  if (amount == null) return '—';
  if (amount < 0.01) return `$${amount.toFixed(4)}`;
  if (amount < 1) return `$${amount.toFixed(3)}`;
  return `$${amount.toFixed(2)}`;
}

export function thousands(n) {
  return n.toLocaleString('en-US');
}

/**
 * A download's filename, made readable.
 *
 * Library filenames carry everything anyone might search on — author, year, ASIN, ISBN,
 * and the mirror it came from — joined by underscores. Shown raw they are a wall of
 * text that pushes the status off the row, and the part that identifies the book is the
 * first few words. The rest is stripped for display only; the file on disk keeps its
 * name, and the real title replaces this as soon as the pipeline reads it.
 */
export function readableName(name) {
  let out = (name || '').replace(/\.(pdf|epub)$/i, '');
  out = out.replace(/\(([^)]*z-?lib[^)]*)\)/gi, ' ');
  out = out.replace(/\[[^\]]*\]/g, ' ');
  out = out.replace(/\([^)]*\)/g, ' ');
  out = out.replace(/B0[A-Z0-9]{8}/g, ' ');
  out = out.replace(/97[89]\d{10}/g, ' ');
  out = out.replace(/[_]+/g, ' ').replace(/\s+/g, ' ').trim();
  out = out.replace(/[-–—,.\s]+$/, '');
  return out.length > 56 ? `${out.slice(0, 55).trimEnd()}…` : out || name;
}

/**
 * How far the automatic cover pass has got.
 *
 * Every book is looked up by itself — on ingest, or on the first shelf load that sees
 * one nobody has asked about — so there is no button to describe. There is only this:
 * a line saying the thing is happening, and how much of it is left.
 */
export function coverLine(covers) {
  if (!covers.enabled) return 'covers · HARDCOVER_API_KEY is not set, so none are looked up';

  const parts = [`${covers.found} found`];
  if (covers.missing) parts.push(`${covers.missing} not on Hardcover`);
  if (covers.failed) parts.push(`${covers.failed} failed`);
  if (covers.pending) parts.push(`${covers.pending} still to look up`);
  return `covers · ${parts.join(' · ')}`;
}
