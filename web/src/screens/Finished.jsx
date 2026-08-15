import { useState } from 'react';

import Patch from '../components/Patch';
import { Button, Chip, QuietLink } from '../components/ui';
import { resyncHardcover } from '../lib/api';

/** 1st, 2nd, 3rd, 4th — English ordinals, including the teens that break the rule. */
function ordinal(n) {
  const tens = n % 100;
  if (tens >= 11 && tens <= 13) return `${n}th`;
  return `${n}${['th', 'st', 'nd', 'rd'][n % 10] || 'th'}`;
}

// Close the loop and offer a jump to a different topic.
// "Switching topics beats stopping": when attention is spent, offer the book furthest
// from what was just read.

export default function Finished({
  book,
  who,
  result,
  recommendation,
  counts,
  onOpenRec,
  onNextRec,
  onShelf,
}) {
  // The result of the call just made, or the outcome recorded when it was finished
  // before. undefined/null means neither exists — say that, do not guess.
  // A re-sync supersedes both: it is the most recent thing Hardcover said.
  const [resync, setResync] = useState(null);
  const [syncing, setSyncing] = useState(false);

  const latest = resync ?? result;
  const marked = latest ? latest.markedRead : book.markedRead;
  const number = latest?.finishNumber ?? book.finishNumber;

  // Hardcover is one account, reached with one key, and it is the owner's. A guest's
  // finish is real and recorded — it is simply theirs and not a write to somebody
  // else's public shelf, and this block says which rather than showing them a chip
  // about a call that was never made on their behalf.
  const guest = who ? !who.owner : false;

  const recheck = async () => {
    setSyncing(true);
    try {
      setResync(await resyncHardcover(book.key));
    } catch (ex) {
      setResync({ markedRead: false, hardcoverError: ex.message });
    }
    setSyncing(false);
  };

  const partCount = book.partCount ?? book.parts?.length ?? 0;
  const titles = book.partTitles ?? (book.parts || []).map((p) => p.title);

  const sittings =
    book.sittings && book.days != null
      ? ` · read in ${book.sittings} sitting${book.sittings === 1 ? '' : 's'} over ${book.days} day${
          book.days === 1 ? '' : 's'
        }`
      : book.sittings
        ? ` · read in ${book.sittings} sitting${book.sittings === 1 ? '' : 's'}`
        : '';

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
        {partCount} of {partCount} parts · 100%
        {/* Which number this book was to be finished here. Counted from recorded
            finishes, so it is a fact about this app's history, not a guess about the
            books that were already sitting in books/read. */}
        {number ? ` · your ${ordinal(number)} finished book` : ''}
      </span>

      <div
        style={{
          height: 4,
          borderRadius: 2,
          marginTop: 20,
          background: 'var(--border-subtle)',
        }}
      >
        <div style={{ height: 4, width: '100%', borderRadius: 2, background: 'var(--shore-400)' }} />
      </div>

      <h1
        style={{
          margin: '28px 0 0',
          maxWidth: '24ch',
          fontFamily: 'var(--font-display-wide)',
          fontSize: 38,
          fontWeight: 600,
          lineHeight: 1.16,
          color: 'var(--text-primary)',
          textWrap: 'pretty',
        }}
      >
        You finished {book.title}
      </h1>
      <p
        style={{
          margin: '16px 0 0',
          maxWidth: '46ch',
          fontFamily: 'var(--font-display-wide)',
          fontSize: 17,
          lineHeight: 1.8,
          color: 'var(--text-secondary)',
        }}
      >
        {book.author} · {book.pages} pages{sittings}
      </p>

      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 11,
          marginTop: 26,
          padding: '18px 20px',
          borderRadius: 13,
          background: 'var(--bg-surface-hover)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {guest ? (
            <>
              <Chip tone="claimed">your finish</Chip>
              <span
                style={{
                  font: "400 12.5px 'Space Grotesk', system-ui",
                  color: 'var(--text-secondary)',
                }}
              >
                kept for {who.name} · Hardcover is the owner's shelf, so nothing was sent
              </span>
            </>
          ) : (
            <>
          {/* Green only ever means finished — and never before Hardcover accepted it.
              "Not checked" is never rendered as "correct", so a book finished before
              this was recorded says so rather than claiming either outcome. */}
          <Chip tone={marked === true ? 'current' : 'neutral'}>
            {marked === true ? 'marked read' : marked === false ? 'not marked' : 'not recorded'}
          </Chip>
          <span
            style={{ font: "400 12.5px 'Space Grotesk', system-ui", color: 'var(--text-secondary)' }}
          >
            {marked === true
              ? latest?.alreadyRead
                ? 'already read on Hardcover'
                : 'on Hardcover'
              : marked === false
                ? latest?.hardcoverError || 'Hardcover did not accept it'
                : 'no Hardcover record for this book'}
          </span>
          {/* The outcome was recorded once and never revisited, so a call that failed
              for a reason of the moment stayed failed. This asks again. */}
          {marked !== true && (
            <QuietLink onClick={syncing ? undefined : recheck}>
              {syncing ? 'checking…' : 'check again'}
            </QuietLink>
          )}
            </>
          )}
        </div>

        {/* Matched on title alone: the author did not line up, so this may be the wrong
            edition — worth saying before it sits on a public shelf. */}
        {!guest && marked === true && latest?.titleOnlyMatch && latest?.hardcoverTitle && (
          <span style={{ font: "400 11.5px 'IBM Plex Mono', monospace", color: 'var(--text-muted)' }}>
            matched on title only → “{latest.hardcoverTitle}”
          </span>
        )}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 26 }}>
        <span
          style={{
            font: "600 9.5px 'IBM Plex Mono', monospace",
            letterSpacing: 'var(--track-eyebrow)',
            textTransform: 'uppercase',
            color: 'var(--text-muted)',
          }}
        >
          what you kept
        </span>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {titles.map((title, i) => (
            <div
              key={i}
              style={{
                display: 'flex',
                alignItems: 'baseline',
                gap: 12,
                padding: '9px 0',
                borderBottom: '1px solid var(--border-subtle)',
              }}
            >
              <span
                style={{
                  font: "500 10.5px 'IBM Plex Mono', monospace",
                  color: 'var(--text-muted)',
                }}
              >
                {String(i + 1).padStart(2, '0')}
              </span>
              <span
                style={{
                  fontFamily: "'Lexend Deca', 'Lexend', system-ui",
                  fontSize: 14.5,
                  lineHeight: 1.5,
                  color:
                    i === titles.length - 1 ? 'var(--text-primary)' : 'var(--text-secondary)',
                }}
              >
                {title}
              </span>
            </div>
          ))}
        </div>
      </div>

      {recommendation && (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 12,
            marginTop: 24,
            padding: '22px 24px',
            borderRadius: 14,
            border: '1px solid var(--border-default)',
            background: 'var(--bg-surface)',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              justifyContent: 'space-between',
              gap: 16,
            }}
          >
            <div style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
              <Patch patch={recommendation.patch} size={34} />
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span
                  style={{
                    font: "600 9.5px 'IBM Plex Mono', monospace",
                    letterSpacing: 'var(--track-eyebrow)',
                    textTransform: 'uppercase',
                    color: 'var(--text-muted)',
                  }}
                >
                  as far from {book.category} as your shelf goes
                </span>
                <span
                  style={{
                    fontFamily: 'var(--font-display-wide)',
                    fontSize: 19,
                    fontWeight: 600,
                    lineHeight: 1.3,
                    color: 'var(--text-primary)',
                  }}
                >
                  {recommendation.subtitle
                    ? `${recommendation.title}: ${recommendation.subtitle}`
                    : recommendation.title}
                </span>
                <span
                  style={{
                    font: "400 12.5px 'Space Grotesk', system-ui",
                    color: 'var(--text-secondary)',
                  }}
                >
                  {recommendation.author} · {recommendation.category} ·{' '}
                  {recommendation.partCount} parts
                </span>
              </div>
            </div>
            <Chip tone="seam">far side</Chip>
          </div>
          <div style={{ display: 'flex', gap: 11, marginTop: 4 }}>
            <Button size="lg" onClick={onOpenRec} style={{ minHeight: 52 }}>
              Read one part
            </Button>
            <Button size="lg" variant="secondary" onClick={onNextRec} style={{ minHeight: 52 }}>
              Show another
            </Button>
          </div>
        </div>
      )}

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 16,
          marginTop: 'auto',
          paddingTop: 22,
        }}
      >
        <span style={{ font: "400 11.5px 'IBM Plex Mono', monospace", color: 'var(--text-muted)' }}>
          {counts.total} books · {counts.read} read
        </span>
        <QuietLink onClick={onShelf}>Back to shelf</QuietLink>
      </div>
    </div>
  );
}
