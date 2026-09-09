import { useCallback, useEffect, useRef, useState } from 'react';

import Patch from '../components/Patch';
import Spinner from '../components/Spinner';
import { Indexing, Summarising } from '../components/Waiting';
import { Button, Chip, ProgressBar, QuietLink } from '../components/ui';
import {
  clearJobs,
  deleteBook,
  enrichBook,
  estimatePdf,
  getEnrichment,
  getJobs,
  moveBook,
  unfinishBook,
  previewContribution,
  removeJob,
  resumeJob,
  submitContribution,
  uploadPdf,
} from '../lib/api';

// Managing the collection, and feeding the pipeline.
//
// The reader is one unit of work per screen; this is the opposite kind of surface — a
// desk where you can see everything at once. It still keeps the reader's shape: the
// same 834px card, the same type roles, mono for every count and identifier.

const STATUS_TONE = { done: 'current', running: 'claimed', queued: 'neutral', failed: 'expired' };

const MONO = "'IBM Plex Mono', monospace";

/** Sub-cent sums are the normal case here, so two decimals would read as "free". */
function money(amount) {
  if (amount == null) return '—';
  if (amount < 0.01) return `$${amount.toFixed(4)}`;
  if (amount < 1) return `$${amount.toFixed(3)}`;
  return `$${amount.toFixed(2)}`;
}

function thousands(n) {
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
function readableName(name) {
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

/** One model to spend on, with what it would cost for this book. */
function ModelChoice({ option, selected, onPick }) {
  const unusable = !option.fits;
  return (
    <button
      type="button"
      onClick={() => onPick(option.id)}
      disabled={unusable}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 14,
        width: '100%',
        padding: '9px 12px',
        borderRadius: 10,
        border: `1px solid ${selected ? 'var(--accent)' : 'var(--border-subtle)'}`,
        background: selected ? 'var(--bg-surface-hover)' : 'transparent',
        cursor: unusable ? 'not-allowed' : 'pointer',
        opacity: unusable ? 0.45 : 1,
        textAlign: 'left',
      }}
    >
      <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
        <span style={{ font: `400 12.5px ${MONO}`, color: 'var(--text-primary)' }}>
          {option.id}
        </span>
        <span style={{ font: `400 10.5px ${MONO}`, color: 'var(--text-muted)' }}>
          {unusable
            ? `context ${thousands(option.contextLength)} — too small for the biggest part`
            : `$${option.inputPerMillion.toFixed(2)} in · $${option.outputPerMillion.toFixed(2)} out per 1M`}
          {/* Whether this model has ever produced a highlighted book here. Cheap and
              untried is the combination that wastes a book, so it is said up front
              rather than discovered. */}
          {!unusable && (option.proven ? ' · proven here' : ' · never tried here')}
        </span>
      </span>
      <span
        style={{
          font: `600 13px ${MONO}`,
          color: selected ? 'var(--accent)' : 'var(--text-secondary)',
          whiteSpace: 'nowrap',
        }}
      >
        {money(option.cost)}
      </span>
    </button>
  );
}

/**
 * A book that has been read and priced, waiting for a yes.
 *
 * No model picker and no button of its own. Dropping three files used to raise three
 * identical dialogs asking the same question, so the choice moved out to the batch and
 * a row is now what it always should have been: this book, this size, this price.
 */
function EstimateRow({ item, model, onCancel }) {
  const { file, estimate } = item;

  if (item.error) {
    return (
      <div style={{ padding: '14px 16px', borderRadius: 13, background: 'var(--chip-expired-bg)' }}>
        <span style={{ font: "400 12.5px/1.6 'Space Grotesk', system-ui", color: 'var(--chip-expired-fg)' }}>
          {readableName(file.name)}: {item.error}
        </span>
        <div style={{ marginTop: 8 }}>
          <QuietLink onClick={() => onCancel(item.id)}>Dismiss</QuietLink>
        </div>
      </div>
    );
  }

  if (!estimate) {
    // Reading a 20MB PDF and counting its tokens takes a few seconds. The Spinner keeps
    // its own 400ms threshold, so a small file that measures instantly shows nothing.
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 13,
          padding: '14px 16px',
          borderRadius: 13,
          background: 'var(--bg-surface-hover)',
        }}
      >
        <Spinner variant="mark" size={22} />
        <span style={{ font: `400 12px ${MONO}`, color: 'var(--text-muted)' }}>
          {readableName(file.name)} · reading and measuring…
        </span>
      </div>
    );
  }

  const chosen = estimate.options.find((o) => o.id === model);

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        padding: '14px 16px',
        borderRadius: 13,
        background: 'var(--bg-surface-hover)',
      }}
    >
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
        <span
          style={{
            fontFamily: 'var(--font-display-wide)',
            fontSize: 14.5,
            fontWeight: 600,
            color: 'var(--text-primary)',
          }}
        >
          {readableName(file.name)}
        </span>
        <span style={{ font: `400 11px ${MONO}`, color: 'var(--text-muted)' }}>
          {estimate.pages} pages · {estimate.chunks} parts
          {estimate.emptyPages > 0 ? ` · ${estimate.emptyPages} pages with no text` : ''}
        </span>
      </div>
      <span style={{ font: `600 13px ${MONO}`, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
        {money(chosen?.cost)}
      </span>
      <QuietLink onClick={() => onCancel(item.id)}>Remove</QuietLink>
    </div>
  );
}

function JobRow({ job, onRemove, onResume, models = [], proven = [], palette, day }) {
  const total = job.chunksTotal;
  // A running job cannot be removed; the worker is still holding the file.
  const settled = job.status === 'done' || job.status === 'failed';

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
            {job.title || readableName(job.filename)}
          </span>
          <span style={{ font: "400 11.5px 'IBM Plex Mono', monospace", color: 'var(--text-muted)' }}>
            {job.author ? `${job.author} · ` : ''}
            {job.pages ? `${job.pages} pages · ` : ''}
            {(job.bytes / 1e6).toFixed(1)} MB
            {job.model ? ` · ${job.model}` : ''}
            {job.estimatedCost != null ? ` · quoted ${money(job.estimatedCost)}` : ''}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Chip tone={STATUS_TONE[job.status] || 'neutral'}>{job.status}</Chip>
          {/* A failed job can always be run again; whether that *resumes* depends on
              whether it got far enough to bank anything. Gating the control on having a
              checkpoint left the jobs that failed earliest — the ones most in need of a
              second go — with no way to start one. */}
          {job.status === 'failed' && (
            <QuietLink
              title={
                job.partsBought > 0
                  ? `Continue from part ${job.partsBought + 1} — the first ${job.partsBought} are already paid for`
                  : 'Run this book again on the same model'
              }
              onClick={() => onResume(job.id)}
            >
              {job.partsBought > 0 ? `Resume from ${job.partsBought + 1}` : 'Run again'}
            </QuietLink>
          )}
          {settled && <QuietLink onClick={() => onRemove(job.id)}>Remove</QuietLink>}
        </div>
      </div>

      {/* Summarising is the long stage — minutes — and gets the composite waiting state
          rather than a bar: there is no honest percentage for a dozen model calls of
          unknown length. Loading pages and reading meta finish fast and get nothing at
          all; the step line below already says what is happening. */}
      {job.status === 'running' && total > 0 && job.step !== 'indexing' && (
        <Summarising
          done={job.chunksDone}
          total={total}
          bounds={job.chunkBounds}
          palette={palette}
          day={day}
        />
      )}

      {job.status === 'running' && job.step === 'indexing' && <Indexing total={total || 0} />}

      {job.status === 'done' && (
        <>
          <ProgressBar pct="100%" fill="var(--shore-400)" />
          <span style={{ font: "400 10.5px 'IBM Plex Mono', monospace", color: 'var(--text-muted)' }}>
            {total || 0} parts written
          </span>
        </>
      )}

      {(job.status === 'queued' || (job.status === 'running' && !total)) && (
        <span style={{ font: "400 10.5px 'IBM Plex Mono', monospace", color: 'var(--text-muted)' }}>
          {job.step || 'waiting'}
        </span>
      )}

      {job.error && (
        <span style={{ font: "400 12px/1.6 'Space Grotesk', system-ui", color: 'var(--chip-expired-fg)' }}>
          {job.error}
        </span>
      )}

      {/* The usual reason a job fails is the model it was given, and the message says so
          — so the alternatives belong here, next to the sentence naming the culprit,
          rather than behind a re-upload. Choosing one drops any parts bought from the old
          model: half a book in one voice and half in another is worse than paying twice. */}
      {job.status === 'failed' && models.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span style={{ font: `400 10.5px ${MONO}`, color: 'var(--text-muted)' }}>
            try again with
          </span>
          {models
            .filter((id) => id !== job.model)
            .map((id) => (
              <button
                key={id}
                type="button"
                className="tap"
                onClick={() => onResume(job.id, id)}
                title={proven.includes(id) ? 'Has produced a highlighted book here' : 'Never tried here'}
                style={{
                  padding: '5px 10px',
                  borderRadius: 8,
                  border: `1px solid ${proven.includes(id) ? 'var(--accent)' : 'var(--border-strong)'}`,
                  background: 'transparent',
                  color: proven.includes(id) ? 'var(--accent)' : 'var(--text-secondary)',
                  font: `400 10.5px ${MONO}`,
                  cursor: 'pointer',
                }}
              >
                {id.split('/')[1] || id}
                {proven.includes(id) ? ' ✓' : ''}
              </button>
            ))}
        </div>
      )}
    </div>
  );
}

/**
 * The cover, where the library has one, falling back to the patch.
 *
 * Only on this screen. The reader's surfaces use coloured patches on purpose — a patch
 * says what family a book belongs to at a glance and never fails to load — and swapping
 * them for covers everywhere would be redesigning the shelf, not filling it in. The
 * library is the overview, and an overview is where a cover earns its place.
 *
 * The ground is painted in the cover's own dominant colour so the row does not flash an
 * empty box while the image arrives from Hardcover's CDN.
 */
function Cover({ book, size = 26 }) {
  const [failed, setFailed] = useState(false);
  if (!book.cover || failed) return <Patch patch={book.patch} size={size} />;

  return (
    <img
      src={book.cover}
      alt=""
      loading="lazy"
      onError={() => setFailed(true)}
      style={{
        width: size,
        height: Math.round(size * 1.5),
        objectFit: 'cover',
        borderRadius: 3,
        background: book.coverColor || 'var(--bg-surface-hover)',
        flexShrink: 0,
      }}
    />
  );
}

/**
 * How far the automatic cover pass has got.
 *
 * Every book is looked up by itself — on ingest, or on the first shelf load that sees
 * one nobody has asked about — so there is no button to describe. There is only this:
 * a line saying the thing is happening, and how much of it is left.
 */
function coverLine(covers) {
  if (!covers.enabled) return 'covers · HARDCOVER_API_KEY is not set, so none are looked up';

  const parts = [`${covers.found} found`];
  if (covers.missing) parts.push(`${covers.missing} not on Hardcover`);
  if (covers.failed) parts.push(`${covers.failed} failed`);
  if (covers.pending) parts.push(`${covers.pending} still to look up`);
  return `covers · ${parts.join(' · ')}`;
}

function CollectionRow({ book, onMove, onDelete, onEnrich, onContribute, busy }) {
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

export default function Library({ books, counts, palette, day, onShelf, onChanged }) {
  const [jobs, setJobs] = useState([]);
  const [hasKey, setHasKey] = useState(true);
  const [error, setError] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(0);
  const [pending, setPending] = useState([]);
  // One model for everything waiting. Asked once rather than per file, because dropping
  // three books raised three identical dialogs and the answer was the same every time.
  const [batchModel, setBatchModel] = useState(null);
  const [startingAll, setStartingAll] = useState(false);
  const [showAllModels, setShowAllModels] = useState(false);
  // What a failed job can be retried with, and which of those have actually worked here.
  const [jobModels, setJobModels] = useState([]);
  const [provenModels, setProvenModels] = useState([]);
  const [contribution, setContribution] = useState(null);
  const [busyKey, setBusyKey] = useState(null);
  const [query, setQuery] = useState('');
  const [covers, setCovers] = useState(null);
  const inputRef = useRef(null);

  const refreshJobs = useCallback(async () => {
    try {
      const data = await getJobs();
      setJobs(data.jobs);
      setJobModels(data.models || []);
      setProvenModels(data.proven || []);
      setHasKey(data.hasKey);
      return data.jobs;
    } catch (ex) {
      setError(ex.message);
      return [];
    }
  }, []);

  const refreshCovers = useCallback(async () => {
    try {
      const data = await getEnrichment();
      setCovers(data);
      return data;
    } catch {
      // The cover pass is not load-bearing, and neither is its status line.
      return null;
    }
  }, []);

  useEffect(() => {
    refreshJobs();
    refreshCovers();
  }, [refreshJobs, refreshCovers]);

  // Poll only while something is actually moving; a settled list is left alone.
  const active = jobs.some((j) => j.status === 'queued' || j.status === 'running');
  useEffect(() => {
    if (!active) return undefined;
    const timer = setInterval(async () => {
      const next = await refreshJobs();
      // A finished job means a new book on the shelf — and a cover being looked up.
      if (!next.some((j) => j.status === 'queued' || j.status === 'running')) {
        onChanged();
        refreshCovers();
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [active, refreshJobs, refreshCovers, onChanged]);

  // The shelf request is what starts the pass, so the collection in hand always
  // predates its results — by a whole library on the first run, by one book after an
  // ingest. Reconcile once on arrival: covers the ledger has and these rows do not mean
  // the collection is stale, not that Hardcover came back empty.
  const reconciled = useRef(false);
  useEffect(() => {
    if (reconciled.current || !covers || covers.pending) return;
    reconciled.current = true;
    if (covers.found > 0 && books.some((book) => !book.cover)) onChanged();
  }, [covers, books, onChanged]);

  // The first shelf load queues every book nobody has asked about, so this can be a few
  // hundred deep. Follow it while it runs and refresh the collection once at the end,
  // so the jackets arrive without anyone reloading the page.
  const enriching = (covers?.pending || 0) > 0;
  useEffect(() => {
    if (!enriching) return undefined;
    const timer = setInterval(async () => {
      const next = await refreshCovers();
      if (next && !next.pending) onChanged();
    }, 4000);
    return () => clearInterval(timer);
  }, [enriching, refreshCovers, onChanged]);

  // Picking a PDF prices it; it is not queued until the estimate is accepted. The file
  // is uploaded twice as a result — once to be read, once to be worked on — which is
  // the cost of never leaving an unconfirmed book sitting in next/.
  const send = useCallback(async (files) => {
    const pdfs = [...files].filter((f) => f.name.toLowerCase().endsWith('.pdf'));
    if (pdfs.length === 0) {
      setError('Only PDF files can be ingested.');
      return;
    }
    setError(null);
    setUploading(pdfs.length);

    for (const file of pdfs) {
      const id = `${file.name}-${file.size}-${Date.now()}-${Math.random()}`;
      setPending((list) => [...list, { id, file, estimate: null, model: null, error: null }]);
      try {
        const estimate = await estimatePdf(file);
        const preferred =
          estimate.options.find((o) => o.id === estimate.defaultModel && o.fits) ||
          estimate.options.find((o) => o.fits);
        setPending((list) =>
          list.map((item) => (item.id === id ? { ...item, estimate } : item)),
        );
        // The first estimate to land sets the default; later ones leave the choice alone,
        // so a second file never silently changes what the first one is about to cost.
        setBatchModel((current) => current || preferred?.id || null);
      } catch (ex) {
        setPending((list) =>
          list.map((item) => (item.id === id ? { ...item, error: ex.message } : item)),
        );
      }
      setUploading((n) => n - 1);
    }
  }, []);

  const pickModel = useCallback((id, model) => {
    setPending((list) => list.map((item) => (item.id === id ? { ...item, model } : item)));
  }, []);

  const dropPending = useCallback((id) => {
    setPending((list) => list.filter((item) => item.id !== id));
  }, []);

  /**
   * Send every priced book at once, on the one model chosen for the batch.
   *
   * Sequential rather than parallel: the worker takes one job at a time anyway, and
   * three uploads racing only means three ways for the same queue to be filled.
   */
  const startAll = useCallback(async () => {
    const ready = pending.filter((entry) => entry.estimate && !entry.error);
    if (!ready.length || !batchModel) return;
    setStartingAll(true);
    for (const item of ready) {
      const chosen = item.estimate.options.find((o) => o.id === batchModel);
      try {
        await uploadPdf(item.file, {
          chunks: item.estimate.chunks,
          model: batchModel,
          cost: chosen?.cost,
        });
        setPending((list) => list.filter((entry) => entry.id !== item.id));
      } catch (ex) {
        setPending((list) =>
          list.map((entry) => (entry.id === item.id ? { ...entry, error: ex.message } : entry)),
        );
      }
    }
    setStartingAll(false);
    refreshJobs();
  }, [pending, batchModel, refreshJobs]);


  const continueJob = useCallback(
    async (id, model) => {
      setError(null);
      try {
        await resumeJob(id, model);
      } catch (ex) {
        setError(ex.message);
      }
      refreshJobs();
    },
    [refreshJobs],
  );

  const dropJob = useCallback(
    async (id) => {
      try {
        await removeJob(id);
      } catch (ex) {
        setError(ex.message);
      }
      refreshJobs();
    },
    [refreshJobs],
  );

  // Read-only against Hardcover: fetches the cover and rating, writes nothing there.
  const onEnrich = async (key) => {
    setBusyKey(key);
    try {
      await enrichBook(key);
      onChanged();
    } catch (ex) {
      setError(`${key}: ${ex.message}`);
    }
    setBusyKey(null);
  };

  // Publishing to a catalogue other people read, so the payload is fetched and shown
  // first and nothing is sent until it is confirmed.
  const onContribute = async (book) => {
    setError(null);
    try {
      const preview = await previewContribution(book.key);
      setContribution({ book, ...preview });
    } catch (ex) {
      setError(`${book.title}: ${ex.message}`);
    }
  };

  const confirmContribution = async () => {
    const key = contribution.book.key;
    setContribution((c) => ({ ...c, sending: true }));
    try {
      await submitContribution(key);
      setContribution(null);
      onChanged();
    } catch (ex) {
      setContribution((c) => ({ ...c, sending: false, error: ex.message }));
    }
  };

  const onMove = async (book, finished) => {
    setBusyKey(book.key);
    try {
      // Marking read here is filing. *Un*marking is a correction, and filing alone was
      // not enough: it moved the JSON back but left the reader's finish record standing,
      // so the row said unread while the profile still counted it read. Undo goes
      // through the same endpoint the finish screen uses, which clears both.
      await (finished ? moveBook(book.key, true) : unfinishBook(book.key));
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

  // What the batch adds up to. Options come from the first priced book — every estimate
  // returns the same model list, and the prices differ per book only in the totals below.
  const priced = pending.filter((item) => item.estimate && !item.error);
  const modelOptions = priced[0]?.estimate?.options || [];
  const batchParts = priced.reduce((sum, item) => sum + (item.estimate.chunks || 0), 0);
  const batchCost = priced.reduce(
    (sum, item) => sum + (item.estimate.options.find((o) => o.id === batchModel)?.cost || 0),
    0,
  );

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
          OPENROUTER_API_KEY is not set, so the pipeline cannot run. Estimates still work — they
          read the PDF and call no model — but a queued book will fail until the key is in .env
          and the server is restarted.
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
            ? `Reading ${uploading} file${uploading === 1 ? '' : 's'}…`
            : 'Drop PDFs here, or choose them from your machine. You see the cost before anything runs.'}
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

      {/* Publishing to a shared catalogue. Every field that would be written is on
          screen before anything is sent, because the title and author were read off the
          first pages by a language model and nobody has checked them. */}
      {contribution && (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 11,
            marginTop: 24,
            padding: '18px 20px',
            borderRadius: 13,
            background: 'var(--bg-surface-hover)',
            border: '1px solid var(--border-strong)',
          }}
        >
          <span
            style={{
              font: `600 9.5px ${MONO}`,
              letterSpacing: 'var(--track-eyebrow)',
              textTransform: 'uppercase',
              color: 'var(--text-muted)',
            }}
          >
            add to hardcover · public catalogue
          </span>
          <p
            style={{
              margin: 0,
              maxWidth: '58ch',
              font: "400 12.5px/1.7 'Space Grotesk', system-ui",
              color: 'var(--text-secondary)',
            }}
          >
            This creates a book on hardcover.app that everyone using it will see. The title
            and author were read off the first pages by a model, so check them — a wrong
            record is harder to remove than to avoid.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            {Object.entries(contribution.payload).map(([field, value]) => (
              <span key={field} style={{ font: `400 11.5px ${MONO}`, color: 'var(--text-primary)' }}>
                {field}: {String(value)}
              </span>
            ))}
            <span style={{ font: `400 11.5px ${MONO}`, color: 'var(--text-muted)' }}>
              author: {contribution.author}
            </span>
          </div>
          {contribution.error && (
            <span style={{ font: "400 12px 'Space Grotesk', system-ui", color: 'var(--chip-expired-fg)' }}>
              {contribution.error}
            </span>
          )}
          <div style={{ display: 'flex', gap: 8 }}>
            <Button size="sm" variant="secondary" onClick={() => setContribution(null)}>
              Cancel
            </Button>
            <Button size="sm" onClick={confirmContribution} disabled={contribution.sending}>
              {contribution.sending ? 'Adding…' : 'Add to Hardcover'}
            </Button>
          </div>
        </div>
      )}

      {pending.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 26 }}>
          <span
            style={{
              font: `600 9.5px ${MONO}`,
              letterSpacing: 'var(--track-eyebrow)',
              textTransform: 'uppercase',
              color: 'var(--text-muted)',
            }}
          >
            before you spend
          </span>

          {pending.map((item) => (
            <EstimateRow key={item.id} item={item} model={batchModel} onCancel={dropPending} />
          ))}

          {/* One question for the whole batch. Every book here is summarized by the same
              model, so asking per file was asking the same thing three times. */}
          {priced.length > 0 && (
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: 10,
                marginTop: 4,
                padding: '14px 16px',
                borderRadius: 13,
                border: '1px solid var(--border-strong)',
              }}
            >
              <span style={{ font: `400 11px ${MONO}`, color: 'var(--text-muted)' }}>
                summarize {priced.length === 1 ? 'this book' : `all ${priced.length} books`} with
              </span>
              {(showAllModels ? modelOptions : modelOptions.slice(0, 3)).map((option) => (
                <ModelChoice
                  key={option.id}
                  option={option}
                  selected={option.id === batchModel}
                  onPick={setBatchModel}
                />
              ))}
              {modelOptions.length > 3 && (
                <QuietLink onClick={() => setShowAllModels((v) => !v)}>
                  {showAllModels ? 'Fewer models' : `All ${modelOptions.length} models`}
                </QuietLink>
              )}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 16,
                  marginTop: 2,
                }}
              >
                <span style={{ font: `400 11px ${MONO}`, color: 'var(--text-muted)' }}>
                  {priced.length} {priced.length === 1 ? 'book' : 'books'} · {batchParts} parts
                </span>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <Button size="sm" variant="secondary" onClick={() => setPending([])} disabled={startingAll}>
                    Cancel all
                  </Button>
                  <Button size="sm" onClick={startAll} disabled={startingAll || !batchModel}>
                    {startingAll ? 'Starting…' : `Summarize · ${money(batchCost)}`}
                  </Button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

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
            <JobRow
              key={job.id}
              job={job}
              onRemove={dropJob}
              onResume={continueJob}
              models={jobModels}
              proven={provenModels}
              palette={palette}
              day={day}
            />
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
        {covers && (
          <span style={{ font: "400 10.5px 'IBM Plex Mono', monospace", color: 'var(--text-muted)' }}>
            {coverLine(covers)}
          </span>
        )}
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {shown.slice(0, 60).map((book) => (
            <CollectionRow
              key={book.key}
              book={book}
              busy={busyKey === book.key}
              onMove={onMove}
              onDelete={onDelete}
              onEnrich={onEnrich}
              onContribute={onContribute}
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
        {/* Same reasoning as the shelf: the pipeline's folder names are how this is
            built, not something the screen needs to say. */}
        <span />
        <QuietLink onClick={onShelf}>Back to shelf</QuietLink>
      </div>
    </div>
  );
}
