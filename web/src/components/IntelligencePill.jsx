// The intelligence a book most asks of its reader, as a chip: "Interpersonal". Gardner's
// eight plus existential, graded by intelligences.py and sent by the shelf as
// `book.intelligence`. Outlined rather than filled, and without a dot, so it never reads
// as the spiral pill beside it; the hover lists every intelligence the book asks for.

export const INTELLIGENCES = [
  ['linguistic', 'Linguistic'],
  ['logical', 'Logical-mathematical'],
  ['spatial', 'Visual-spatial'],
  ['musical', 'Musical'],
  ['bodily', 'Bodily-kinesthetic'],
  ['naturalist', 'Naturalist'],
  ['interpersonal', 'Interpersonal'],
  ['intrapersonal', 'Intrapersonal'],
  ['existential', 'Existential'],
];
const NAMES = Object.fromEntries(INTELLIGENCES);

/** A book's fit with one intelligence, 0 to 3, or -1 when it is not graded. */
export function fitOf(book, key) {
  return book.intelligence?.fits?.[key] ?? -1;
}

export default function IntelligencePill({ intelligence, onAccent = false }) {
  if (!intelligence) return null;
  // The others it asks for in earnest (a fit of 2 or 3), strongest first, for the hover.
  const also = Object.entries(intelligence.fits || {})
    .filter(([key, fit]) => fit >= 2 && key !== intelligence.primary)
    .sort((a, b) => b[1] - a[1])
    .map(([key]) => NAMES[key]);
  return (
    <span
      title={`Mostly ${intelligence.name}${also.length ? `, also ${also.join(', ')}` : ''}. ${intelligence.reason}`}
      style={{
        flex: 'none',
        display: 'inline-flex',
        alignItems: 'center',
        padding: '3px 8px',
        borderRadius: 4,
        // As the spiral pill: mixed case at 10px, read as a word.
        font: "600 10px 'IBM Plex Mono', monospace",
        letterSpacing: '0.01em',
        whiteSpace: 'nowrap',
        background: 'transparent',
        border: `1px solid ${onAccent ? 'rgba(20,32,31,.35)' : 'var(--border-strong)'}`,
        color: onAccent ? 'var(--accent-on)' : 'var(--text-secondary)',
      }}
    >
      {intelligence.name}
    </span>
  );
}
