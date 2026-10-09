import { useEffect, useRef, useState } from 'react';

import Patch from '../components/Patch';
import IntelligencePill from '../components/IntelligencePill';
import SpiralPill from '../components/SpiralPill';
import { Button, Chip, QuietLink, Sheet } from '../components/ui';
import { useNarrow } from '../lib/prefs';
import { finishQuest, getQuests, rerollQuests, resyncHardcover, startQuest } from '../lib/api';

// When each quest is for. Stored as small, medium and large, shown as the moment: a goal
// is concrete when it says when.
const QUEST_SIZES = [
  ['small', 'next break'],
  ['medium', 'tonight'],
  ['large', 'this weekend'],
];

/** "15 min", "1½ h", "5 h": an estimate, said the way a person would. */
function duration(minutes) {
  if (!minutes) return null;
  if (minutes < 60) return `${minutes} min`;
  const hours = minutes / 60;
  return `${Number.isInteger(hours) ? hours : (Math.round(hours * 2) / 2).toString().replace('.5', '½')} h`;
}

/** 1st, 2nd, 3rd, 4th — English ordinals, including the teens that break the rule. */
function ordinal(n) {
  const tens = n % 100;
  if (tens >= 11 && tens <= 13) return `${n}th`;
  return `${n}${['th', 'st', 'nd', 'rd'][n % 10] || 'th'}`;
}

const EYEBROW = {
  font: "600 9.5px 'IBM Plex Mono', monospace",
  letterSpacing: 'var(--track-eyebrow)',
  textTransform: 'uppercase',
  color: 'var(--text-muted)',
};

// The three questions after a quest, in order: what you did, what went wrong, and why
// the book asks for it this way. Doing it and learning from the mistakes is where the
// reading turns into knowing, so the mistakes and the why are asked for, not optional.
const QUESTIONS = [
  ['happened', 'What did you do, and what happened?', 'Say what you actually did, not what the plan said.', 'what happened'],
  ['wentWrong', 'What went wrong, or not as planned?', 'The mistakes are the useful part. “Nothing” is rarely true.', 'what went wrong'],
  ['why', 'Why do you think the book asks for it this way?', 'What is each step for? What would you change next time?', 'why it asks this'],
];

// The lead quest's colours: the accent, with its own ink for every text and chip on it.
const LEAD = {
  background: 'var(--accent)',
  borderColor: 'var(--accent)',
  '--text-primary': 'var(--accent-on)',
  '--text-secondary': 'var(--accent-on)',
  '--text-muted': 'var(--accent-on)',
  '--chip-neutral-bg': 'rgba(20,32,31,.16)',
  '--chip-neutral-fg': 'var(--accent-on)',
};

/** "3 October": the day, said plainly. */
function day(iso) {
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'long' });
}

const ANSWER_TEXT = {
  fontFamily: "'Lexend Deca', 'Lexend', system-ui",
  fontSize: 14,
  lineHeight: 1.55,
  color: 'var(--text-primary)',
};

/** The three questions, inside the plan, where its footer was. */
function ReflectionForm({ initial, onSave, onCancel, saving, error }) {
  const [answers, setAnswers] = useState(() =>
    Object.fromEntries(QUESTIONS.map(([field]) => [field, initial?.[field] || ''])),
  );
  const complete = QUESTIONS.every(([field]) => answers[field].trim());

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (complete && !saving) onSave(answers);
      }}
      style={{ display: 'flex', flexDirection: 'column', gap: 16, paddingTop: 14, borderTop: '1px solid var(--border-subtle)' }}
    >
      {QUESTIONS.map(([field, question, hint], i) => (
        <label key={field} style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
          <span style={{ font: "500 14px 'Space Grotesk', system-ui", lineHeight: 1.4 }}>{question}</span>
          <textarea
            autoFocus={i === 0}
            rows={3}
            value={answers[field]}
            placeholder={hint}
            maxLength={2000}
            onChange={(event) => setAnswers((a) => ({ ...a, [field]: event.target.value }))}
            style={{
              ...ANSWER_TEXT,
              boxSizing: 'border-box',
              width: '100%',
              minHeight: 76,
              padding: '10px 12px',
              borderRadius: 'var(--radius-input)',
              border: '1px solid var(--border-strong)',
              background: 'transparent',
              resize: 'vertical',
              outline: 'none',
            }}
          />
        </label>
      ))}
      {error && (
        <span style={{ font: "400 12px 'Space Grotesk', system-ui", color: 'var(--chip-expired-fg)' }}>{error}</span>
      )}
      <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
        <Button size="lg" type="submit" disabled={!complete || saving} style={{ minHeight: 48 }}>
          {saving ? 'Saving…' : 'Save'}
        </Button>
        <QuietLink onClick={onCancel}>Cancel</QuietLink>
      </div>
    </form>
  );
}

/** A done quest's reflection, read back. */
function Reflection({ answers }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, paddingTop: 14, borderTop: '1px solid var(--border-subtle)' }}>
      {QUESTIONS.map(([field, , , label]) => (
        <div key={field} style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          <span style={EYEBROW}>{label}</span>
          <span style={{ ...ANSWER_TEXT, whiteSpace: 'pre-wrap' }}>{answers[field]}</span>
        </div>
      ))}
    </div>
  );
}

/** Two arrows chasing round: "make these again". Drawn, not an emoji, so it takes the ink. */
function RefreshIcon({ turning }) {
  return (
    <svg
      className={turning ? 'quest-turning' : undefined}
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M20 11a8 8 0 0 0-14.3-4.9L4 8" />
      <path d="M4 3v5h5" />
      <path d="M4 13a8 8 0 0 0 14.3 4.9L20 16" />
      <path d="M20 21v-5h-5" />
    </svg>
  );
}

// Measured on the running reader, October 2026, eight runs: 10, 13, 13, 13, 25, 28, 30
// and 64 seconds. The spread is retries: a set that fails a check is asked for again, up
// to three times, and a direction ("indoor plants") makes the checks fail more often.
const REROLL_ESTIMATE = 'usually 15 to 60 seconds';

/**
 * Asking for new quests, and how that is going. The owner's alone: it spends API credit
 * and changes the set every reader is offered. Started and finished quests are kept by
 * the server, and the ones replaced are remembered as passed on, so they do not return.
 *
 * An icon rather than a sentence; the sentence is its tooltip and accessible name, and
 * `withLabel` shows it as well where the button would otherwise be unexplained.
 */
function RerollButton({ status, error, label, onReroll, withLabel = false }) {
  const running = status?.state === 'running';
  // Asking which way the new quests should lean, before anything is spent.
  const [asking, setAsking] = useState(false);
  const [direction, setDirection] = useState('');
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return undefined;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [running]);

  const quiet = { font: "400 12px 'Space Grotesk', system-ui", color: 'var(--text-muted)' };
  const icon = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    minWidth: 34,
    height: 34,
    padding: withLabel ? '0 12px' : 0,
    borderRadius: 17,
    border: '1px solid var(--border-default)',
    background: 'transparent',
    color: 'var(--text-secondary)',
    font: "500 12.5px 'Space Grotesk', system-ui",
    cursor: running ? 'default' : 'pointer',
  };

  if (running) {
    const seconds = status.startedAt ? Math.max(0, Math.round((now - Date.parse(status.startedAt)) / 1000)) : 0;
    return (
      <span style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
        <span style={quiet}>
          new quests · {seconds} s · {seconds > 30 ? 'a set failed a check, asking again' : REROLL_ESTIMATE}
        </span>
        <span style={icon} aria-hidden="true">
          <RefreshIcon turning />
        </span>
      </span>
    );
  }
  if (asking) {
    const go = () => {
      setAsking(false);
      onReroll(direction);
    };
    return (
      <form
        onSubmit={(event) => {
          event.preventDefault();
          go();
        }}
        style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}
      >
        <input
          autoFocus
          value={direction}
          maxLength={120}
          placeholder="Which way? (optional) e.g. indoor plants"
          aria-label="Which way should the new quests lean? Optional."
          onChange={(event) => setDirection(event.target.value)}
          onKeyDown={(event) => event.key === 'Escape' && setAsking(false)}
          style={{
            width: 260,
            padding: '8px 12px',
            borderRadius: 'var(--radius-input)',
            border: '1px solid var(--border-strong)',
            background: 'transparent',
            color: 'var(--text-primary)',
            font: "400 13px 'Space Grotesk', system-ui",
            outline: 'none',
          }}
        />
        <Button size="sm" type="submit">
          New quests
        </Button>
        <QuietLink onClick={() => setAsking(false)}>Cancel</QuietLink>
      </form>
    );
  }

  const failed = error || (status?.state === 'failed' ? status.error : null);
  return (
    <span style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
      {failed && <span style={{ ...quiet, color: 'var(--chip-expired-fg)' }}>{failed}</span>}
      <button
        type="button"
        className="row"
        onClick={() => setAsking(true)}
        title={failed ? 'Try again' : `${label} · ${REROLL_ESTIMATE}`}
        aria-label={failed ? 'Try again' : label}
        style={icon}
      >
        <RefreshIcon />
        {withLabel && <span>{failed ? 'Try again' : label}</span>}
      </button>
    </span>
  );
}

/**
 * Three quests in a row; the one picked opens into its plan beneath it.
 *
 * The open card and its plan are one container, like a tab and its page (the design on
 * the Quests canvas): the card drops its bottom edge and overlaps the plan's top border
 * by a pixel, the plan's corner under it goes square, and the other two cards lift away.
 * So the plan does not repeat the card's title: it starts where the card ends.
 *
 * A quest moves through start → "I did it" → a reflection, all inside the plan. The way
 * back to it days later is the book itself: the shelf marks a read book with a quest
 * still open, and opening a read book lands here.
 */
function Quests({ quests, started, done, open, onOpen, onStart, starting, onDone, saving, saveError, action, fresh, replacing }) {
  const [writing, setWriting] = useState(false);
  useEffect(() => setWriting(false), [open]);

  const index = QUEST_SIZES.findIndex(([size]) => size === open);
  const active = open ? quests[open] : null;
  const reflection = open ? done[open] : null;
  const planRadius = ['0 14px 14px 14px', '14px', '14px 0 14px 14px'][index] || '14px';

  const save = async (answers) => {
    if (await onDone(open, answers)) setWriting(false);
  };
  const undoDone = () => {
    if (window.confirm('Remove this reflection? What you wrote is not kept.')) onDone(open, null);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 18 }}>
      <div style={{ display: 'flex', gap: 12, alignItems: 'baseline', justifyContent: 'space-between', flexWrap: 'wrap' }}>
        <span style={EYEBROW}>try it · in your next break, tonight or this weekend</span>
        {action}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 12, alignItems: 'stretch' }}>
          {QUEST_SIZES.map(([size, when]) => {
            const quest = quests[size];
            const chosen = size === open;
            // The chip says the moment, until the quest is started or done; then it says that,
            // and the moment moves to the line beside it.
            const taken = done[size] ? ['current', 'done'] : started[size] ? ['claimed', 'started'] : null;
            // Just replaced by a reroll: marked "new" until the next one or another book.
            const isNew = fresh.has(size) && !taken;
            // Being replaced right now: faded, so it is clear which cards are about to change.
            const going = replacing && !taken;
            // The next-break quest is the screen's one next action while nobody has taken it
            // up: it wears the accent, the 10 of the 60-30-10 split.
            const lead = size === 'small' && !taken && !chosen;
            return (
              <button
                // Keyed on the title so a replaced card mounts afresh and fades in.
                key={`${size}:${quest.title}`}
                className={isNew ? 'quest-new' : undefined}
                type="button"
                aria-expanded={chosen}
                onClick={() => onOpen(chosen ? null : size)}
                style={{
                  boxSizing: 'border-box',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 8,
                  textAlign: 'left',
                  padding: '16px 16px 18px',
                  font: 'inherit',
                  color: 'var(--text-primary)',
                  cursor: 'pointer',
                  background: 'var(--bg-surface)',
                  border: `1px solid ${chosen ? 'var(--accent)' : 'var(--border-default)'}`,
                  borderBottom: `1px solid ${chosen ? 'var(--bg-surface)' : 'var(--border-default)'}`,
                  borderRadius: chosen ? '14px 14px 0 0' : 14,
                  marginBottom: chosen ? -1 : open ? 12 : 0,
                  position: 'relative',
                  zIndex: chosen ? 1 : 0,
                  opacity: going ? 0.4 : 1,
                  transition: 'opacity var(--dur-instant, 90ms) var(--ease-move, ease)',
                  ...(lead ? LEAD : null),
                }}
              >
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  {isNew ? (
                    <Chip style={lead ? { background: 'var(--accent-on)', color: 'var(--accent)' } : { background: 'var(--accent)', color: 'var(--accent-on)' }}>new</Chip>
                  ) : taken ? (
                    <Chip tone={taken[0]}>{taken[1]}</Chip>
                  ) : (
                    <Chip tone="neutral">{when}</Chip>
                  )}
                  <span style={{ font: "400 11px 'IBM Plex Mono', monospace", color: 'var(--text-muted)' }}>
                    {[taken || isNew ? when : null, duration(quest.minutes)].filter(Boolean).join(' · ')}
                  </span>
                </span>
                <span style={{ fontFamily: 'var(--font-display-wide)', fontSize: 15.5, fontWeight: 600, lineHeight: 1.3 }}>
                  {quest.title}
                </span>
                <span style={{ font: "400 13px 'Space Grotesk', system-ui", lineHeight: 1.5, color: 'var(--text-secondary)' }}>
                  {quest.short}
                </span>
              </button>
            );
          })}
        </div>

        {active && (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 14,
              padding: '18px 22px 20px',
              border: '1px solid var(--accent)',
              borderRadius: planRadius,
              background: 'var(--bg-surface)',
            }}
          >
            <span style={{ font: "400 12.5px 'Space Grotesk', system-ui", color: 'var(--text-muted)' }}>
              From the book: {active.source}
              {active.direction && ` · your direction: ${active.direction}`}
            </span>
            {active.needs.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <span style={EYEBROW}>what you need</span>
                <span style={{ font: "400 13.5px 'Space Grotesk', system-ui", lineHeight: 1.55, color: 'var(--text-secondary)' }}>
                  {active.needs.join(' · ')}
                </span>
              </div>
            )}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <span style={EYEBROW}>the plan</span>
              <ol style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 8 }}>
                {active.steps.map((step, i) => (
                  <li
                    key={i}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '24px minmax(0, 1fr)',
                      gap: 10,
                      alignItems: 'baseline',
                      fontFamily: "'Lexend Deca', 'Lexend', system-ui",
                      fontSize: 14,
                      lineHeight: 1.55,
                    }}
                  >
                    <span style={{ font: "600 11px 'IBM Plex Mono', monospace", color: 'var(--accent)' }}>
                      {String(i + 1).padStart(2, '0')}
                    </span>
                    <span>{step}</span>
                  </li>
                ))}
              </ol>
            </div>
            <div style={{ display: 'flex', gap: 10, alignItems: 'baseline', paddingTop: 12, borderTop: '1px solid var(--border-subtle)' }}>
              <span style={{ ...EYEBROW, flex: 'none' }}>done when</span>
              <span style={{ font: "500 13.5px 'Space Grotesk', system-ui", lineHeight: 1.5 }}>{active.doneWhen}</span>
            </div>

            {writing ? (
              <ReflectionForm
                initial={reflection}
                onSave={save}
                onCancel={() => setWriting(false)}
                saving={saving}
                error={saveError}
              />
            ) : (
              <>
                {reflection && <Reflection answers={reflection} />}
                <div style={{ display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap' }}>
                  {reflection ? (
                    <>
                      <Chip tone="current">done</Chip>
                      <span style={{ font: "400 12.5px 'Space Grotesk', system-ui", color: 'var(--text-secondary)' }}>
                        on {day(reflection.doneAt)}
                      </span>
                      <QuietLink onClick={() => setWriting(true)}>Edit</QuietLink>
                      <QuietLink onClick={saving ? undefined : undoDone}>Undo</QuietLink>
                    </>
                  ) : started[open] ? (
                    <>
                      <Button size="lg" onClick={() => setWriting(true)} style={{ minHeight: 48 }}>
                        I did it
                      </Button>
                      <span style={{ font: "400 12.5px 'Space Grotesk', system-ui", color: 'var(--text-secondary)' }}>
                        started {day(started[open])}
                      </span>
                      <QuietLink onClick={starting ? undefined : () => onStart(open)}>
                        {starting ? 'undoing…' : 'Undo start'}
                      </QuietLink>
                    </>
                  ) : (
                    <Button size="lg" onClick={starting ? undefined : () => onStart(open)} style={{ minHeight: 48 }}>
                      {starting ? 'Starting…' : 'Start this quest'}
                    </Button>
                  )}
                  <span style={{ flexGrow: 1 }} />
                  <QuietLink onClick={() => onOpen(null)}>Close</QuietLink>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
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
  similar = [],
  onOpenBook,
  onShelf,
  onReset,
}) {
  // The result of the call just made, or the outcome recorded when it was finished
  // before. undefined/null means neither exists — say that, do not guess.
  // A re-sync supersedes both: it is the most recent thing Hardcover said.
  const narrow = useNarrow();
  const [resync, setResync] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const [resetting, setResetting] = useState(false);

  // Three quests made from this book's summary by quests.py, or null when none were made
  // yet. Never waited on: the screen renders without them and they arrive after.
  const [quests, setQuests] = useState(null);
  // Which ones this reader started, {size: startedAt}: the hand-off to a daily quest list.
  const [started, setStarted] = useState({});
  // The card that is open. One at a time, and none until the reader picks one.
  const [open, setOpen] = useState(null);
  const [starting, setStarting] = useState(false);
  // The ones they did, {size: {doneAt, happened, wentWrong, why}}: what they made of it.
  const [done, setDone] = useState({});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);
  // New quests being made for this book, {state: 'running' | 'failed', error?}, or null.
  const [reroll, setReroll] = useState(null);
  const [rerollError, setRerollError] = useState(null);
  // Sizes a reroll just replaced, so their cards can say so.
  const [fresh, setFresh] = useState(() => new Set());
  // The titles as they were when a reroll began; compared with the set that lands.
  const before = useRef(null);

  const apply = (answer) => {
    const next = answer?.quests || null;
    if (before.current && !answer?.reroll) {
      setFresh(new Set(QUEST_SIZES.map(([size]) => size).filter((size) => next?.[size]?.title !== before.current[size])));
      before.current = null;
    }
    setQuests(next);
    setStarted(answer?.started || {});
    setDone(answer?.done || {});
    setReroll(answer?.reroll || null);
  };

  useEffect(() => {
    let live = true;
    setOpen(null);
    setRerollError(null);
    setFresh(new Set());
    before.current = null;
    getQuests(book.key)
      .then((answer) => live && apply(answer))
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [book.key]);

  // While new quests are being made, ask every few seconds; the new set replaces the old
  // in place when it lands, and an open card shows its new quest.
  useEffect(() => {
    if (reroll?.state !== 'running') return undefined;
    let live = true;
    const timer = setInterval(() => {
      getQuests(book.key)
        .then((answer) => live && apply(answer))
        .catch(() => {});
    }, 3000);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [reroll?.state, book.key]);

  const startReroll = async (direction = '') => {
    setRerollError(null);
    setFresh(new Set());
    before.current = Object.fromEntries(QUEST_SIZES.map(([size]) => [size, quests?.[size]?.title ?? null]));
    try {
      const answer = await rerollQuests(book.key, direction);
      setReroll(answer?.reroll || null);
    } catch (ex) {
      before.current = null;
      setRerollError(ex.message);
    }
  };

  const toggleStart = async (size) => {
    setStarting(true);
    try {
      const answer = await startQuest(book.key, size, !started[size]);
      setStarted(answer?.started || {});
    } finally {
      setStarting(false);
    }
  };

  // Save a reflection (or remove it, with null). True when it was saved, so the form
  // closes only on success and keeps what was typed when the request failed.
  const recordDone = async (size, reflection) => {
    setSaving(true);
    setSaveError(null);
    try {
      const answer = await finishQuest(book.key, size, reflection);
      setDone(answer?.done || {});
      return true;
    } catch (ex) {
      setSaveError(ex.message);
      return false;
    } finally {
      setSaving(false);
    }
  };

  const reset = async () => {
    setResetting(true);
    try {
      await onReset();
    } finally {
      setResetting(false);
    }
  };

  const latest = resync ?? result;
  const marked = latest ? latest.markedRead : book.markedRead;
  const number = latest?.finishNumber ?? book.finishNumber;

  // Hardcover is one account, reached with one key, and it is the owner's. Another
  // reader's finish is real and recorded — it is simply theirs and not a write to
  // somebody else's public shelf, and this block says which rather than showing a chip
  // about a call that was never made on their behalf.
  // Named for what it is: not the owner. There is no guest any more, and this was
  // never about one — it is about whose Hardcover account the key opens.
  const notOwner = who ? !who.owner : false;

  // Sizes this reader has taken up; the server also keeps any another reader took up.
  const taken = QUEST_SIZES.filter(([size]) => started[size] || done[size]).length;
  const rerollAction =
    who?.owner && taken < QUEST_SIZES.length ? (
      <RerollButton
        status={reroll}
        error={rerollError}
        label={taken ? 'New quests for the ones not started' : 'New quests'}
        onReroll={startReroll}
      />
    ) : null;

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

  // "read in 1 sitting over 0 days" is what this printed for a book read in one day.
  // A single day is not a span, so it is left out; one sitting is said as a word.
  const sittingsText = book.sittings === 1 ? 'one sitting' : `${book.sittings} sittings`;
  const sittings = !book.sittings
    ? ''
    : book.days >= 2
      ? ` · read in ${sittingsText} over ${book.days} days`
      : ` · read in ${sittingsText}`;

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        minHeight: 1112,
        boxSizing: 'border-box',
        padding: '32px 44px 22px',
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
          fontSize: 34,
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
      {(book.spiral || book.intelligence) && (
        <div style={{ marginTop: 10, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <SpiralPill spiral={book.spiral} />
          <IntelligencePill intelligence={book.intelligence} />
        </div>
      )}

      {/* The sheet: everything to do with the book from here on — its Hardcover entry, the
          quests and the next book — on the graphite page inside the indigo frame. */}
      <Sheet grow style={{ marginTop: 24 }}>
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 11,
          marginTop: 18,
          padding: '18px 20px',
          borderRadius: 13,
          background: 'var(--bg-surface-hover)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {notOwner ? (
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
        {!notOwner && marked === true && latest?.titleOnlyMatch && latest?.hardcoverTitle && (
          <span style={{ font: "400 11.5px 'IBM Plex Mono', monospace", color: 'var(--text-muted)' }}>
            matched on title only → “{latest.hardcoverTitle}”
          </span>
        )}
      </div>

      {/* The book's last word: three things to do with it, from a few minutes to a
          project. They take the place of the part list, which only recaps; a book with
          no quests yet keeps the list. */}
      {quests ? (
        <Quests
          action={rerollAction}
          fresh={fresh}
          replacing={reroll?.state === 'running'}
          quests={quests}
          started={started}
          done={done}
          open={open}
          onOpen={setOpen}
          onStart={toggleStart}
          starting={starting}
          onDone={recordDone}
          saving={saving}
          saveError={saveError}
        />
      ) : (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 18 }}>
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
        {who?.owner && (
          <RerollButton status={reroll} error={rerollError} label="Make three quests from this book" onReroll={startReroll} withLabel />
        )}
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
      )}

      {/* The other way on from a book: stay with the subject. Up to three unread books
          whose summaries are nearest this one's (api/similar.py); the row below stays
          the way out to something else entirely. So the screen ends in a choice: do
          something with this book, read another like it, or switch. */}
      {similar.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 22 }}>
          <span
            style={{
              font: "600 9.5px 'IBM Plex Mono', monospace",
              letterSpacing: 'var(--track-eyebrow)',
              textTransform: 'uppercase',
              color: 'var(--text-muted)',
            }}
          >
            more like this · read one part
          </span>
          <div style={{ display: 'grid', gridTemplateColumns: narrow ? 'minmax(0, 1fr)' : `repeat(${similar.length}, minmax(0, 1fr))`, gap: 10 }}>
            {similar.map((other) => (
              <button
                key={other.key}
                type="button"
                className="tap row"
                onClick={() => onOpenBook(other.key)}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'flex-start',
                  gap: 10,
                  minHeight: 44,
                  padding: '14px 16px',
                  borderRadius: 12,
                  textAlign: 'left',
                  border: '1px solid var(--border-default)',
                  background: 'var(--bg-surface-hover)',
                }}
              >
                {/* Wraps: a transition's pill with its place runs wider than a narrow card. */}
                <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8, width: '100%' }}>
                  <Patch patch={other.patch} size={28} />
                  <SpiralPill spiral={other.spiral} />
                </span>
                <span
                  style={{
                    fontFamily: 'var(--font-display-wide)',
                    fontSize: 14,
                    fontWeight: 600,
                    lineHeight: 1.3,
                    color: 'var(--text-primary)',
                  }}
                >
                  {other.title}
                </span>
                <span style={{ font: "400 11.5px 'Space Grotesk', system-ui", color: 'var(--text-secondary)' }}>
                  {other.author} · {other.partCount} parts
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* One slim row, so the quests above have the room: the open plan and this used
          to push the screen past the tablet's height. Same two actions as before. */}
      {recommendation && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 16,
            marginTop: 20,
            padding: '16px 20px',
            borderRadius: 14,
            border: '1px solid var(--border-default)',
            background: 'var(--bg-surface)',
          }}
        >
          <div style={{ display: 'flex', gap: 14, alignItems: 'center', minWidth: 0 }}>
            <Patch patch={recommendation.patch} size={34} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0 }}>
              <span
                style={{
                  font: "600 9.5px 'IBM Plex Mono', monospace",
                  letterSpacing: 'var(--track-eyebrow)',
                  textTransform: 'uppercase',
                  color: 'var(--text-muted)',
                }}
              >
                {similar.length ? 'or something else entirely' : `as far from ${book.category} as your shelf goes`}
              </span>
              <span
                style={{
                  fontFamily: 'var(--font-display-wide)',
                  fontSize: 16,
                  fontWeight: 600,
                  lineHeight: 1.3,
                  color: 'var(--text-primary)',
                }}
              >
                {recommendation.subtitle
                  ? `${recommendation.title}: ${recommendation.subtitle}`
                  : recommendation.title}
              </span>
              <span style={{ font: "400 12px 'Space Grotesk', system-ui", color: 'var(--text-secondary)' }}>
                {recommendation.author} · {recommendation.partCount} parts
              </span>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 16, alignItems: 'center', flex: 'none' }}>
            <QuietLink onClick={onNextRec}>Show another</QuietLink>
            <Button variant="secondary" onClick={onOpenRec} style={{ minHeight: 44 }}>
              Read one part
            </Button>
          </div>
        </div>
      )}
      </Sheet>

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 16,
          marginTop: 14,
          paddingTop: 16,
        }}
      >
        <span style={{ font: "400 11.5px 'IBM Plex Mono', monospace", color: 'var(--text-muted)' }}>
          {counts.total} books · {counts.read} read
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
          {/* A finish can be a mistake — the wrong row tapped, or a book marked read
              from the library that was never actually read. Undoing it is the reader's
              own record, so it sits here rather than only in the library, and it is a
              quiet link rather than a button: it is the rare correction, not the way
              out of this screen. Hardcover keeps whatever it was told; retracting a
              public shelf entry is done on Hardcover. */}
          {onReset && (
            <QuietLink onClick={resetting ? undefined : reset}>
              {resetting ? 'Putting it back…' : 'I have not finished this'}
            </QuietLink>
          )}
          <QuietLink onClick={onShelf}>Back to shelf</QuietLink>
        </div>
      </div>
    </div>
  );
}
