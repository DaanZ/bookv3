import { useCallback, useEffect, useRef, useState } from 'react';

import Patch from '../components/Patch';
import { Button, Chip, ProgressBar, QuietLink } from '../components/ui';
import { clearJobs, deleteBook, getJobs, moveBook, uploadPdf } from '../lib/api';

// Managing the collection, and feeding the pipeline.
//
// The reader is one unit of work per screen; this is the opposite kind of surface — a
// desk where you can see everything at once. It still keeps the reader's shape: the
// same 834px card, the same type roles, mono for every count and identifier.

const STATUS_TONE = { done: 'current', running: 'claimed', queued: 'neutral', failed: 'expired' };

function JobRow({ job }) {
  const total = job.chunksTotal;
  const pct = total ? Math.round((job.chunksDone / total) * 100) : job.status === 'done' ? 100 : 0;

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        padding: '16px 18px',
        borderRadius: 13,
        background: 'var(--bg-surface-hover)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
          <span
            style={{
              fontFamily: 'var(--font-display-wide)',
              fontSize: 15,
              fontWeight: 600,
              color: 'var(--text-primary)',
            }}
          >
            {job.title || job.filename}
          </span>
          <span style={{ font: "400 11.5px 'IBM Plex Mono', monospace", color: 'var(--text-muted)' }}>
            {job.author ? `${job.author} · ` : ''}
            {job.pages ? `${job.pages} pages · ` : ''}
            {(job.bytes / 1e6).toFixed(1)} MB
          </span>
        </div>
        <Chip tone={STATUS_TONE[job.status] || 'neutral'}>{job.status}</Chip>
      </div>

      {job.status !== 'failed' && (
        <>
          <ProgressBar
            pct={`${pct}%`}
            fill={job.status === 'done' ? 'var(--shore-400)' : 'var(--accent)'}
          />
          <span style={{ font: "400 10.5px 'IBM Plex Mono', monospace", color: 'var(--text-muted)' }}>
            {job.status === 'done'
              ? `${total || 0} parts written to books/available`
              : job.step || 'waiting'}
            {total ? ` · ${job.chunksDone}/${total}` : ''}
          </span>
        </>
      )}

      {job.error && (
        <span style={{ font: "400 12px/1.6 'Space Grotesk', system-ui", color: 'var(--chip-expired-fg)' }}>
          {job.error}
        </span>
      )}
    </div>
  );
}

function CollectionRow({ book, onMove, onDelete, busy }) {
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
      <Patch patch={book.patch} size={26} />
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

export default function Library({ books, counts, onShelf, onChanged }) {
  const [jobs, setJobs] = useState([]);
  const [hasKey, setHasKey] = useState(true);
  const [error, setError] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(0);
  const [busyKey, setBusyKey] = useState(null);
  const [query, setQuery] = useState('');
  const inputRef = useRef(null);

  const refreshJobs = useCallback(async () => {
    try {
      const data = await getJobs();
      setJobs(data.jobs);
      setHasKey(data.hasKey);
      return data.jobs;
    } catch (ex) {
      setError(ex.message);
      return [];
    }
  }, []);

  useEffect(() => {
    refreshJobs();
  }, [refreshJobs]);

  // Poll only while something is actually moving; a settled list is left alone.
  const active = jobs.some((j) => j.status === 'queued' || j.status === 'running');
  useEffect(() => {
    if (!active) return undefined;
    const timer = setInterval(async () => {
      const next = await refreshJobs();
      // A finished job means a new book on the shelf.
      if (!next.some((j) => j.status === 'queued' || j.status === 'running')) onChanged();
    }, 2000);
    return () => clearInterval(timer);
  }, [active, refreshJobs, onChanged]);

  const send = useCallback(
    async (files) => {
      const pdfs = [...files].filter((f) => f.name.toLowerCase().endsWith('.pdf'));
      if (pdfs.length === 0) {
        setError('Only PDF files can be ingested.');
        return;
      }
      setError(null);
      setUploading(pdfs.length);
      for (const file of pdfs) {
        try {
          await uploadPdf(file);
        } catch (ex) {
          setError(`${file.name}: ${ex.message}`);
        }
        setUploading((n) => n - 1);
      }
      refreshJobs();
    },
    [refreshJobs],
  );

  const onMove = async (book, finished) => {
    setBusyKey(book.key);
    try {
      await moveBook(book.key, finished);
      onChanged();
    } catch (ex) {
      setError(ex.message);
    }
    setBusyKey(null);
  };

  const onDelete = async (key) => {
    setBusyKey(key);
    try {
      await deleteBook(key);
      onChanged();
    } catch (ex) {
      setError(ex.message);
    }
    setBusyKey(null);
  };

  const needle = query.trim().toLowerCase();
  const shown = needle
    ? books.filter(
        (b) =>
          b.title.toLowerCase().includes(needle) ||
          (b.author || '').toLowerCase().includes(needle) ||
          (b.category || '').toLowerCase().includes(needle),
      )
    : books;

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
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 20 }}>
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
            Your library
          </h1>
        </div>
        <QuietLink onClick={onShelf}>Shelf</QuietLink>
      </div>

      <p
        style={{
          margin: '12px 0 0',
          maxWidth: '52ch',
          fontFamily: 'var(--font-display-wide)',
          fontSize: 16,
          lineHeight: 1.8,
          color: 'var(--text-secondary)',
        }}
      >
        Add a PDF and the pipeline reads it, splits it into parts and writes the highlighted
        summary the reader shows. It takes a few minutes a book — one at a time, so you can watch
        one finish.
      </p>

      {!hasKey && (
        <div
          style={{
            marginTop: 20,
            padding: '14px 16px',
            borderRadius: 13,
            background: 'var(--chip-expired-bg)',
            color: 'var(--chip-expired-fg)',
            font: "400 12.5px/1.6 'Space Grotesk', system-ui",
          }}
        >
          OPENAI_API_KEY is not set, so the pipeline cannot run. Uploads are still accepted and
          queued — they will fail until the key is in .env and the server is restarted.
        </div>
      )}

      {error && (
        <div
          style={{
            marginTop: 20,
            padding: '14px 16px',
            borderRadius: 13,
            background: 'var(--chip-expired-bg)',
            color: 'var(--chip-expired-fg)',
            font: "400 12.5px/1.6 'Space Grotesk', system-ui",
          }}
        >
          {error}
        </div>
      )}

      {/* Drop target. A dashed edge is the one place the design's hairline rule bends —
          it has to read as "incomplete until you put something here". */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          send(e.dataTransfer.files);
        }}
        style={{
          marginTop: 24,
          padding: '30px 24px',
          borderRadius: 14,
          border: `1px dashed ${dragging ? 'var(--accent)' : 'var(--border-strong)'}`,
          background: dragging ? 'var(--bg-surface-hover)' : 'transparent',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 14,
          transition: 'border-color var(--dur-instant, 90ms) var(--ease-move, ease)',
        }}
      >
        <span
          style={{
            font: "400 13.5px 'Space Grotesk', system-ui",
            color: 'var(--text-secondary)',
            textAlign: 'center',
          }}
        >
          {uploading > 0
            ? `Uploading ${uploading} file${uploading === 1 ? '' : 's'}…`
            : 'Drop PDFs here, or choose them from your machine.'}
        </span>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          multiple
          onChange={(e) => {
            send(e.target.files);
            e.target.value = '';
          }}
          style={{ display: 'none' }}
        />
        <Button size="lg" onClick={() => inputRef.current?.click()} disabled={uploading > 0}>
          Choose PDFs
        </Button>
      </div>

      {jobs.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 26 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span
              style={{
                font: "600 9.5px 'IBM Plex Mono', monospace",
                letterSpacing: 'var(--track-eyebrow)',
                textTransform: 'uppercase',
                color: 'var(--text-muted)',
              }}
            >
              processing
            </span>
            {!active && (
              <QuietLink
                onClick={async () => {
                  await clearJobs();
                  refreshJobs();
                }}
              >
                Clear finished
              </QuietLink>
            )}
          </div>
          {jobs.map((job) => (
            <JobRow key={job.id} job={job} />
          ))}
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 30 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
          <span
            style={{
              font: "600 9.5px 'IBM Plex Mono', monospace",
              letterSpacing: 'var(--track-eyebrow)',
              textTransform: 'uppercase',
              color: 'var(--text-muted)',
            }}
          >
            the collection · {shown.length} shown
          </span>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter by title, author or category"
            style={{
              width: 280,
              padding: '8px 12px',
              borderRadius: 'var(--radius-input)',
              border: '1px solid var(--border-strong)',
              background: 'transparent',
              color: 'var(--text-primary)',
              font: "400 12px 'Space Grotesk', system-ui",
              outline: 'none',
            }}
          />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {shown.slice(0, 60).map((book) => (
            <CollectionRow
              key={book.key}
              book={book}
              busy={busyKey === book.key}
              onMove={onMove}
              onDelete={onDelete}
            />
          ))}
        </div>
        {shown.length > 60 && (
          <span style={{ font: "400 11.5px 'IBM Plex Mono', monospace", color: 'var(--text-muted)' }}>
            … and {shown.length - 60} more · narrow the filter to reach them
          </span>
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
          next/ → books/available · pdfs/
        </span>
        <QuietLink onClick={onShelf}>Back to shelf</QuietLink>
      </div>
    </div>
  );
}
