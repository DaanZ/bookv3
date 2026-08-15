import Patch from '../components/Patch';
import { ProgressBar, QuietLink } from '../components/ui';
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

/**
 * One suggestion, with the book it came from named.
 *
 * Only on the "not started" filter, because that is the question it answers, and only
 * one — a shelf that opens with a row of recommendations is a shop.
 */
function Suggestion({ entry, onOpen }) {
  return (
    <button
      className="tap row"
      onClick={onOpen}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        padding: '14px 18px',
        borderRadius: 14,
        background: 'transparent',
        border: '1px dashed var(--border-strong)',
      }}
    >
      <Patch patch={entry.book.patch} size={34} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0, textAlign: 'left' }}>
        <span
          style={{
            font: "600 9.5px 'IBM Plex Mono', monospace",
            letterSpacing: 'var(--track-eyebrow)',
            textTransform: 'uppercase',
            color: 'var(--text-muted)',
          }}
        >
          because you read {entry.because.title}
        </span>
        <span
          style={{
            fontFamily: 'var(--font-display-wide)',
            fontSize: 17,
            fontWeight: 600,
            color: 'var(--text-primary)',
          }}
        >
          {entry.book.title}
        </span>
      </div>
    </button>
  );
}

export default function Shelf({
  books,
  counts,
  themeLabel,
  who,
  suggestion,
  onOpen,
  filter,
  onFilter,
  onLibrary,
  onProfiles,
  onLock,
}) {
  const guest = !who || who.guest;
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
        {counts.total} books{guest ? '' : ` · ${counts.read} read`}
        {who ? ` · ${who.name}` : ''}
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
        {guest ? 'The catalogue' : 'Your shelf'}
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
        {guest
          ? `Read anything here — the catalogue is open and asks nobody who they are. Picking a
             profile is what makes it yours: a page kept in every book, and books suggested from
             the ones you have read.`
          : `Pick up where you stopped, start something new, or look back at one you finished. The
             patch tells you the kind of book before you read a word, and every page you keep is
             ${who.name}'s alone.`}
      </p>

      {/* The design was drawn against three books; this shelf holds hundreds, so the
          rows are filtered rather than paged — one unit of work per screen still holds.
          A guest has no reading to filter: two of the three would always be empty, so
          the catalogue is shown whole instead of behind a control that does nothing. */}
      <div style={{ display: guest ? 'none' : 'flex', gap: 8, marginTop: 24 }}>
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

      {filter === 'new' && suggestion && (
        <div style={{ marginTop: 20 }}>
          <Suggestion entry={suggestion} onOpen={() => onOpen(suggestion.book.key)} />
        </div>
      )}

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
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <span style={{ font: "400 11.5px 'IBM Plex Mono', monospace", color: 'var(--text-muted)' }}>
            {themeLabel}
          </span>
          {/* Who these bookmarks belong to, and the way to be somebody else. Named
              rather than labelled "profiles": the question the row answers is whose
              page this is. */}
          {who && (
            <QuietLink onClick={onProfiles}>
              <span
                aria-hidden="true"
                style={{
                  display: 'inline-block',
                  width: 8,
                  height: 8,
                  borderRadius: 2,
                  marginRight: 7,
                  background: who.tone,
                  verticalAlign: 'baseline',
                }}
              />
              {who.name}
            </QuietLink>
          )}
          {/* Only where there is something to lock. On a profile with no PIN this
              would be a button that closes the shelf and then opens it again. */}
          {onLock && <QuietLink onClick={onLock}>Lock</QuietLink>}
          {/* Adding and removing books is the owner's. Nobody else is shown the door —
              and the API refuses it too, so this is the label on a rule, not the rule. */}
          {who?.owner && <QuietLink onClick={onLibrary}>Library</QuietLink>}
        </div>
      </div>
    </div>
  );
}
