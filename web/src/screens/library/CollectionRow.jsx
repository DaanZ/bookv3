import { useState } from 'react';

import { Button, Chip, QuietLink } from '../../components/ui';

import Cover from './Cover';

export default function CollectionRow({ book, onMove, onDelete, onEnrich, onContribute, busy }) {
  const [confirming, setConfirming] = useState(false);

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 14,
        padding: '11px 0',
        borderBottom: '1px solid var(--border-subtle)',
        opacity: busy ? 0.5 : 1,
      }}
    >
      <Cover book={book} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0 }}>
        <span
          style={{
            fontFamily: "'Lexend Deca', 'Lexend', system-ui",
            fontSize: 14.5,
            lineHeight: 1.4,
            color: 'var(--text-primary)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {book.title}
        </span>
        <span style={{ font: "400 10.5px 'IBM Plex Mono', monospace", color: 'var(--text-muted)' }}>
          {book.partCount} parts · {book.category}
          {book.hardcover?.rating ? ` · ★ ${book.hardcover.rating}` : ''}
          {book.finishNumber ? ` · #${book.finishNumber} finished` : ''}
          {/* Only says anything when there is something to say. A book with no recorded
              finish is not "not on Hardcover", it was simply never asked about. */}
          {book.markedRead === true ? ' · on hardcover' : ''}
          {book.markedRead === false ? ' · not on hardcover' : ''}
        </span>
      </div>

      {confirming ? (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span style={{ font: "400 11px 'Space Grotesk', system-ui", color: 'var(--chip-expired-fg)' }}>
            Delete the summary?
          </span>
          <Button size="sm" variant="secondary" onClick={() => setConfirming(false)}>
            Keep
          </Button>
          <Button size="sm" onClick={() => onDelete(book.key)}>
            Delete
          </Button>
        </div>
      ) : (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {/* Fetching costs one request and writes nothing to Hardcover, so it is a
              plain action. Adding the book to their catalogue is not — that goes
              through a confirm step that shows the payload first.

              Rarely the way a cover arrives any more: the background pass asks about
              every book by itself. "Look up" is jumping the queue on a book still
              waiting; "again" is a second opinion on one Hardcover answered no to. */}
          {!book.hardcover && (
            <QuietLink onClick={() => onEnrich(book.key)}>
              {book.hardcover === null ? 'Look up again' : 'Look up'}
            </QuietLink>
          )}
          {book.hardcover === null && book.isbn && (
            <QuietLink onClick={() => onContribute(book)}>Add to Hardcover</QuietLink>
          )}
          {/* Opened in a tab rather than navigated to: printing is a detour, and the
              library you were managing should still be there when the dialog closes.
              A hash URL, so it is also the thing you send somebody who wants the PDF. */}
          <QuietLink
            onClick={() =>
              window.open(`${window.location.pathname}#print/${encodeURIComponent(book.key)}`, '_blank')
            }
          >
            Print
          </QuietLink>
          <Chip tone={book.state === 'read' ? 'current' : 'neutral'}>
            {book.state === 'read' ? 'read' : book.state === 'reading' ? 'reading' : 'unread'}
          </Chip>
          <Button size="sm" variant="secondary" onClick={() => onMove(book, book.state !== 'read')}>
            {book.state === 'read' ? 'To unread' : 'To read'}
          </Button>
          <QuietLink onClick={() => setConfirming(true)}>Delete</QuietLink>
        </div>
      )}
    </div>
  );
}
