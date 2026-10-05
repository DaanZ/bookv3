import { useEffect, useState } from 'react';

import Patch from '../components/Patch';
import { Button, Chip, QuietLink } from '../components/ui';
import { finishQuest, getQuests, resyncHardcover, startQuest } from '../lib/api';

const QUEST_SIZES = [
  ['small', 'today'],
  ['medium', 'this week'],
  ['large', 'a project'],
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
function Quests({ quests, started, done, open, onOpen, onStart, starting, onDone, saving, saveError }) {
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
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 24 }}>
      <span style={EYEBROW}>three ways to use it · pick one to see the plan</span>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 12, alignItems: 'stretch' }}>
          {QUEST_SIZES.map(([size, when]) => {
            const quest = quests[size];
            const chosen = size === open;
            const state = done[size] ? ['current', 'done'] : started[size] ? ['claimed', 'started'] : ['neutral', size];
            return (
              <button
                key={size}
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
                }}
              >
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Chip tone={state[0]}>{state[1]}</Chip>
                  <span style={{ font: "400 11px 'IBM Plex Mono', monospace", color: 'var(--text-muted)' }}>
                    {[when, duration(quest.minutes)].filter(Boolean).join(' · ')}
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
  onShelf,
  onReset,
}) {
  // The result of the call just made, or the outcome recorded when it was finished
  // before. undefined/null means neither exists — say that, do not guess.
  // A re-sync supersedes both: it is the most recent thing Hardcover said.
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
  useEffect(() => {
    let live = true;
    setOpen(null);
    getQuests(book.key)
      .then((answer) => {
        if (!live) return;
        setQuests(answer?.quests || null);
        setStarted(answer?.started || {});
        setDone(answer?.done || {});
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [book.key]);

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
                as far from {book.category} as your shelf goes
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
