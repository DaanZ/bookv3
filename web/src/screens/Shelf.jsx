import Patch from '../components/Patch';
import { ProgressBar } from '../components/ui';
import { cum } from '../lib/reading';

// Choose what to read; see at a glance what each book is and where you left it.

const CHIPS = {
  new: ['not started', 'var(--chip-neutral-bg)', 'var(--chip-neutral-fg)'],
  reading: [null, 'var(--chip-claimed-bg)', 'var(--chip-claimed-fg)'],
  read: ['read', 'var(--chip-current-bg)', 'var(--chip-current-fg)'],
};

function metaLine(book, donePct) {
  if (book.state === 'new') return `${book.partCount} parts · nothing read yet`;
  if (book.state === 'reading') {
    const paused =
      book.pausedDays == null
        ? 'in progress'
        : book.pausedDays === 0
          ? 'paused today'
          : `paused ${book.pausedDays} day${book.pausedDays === 1 ? '' : 's'} ago`;
    return `${paused} · ${donePct}% of the weight read`;
  }
  const sittings = book.sittings ? ` · read in ${book.sittings} sittings` : '';
  return `${book.partCount} parts${sittings}`;
}

function BookRow({ book, onOpen }) {
  const [chipWord, chipBg, chipFg] = CHIPS[book.state] || CHIPS.new;
  const chip = chipWord ?? `part ${book.at + 1} of ${book.partCount}`;
  const done = book.state === 'read' ? 1 : cum(book.partCount, book.at);
  const donePct = Math.round(done * 100);

  return (
    <button
      className="tap row"
      onClick={onOpen}
      style={{
        padding: '22px 24px',
        borderRadius: 14,
        background: 'var(--bg-surface-hover)',
        border: `1px solid ${
          book.state === 'reading' ? 'var(--border-strong)' : 'var(--border-default)'
        }`,
      }}
    >
      <div style={{ display: 'flex', gap: 20, alignItems: 'flex-start' }}>
        <Patch patch={book.patch} size={56} />
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              justifyContent: 'space-between',
              gap: 18,
            }}
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              <span
                style={{
                  fontFamily: 'var(--font-display-wide)',
                  fontSize: 20,
                  fontWeight: 600,
                  lineHeight: 1.3,
                  color: 'var(--text-primary)',
                }}
              >
                {book.subtitle ? `${book.title}: ${book.subtitle}` : book.title}
              </span>
              <span
                style={{
                  font: "400 12.5px 'Space Grotesk', system-ui",
                  color: 'var(--text-secondary)',
                }}
              >
                {book.author} · {book.category} · {book.pages} pages
              </span>
            </div>
            <span
              style={{
                flex: 'none',
                padding: '4px 9px',
                borderRadius: 4,
                font: "600 8.5px 'IBM Plex Mono', monospace",
                letterSpacing: 'var(--track-chip)',
                textTransform: 'uppercase',
                background: chipBg,
                color: chipFg,
              }}
            >
              {chip}
            </span>
          </div>
          <ProgressBar
            pct={`${donePct}%`}
            fill={book.state === 'read' ? 'var(--shore-400)' : 'var(--accent)'}
          />
          <span
            style={{ font: "400 11.5px 'IBM Plex Mono', monospace", color: 'var(--text-muted)' }}
          >
            {metaLine(book, donePct)}
          </span>
        </div>
      </div>
    </button>
  );
}

export default function Shelf({ books, counts, themeLabel, onOpen, filter, onFilter }) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        minHeight: 1112,
        boxSizing: 'border-box',
        padding: '40px 44px 34px',
      }}
    >
      <span
        style={{
          font: "600 10px 'IBM Plex Mono', monospace",
          letterSpacing: 'var(--track-eyebrow)',
          textTransform: 'uppercase',
          color: 'var(--text-muted)',
        }}
      >
        {counts.total} books · {counts.read} read
      </span>
      <h1
        style={{
          margin: '10px 0 0',
          fontFamily: 'var(--font-display-wide)',
          fontSize: 36,
          fontWeight: 600,
          lineHeight: 1.14,
          color: 'var(--text-primary)',
        }}
      >
        Your shelf
      </h1>
      <p
        style={{
          margin: '12px 0 0',
          maxWidth: '44ch',
          fontFamily: 'var(--font-display-wide)',
          fontSize: 16,
          lineHeight: 1.8,
          color: 'var(--text-secondary)',
        }}
      >
        Pick up where you stopped, start something new, or look back at one you finished. The patch
        tells you the kind of book before you read a word.
      </p>

      {/* The design was drawn against three books; this shelf holds hundreds, so the
          rows are filtered rather than paged — one unit of work per screen still holds. */}
      <div style={{ display: 'flex', gap: 8, marginTop: 24 }}>
        {[
          ['reading', 'Reading'],
          ['new', 'Not started'],
          ['read', 'Read'],
        ].map(([value, label]) => (
          <button
            key={value}
            type="button"
            className="tap"
            onClick={() => onFilter(value)}
            style={{
              width: 'auto',
              padding: '7px 13px',
              borderRadius: 10,
              font: "500 12px 'Space Grotesk', system-ui",
              background: filter === value ? 'var(--accent)' : 'transparent',
              color: filter === value ? 'var(--accent-on)' : 'var(--text-secondary)',
              border: `1px solid ${filter === value ? 'var(--accent)' : 'var(--border-strong)'}`,
            }}
          >
            {label}
          </button>
        ))}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginTop: 20 }}>
        {books.length === 0 ? (
          <span
            style={{ font: "400 12.5px 'Space Grotesk', system-ui", color: 'var(--text-muted)' }}
          >
            Nothing here yet.
          </span>
        ) : (
          books.map((book) => (
            <BookRow key={book.key} book={book} onOpen={() => onOpen(book.key)} />
          ))
        )}
      </div>

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 16,
          marginTop: 'auto',
          paddingTop: 26,
          borderTop: '1px solid var(--border-subtle)',
        }}
      >
        <span style={{ font: "400 11.5px 'IBM Plex Mono', monospace", color: 'var(--text-muted)' }}>
          books/available · books/read
        </span>
        <span style={{ font: "400 11.5px 'IBM Plex Mono', monospace", color: 'var(--text-muted)' }}>
          {themeLabel}
        </span>
      </div>
    </div>
  );
}
