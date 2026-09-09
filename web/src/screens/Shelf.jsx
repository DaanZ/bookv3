import Patch from '../components/Patch';
import { ProgressBar, QuietLink } from '../components/ui';
import { cum, paletteFor } from '../lib/reading';

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

function BookRow({ book, gradient, onOpen }) {
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
          <ProgressBar pct={`${donePct}%`} gradient={gradient} />
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
  sort,
  onSort,
  onLibrary,
  onProfiles,
  onLock,
  palette,
  day,
}) {
  const guest = !who || who.guest;
  // One ramp for the whole shelf, built once rather than per row.
  const gradient = paletteFor(palette || 'sunset', !!day, 8);
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
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
          marginTop: 24,
        }}
      >
        <div style={{ display: guest ? 'none' : 'flex', gap: 8 }}>
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

        {/* Order, not a filter — so it is one control that names its current state and
            swaps, rather than a second row of chips competing with the first. A guest
            gets it too: the catalogue is the one shelf they do see in full, and it is
            the longest, so ordering it is worth more to them than to anyone. */}
        <button
          type="button"
          className="tap"
          onClick={() => onSort(sort === 'added' ? 'title' : 'added')}
          title={
            sort === 'added'
              ? 'Sorted by date added, newest first. Switch to A–Z.'
              : 'Sorted A–Z. Switch to recently added.'
          }
          style={{
            width: 'auto',
            marginLeft: 'auto',
            padding: '7px 13px',
            borderRadius: 10,
            font: "500 12px 'Space Grotesk', system-ui",
            background: 'transparent',
            color: 'var(--text-secondary)',
            border: '1px solid var(--border-strong)',
            whiteSpace: 'nowrap',
          }}
        >
          {sort === 'added' ? 'Recently added' : 'A–Z'}
        </button>
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
            <BookRow key={book.key} book={book} gradient={gradient} onOpen={() => onOpen(book.key)} />
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
        {/* The footer used to name the folders the books are filed in. That is where the
            implementation keeps them, not anything a reader needs to know — the shelf
            already says what is read and what is not. */}
        <span />
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <span style={{ font: "400 11.5px 'IBM Plex Mono', monospace", color: 'var(--text-muted)' }}>
            {themeLabel}
          </span>
          {/* Who these bookmarks belong to, and the way to be somebody else.
              The name alone was the whole label here, on the reasoning that the question
              being answered is whose page this is. It failed: a name in a footer does not
              read as a control, so the one way to reach the profiles was invisible — and
              a reader told to "pick a profile" had nowhere to go. The name still leads,
              because it is the answer, but the destination is now said out loud. */}
          {who && (
            <QuietLink onClick={onProfiles} title="Switch reader, or add one">
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
              {who.name} · profiles
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
