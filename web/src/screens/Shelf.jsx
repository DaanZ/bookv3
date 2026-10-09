import Patch from '../components/Patch';
import IntelligencePill, { INTELLIGENCES } from '../components/IntelligencePill';
import SpiralPill from '../components/SpiralPill';
import SpiralRange from '../components/SpiralRange';
import { Button, ProgressBar, QuietLink, Sheet } from '../components/ui';
import { useNarrow } from '../lib/prefs';
import { cum, paletteFor } from '../lib/reading';

// Choose what to read; see at a glance what each book is and where you left it.

const CHIPS = {
  new: ['not started', 'var(--chip-neutral-bg)', 'var(--chip-neutral-fg)'],
  reading: [null, 'var(--chip-claimed-bg)', 'var(--chip-claimed-fg)'],
  read: ['read', 'var(--chip-current-bg)', 'var(--chip-current-fg)'],
  // A read book with a quest started and not yet reflected on. It takes the place of
  // "read" because it names what is left to do, and opening the book lands on the quest.
  questOpen: ['quest open', 'var(--chip-claimed-bg)', 'var(--chip-claimed-fg)'],
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

// The book you are reading is the shelf's one next action, so it wears the accent: the 10
// of the 60-30-10 split. Its text and chip switch to the accent's own ink.
const NEXT = {
  background: 'var(--accent)',
  '--bg-surface-hover': 'var(--accent)',
  '--text-primary': 'var(--accent-on)',
  '--text-secondary': 'var(--accent-on)',
  '--text-muted': 'var(--accent-on)',
  '--border-subtle': 'rgba(20,32,31,.16)',
};

function BookRow({ book, gradient, onOpen, narrow, next = false }) {
  const chipKey = book.state === 'read' && book.questsOpen ? 'questOpen' : book.state;
  const [chipWord, chipBg, chipFg] = next
    ? [CHIPS[chipKey]?.[0], 'rgba(20,32,31,.16)', 'var(--accent-on)']
    : CHIPS[chipKey] || CHIPS.new;
  const chip = chipWord ?? `part ${book.at + 1} of ${book.partCount}`;
  const done = book.state === 'read' ? 1 : cum(book.partCount, book.at);
  const donePct = Math.round(done * 100);

  return (
    <button
      className="tap row"
      onClick={onOpen}
      style={{
        padding: narrow ? '16px' : '22px 24px',
        borderRadius: 14,
        background: 'var(--bg-surface-hover)',
        border: `1px solid ${
          next ? 'var(--accent)' : book.state === 'reading' ? 'var(--border-strong)' : 'var(--border-default)'
        }`,
        ...(next ? NEXT : null),
      }}
    >
      <div style={{ display: 'flex', gap: narrow ? 14 : 20, alignItems: 'flex-start' }}>
        <Patch patch={book.patch} size={narrow ? 40 : 56} />
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 }}>
          {/* Side by side the chip takes a column the title needs; on a phone it goes
              above the title instead, so a long title wraps across the whole row. */}
          <div
            style={{
              display: 'flex',
              flexDirection: narrow ? 'column-reverse' : 'row',
              alignItems: 'flex-start',
              justifyContent: 'space-between',
              gap: narrow ? 8 : 18,
            }}
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              <span
                style={{
                  fontFamily: 'var(--font-display-wide)',
                  fontSize: narrow ? 17 : 20,
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
            {/* The reader's state, then the book's Spiral Dynamics level beneath it. */}
            <div
              style={{
                flex: 'none',
                display: 'flex',
                flexDirection: narrow ? 'row' : 'column',
                alignItems: narrow ? 'center' : 'flex-end',
                gap: 6,
              }}
            >
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
              <SpiralPill spiral={book.spiral} onAccent={next} />
              <IntelligencePill intelligence={book.intelligence} onAccent={next} />
            </div>
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

export default function Shelf({
  books,
  counts,
  themeLabel,
  who,
  onOpen,
  filter,
  onFilter,
  sort,
  onSort,
  spiralRange,
  spiralScores = [],
  onSpiralRange,
  intelligence = null,
  intelligenceCounts = null,
  onIntelligence,
  onLibrary,
  onProfiles,
  onLock,
  palette,
  day,
}) {
  // One ramp for the whole shelf, built once rather than per row.
  const gradient = paletteFor(palette || 'sunset', !!day, 8);
  const narrow = useNarrow();

  // Filters are the controls a phone reaches for most, so there they are full touch
  // targets (44px) rather than the tablet's compact chips.
  // The first book in progress is the one to pick up: the shelf's single accent.
  const nextKey = books.find((book) => book.state === 'reading')?.key;
  const control = (on) => ({
    width: 'auto',
    padding: narrow ? '12px 16px' : '7px 13px',
    borderRadius: 10,
    font: `500 ${narrow ? 14 : 12}px 'Space Grotesk', system-ui`,
    whiteSpace: 'nowrap',
    background: on ? 'var(--accent)' : 'transparent',
    color: on ? 'var(--accent-on)' : 'var(--text-secondary)',
    border: `1px solid ${on ? 'var(--accent)' : 'var(--border-strong)'}`,
  });
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        minHeight: narrow ? 0 : 1112,
        boxSizing: 'border-box',
        padding: narrow ? '26px 18px 24px' : '32px 44px 22px',
      }}
    >
      {/* The header: what this is, and for the owner the way to the library beside it.
          The library link sat in the footer, below a list of hundreds of books. */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 }}>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <span
            style={{
              font: "600 10px 'IBM Plex Mono', monospace",
              letterSpacing: 'var(--track-eyebrow)',
              textTransform: 'uppercase',
              color: 'var(--text-muted)',
            }}
          >
            {counts.total} books · {counts.read} read
            {who ? ` · ${who.name}` : ''}
          </span>
          <h1
            style={{
              margin: '10px 0 0',
              fontFamily: 'var(--font-display-wide)',
              fontSize: narrow ? 30 : 36,
              fontWeight: 600,
              lineHeight: 1.14,
              color: 'var(--text-primary)',
            }}
          >
            Your shelf
          </h1>
        </div>
        {/* Adding and removing books is the owner's. Nobody else is shown the door —
            and the API refuses it too, so this is the label on a rule, not the rule. */}
        {who?.owner && (
          <Button variant="secondary" onClick={onLibrary} style={{ minHeight: 44, flex: 'none' }}>
            Library
          </Button>
        )}
      </div>
      {/* On a phone the introduction costs a screenful before the first book, and says
          nothing a reader needs twice. */}
      {!narrow && (
      <p
        style={{
          margin: '12px 0 0',
          maxWidth: '44ch',
          fontFamily: 'var(--font-display-wide)',
          fontSize: narrow ? 15 : 16,
          lineHeight: narrow ? 1.65 : 1.8,
          color: 'var(--text-secondary)',
        }}
      >
        {`Pick up where you stopped, start something new, or look back at one you finished. The
          patch tells you the kind of book before you read a word, and every page you keep is
          ${who?.name ? `${who.name}'s` : 'yours'} alone.`}
      </p>
      )}

      {/* The sheet: the list and its filters, on the graphite page inside the indigo
          frame. The filters moved onto it from the frame, where they made the header band
          — and the frame — taller than its 30. */}
      <Sheet grow narrow={narrow} style={{ marginTop: 22 }}>
      {/* The design was drawn against three books; this shelf holds hundreds, so the
          rows are filtered rather than paged — one unit of work per screen still holds. */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: narrow ? 8 : 12,
          marginTop: 18,
        }}
      >
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
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
              style={control(filter === value)}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Order, not a filter — so it is one control that names its current state,
            rather than a second row of chips competing with the first. It was a button
            that swapped between two orders; with the spiral grades there are four, so it
            is a select. Not on a phone: there the three filters get the line to
            themselves, and the order is the default shuffle. */}
        {/* Which intelligence, beside the order: a narrowing, but one with nine answers,
            so a select like the order rather than nine more chips. Each says how many
            books here ask for it. Hidden until books are graded, and on a phone. */}
        {!narrow && intelligenceCounts && onIntelligence && (
        <select
          value={intelligence || ''}
          onChange={(e) => onIntelligence(e.target.value || null)}
          aria-label="Intelligence the books ask for"
          className="tap"
          style={{ ...control(Boolean(intelligence)), marginLeft: 'auto', cursor: 'pointer', background: intelligence ? 'var(--accent)' : 'var(--bg-sheet)' }}
        >
          <option value="">Every intelligence</option>
          {INTELLIGENCES.map(([key, name]) => (
            <option key={key} value={key}>
              {name} ({intelligenceCounts[key]})
            </option>
          ))}
        </select>
        )}
        {!narrow && (
        <select
          value={sort}
          onChange={(e) => onSort(e.target.value)}
          aria-label="Order of the books"
          className="tap"
          style={{ ...control(false), marginLeft: intelligenceCounts ? 0 : 'auto', cursor: 'pointer', background: 'var(--bg-sheet)' }}
        >
          <option value="shuffled">Shuffled</option>
          <option value="added">Recently added</option>
          <option value="spiral-low">Spiral, low to high</option>
          <option value="spiral-high">Spiral, high to low</option>
        </select>
        )}
      </div>

      {/* Narrow the unread books to a band of the spiral, to choose what to start, or the
          read ones, to look back over a kind of book. */}
      {filter !== 'reading' && onSpiralRange && (
        <SpiralRange scores={spiralScores} value={spiralRange} onChange={onSpiralRange} count={books.length} />
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
            <BookRow key={book.key} book={book} gradient={gradient} narrow={narrow}
                     next={book.key === nextKey} onOpen={() => onOpen(book.key)} />
          ))
        )}
      </div>
      </Sheet>

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 16,
          marginTop: narrow ? 28 : 14,
          paddingTop: 16,
          borderTop: '1px solid var(--border-subtle)',
        }}
      >
        {/* The footer used to name the folders the books are filed in. That is where the
            implementation keeps them, not anything a reader needs to know — the shelf
            already says what is read and what is not. */}
        <span />
        <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 16 }}>
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
        </div>
      </div>
    </div>
  );
}
