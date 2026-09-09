import { useEffect, useMemo, useState } from 'react';

import AmbiencePlayer from '../components/AmbiencePlayer';
import Patch from '../components/Patch';
import Spinner from '../components/Spinner';
import { Button, ProgressBar, QuietLink } from '../components/ui';
import { useReducedMotion } from '../lib/prefs';
import {
  frontCount,
  highlightCount,
  newBudget,
  paginate,
  paletteFor,
  progressOf,
  tokensOf,
} from '../lib/reading';
import useSwipeNavigation from '../lib/useSwipeNavigation';

// Read one page of a part, then move on with one tap.

export default function Reader({ book, part, page, prefs, ambience, canFinish = true,
                                 finishing = false, onNavigate, onShelf, onFinish }) {
  const [soundOpen, setSoundOpen] = useState(false);

  const day = prefs.theme === 'day';
  // 8 is the design's ceiling on anchors per page, and stays the default. It is no
  // longer a hard limit, because the palette is now sampled rather than sliced and can
  // carry any number of stops.
  const cap = Math.min(16, Math.max(1, prefs.maxHighlights));

  const partCount = book.parts.length;
  const current = book.parts[part];
  const pages = useMemo(() => paginate(current?.body), [current]);
  const pageIndex = Math.min(page, Math.max(0, pages.length - 1));

  // The palette is cut to this page. Six highlights get six stops spanning the whole
  // ramp, so every page sweeps the full palette instead of stopping partway along it.
  const marks = useMemo(
    () => highlightCount(pages[pageIndex] || [], cap),
    [pages, pageIndex, cap],
  );
  const palette = useMemo(
    () => paletteFor(prefs.palette, day, marks || 1),
    [prefs.palette, day, marks],
  );

  // One budget per page, spent in reading order: the first distinct phrase takes band 1.
  const paras = useMemo(() => {
    const budget = newBudget();
    return (pages[pageIndex] || []).map((text) => tokensOf(text, palette, cap, budget));
  }, [pages, pageIndex, palette, cap]);

  const progress = progressOf(partCount, part, pageIndex, pages.length);
  const pct = `${Math.round(progress * 100)}%`;
  const lastPage = pageIndex + 1 >= pages.length;
  const lastPart = part + 1 >= partCount;

  const showResume =
    book.state === 'reading' && part === book.at && pageIndex === 0 && !!book.resumeRecap;

  // Duck while the resume strip is on screen; the page turn that leaves it restores
  // the level. The bed is background — it steps back when something asks to be read.
  const { duck } = ambience;
  useEffect(() => {
    duck(showResume);
  }, [duck, showResume]);

  // A guest reaches the end of a book and there is nothing to record — no finish, no
  // sittings, no Hardcover. The last page returns them to the shelf and says so, rather
  // than offering a button that fails.
  const nextLabel = !lastPage
    ? 'Next page'
    : lastPart
      ? canFinish
        ? 'Finish book'
        : 'Back to the shelf'
      : 'Next part';
  const backLabel = pageIndex > 0 ? 'Previous page' : part === 0 ? 'Back to shelf' : 'Previous part';

  const goNext = () => {
    if (!lastPage) return onNavigate(part, pageIndex + 1);
    if (lastPart) return canFinish ? onFinish() : onShelf();
    return onNavigate(part + 1, 0);
  };

  const goBack = () => {
    if (pageIndex > 0) return onNavigate(part, pageIndex - 1);
    if (part === 0) return onShelf();
    return onNavigate(part - 1, 0);
  };

  // Dragging the page turns it. The two moves that leave the reader entirely — finishing
  // the book, and falling off the front onto the shelf — are left to the controls: a
  // whole screen change should not arrive as a page turn.
  const reducedMotion = useReducedMotion();
  const canSwipeNext = !lastPage || !lastPart;
  const canSwipeBack = pageIndex > 0 || part > 0;
  const swipe = useSwipeNavigation({
    onNext: goNext,
    onPrevious: goBack,
    canNext: canSwipeNext,
    canPrevious: canSwipeBack,
    reduced: reducedMotion,
  });

  const pausedLabel =
    book.pausedDays == null
      ? 'you stopped here'
      : book.pausedDays === 0
        ? 'you stopped here · earlier today'
        : `you stopped here · ${book.pausedDays} day${book.pausedDays === 1 ? '' : 's'} ago`;

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        minHeight: 1112,
        boxSizing: 'border-box',
        padding: '36px 44px 32px',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 20,
        }}
      >
        <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
          <Patch patch={book.patch} size={34} />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <span
              style={{
                font: "600 10px 'IBM Plex Mono', monospace",
                letterSpacing: 'var(--track-eyebrow)',
                textTransform: 'uppercase',
                color: 'var(--text-muted)',
              }}
            >
              {pct} · part {part + 1} of {partCount}
            </span>
            <span
              style={{
                fontFamily: 'var(--font-display-wide)',
                fontSize: 17,
                fontWeight: 600,
                color: 'var(--text-primary)',
              }}
            >
              {book.title}
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
        </div>
        <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
          <QuietLink onClick={() => setSoundOpen((v) => !v)}>
            {ambience.on ? 'Sound on' : 'Sound'}
          </QuietLink>
          <QuietLink onClick={onShelf}>Shelf</QuietLink>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 7, marginTop: 26 }}>
        {/* The book's own palette, the one its highlights are drawn from. Eight stops
            rather than the page's count: this bar spans the whole book, so it shows the
            whole ramp regardless of how many phrases happen to be marked on this page. */}
        <ProgressBar pct={pct} gradient={paletteFor(prefs.palette, day, 8)} />
        <span
          style={{ font: "400 10.5px 'IBM Plex Mono', monospace", color: 'var(--text-muted)' }}
        >
          logistic · the introduction is not counted · 80% of the bar by part{' '}
          {frontCount(partCount)}
        </span>
      </div>

      <AmbiencePlayer ambience={ambience} open={soundOpen} onClose={() => setSoundOpen(false)} />

      {showResume && (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 9,
            marginTop: 24,
            padding: '16px 18px',
            borderRadius: 13,
            background: 'var(--bg-surface-hover)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
            {/* Gold is only ever a join — here, the join between two reading sessions. */}
            <div
              style={{
                width: 40,
                height: 2,
                borderRadius: 2,
                background:
                  'linear-gradient(90deg, var(--seam-600), var(--seam-100), var(--seam-500))',
              }}
            />
            <span
              style={{
                font: "600 9.5px 'IBM Plex Mono', monospace",
                letterSpacing: 'var(--track-eyebrow)',
                textTransform: 'uppercase',
                color: 'var(--seam-text)',
              }}
            >
              {pausedLabel}
            </span>
          </div>
          <p
            style={{
              margin: 0,
              maxWidth: '54ch',
              font: "400 13.5px/1.6 'Space Grotesk', system-ui",
              color: 'var(--text-secondary)',
            }}
          >
            {book.resumeRecap}
          </p>
        </div>
      )}

      {/* The swipe surface. Title and body travel together — a page turn moves the
          whole page, not its paragraphs. The clip lives on the wrapper so the leaving
          page disappears at the card's edge instead of over the chrome.
          It takes the slack below the text (flex: 1) so a short part is just as
          draggable as a full one — the empty space under three lines is still page. */}
      <div
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          marginLeft: -44,
          marginRight: -44,
          paddingInline: 44,
        }}
      >
        <div {...swipe.handlers} style={{ ...swipe.style, flex: 1 }}>
          <h2
            style={{
              margin: '26px 0 0',
              maxWidth: '32ch',
              fontFamily: 'var(--font-display-wide)',
              fontSize: 27,
              fontWeight: 600,
              lineHeight: 1.28,
              color: 'var(--text-primary)',
              textWrap: 'pretty',
            }}
          >
            {current?.title}
          </h2>

          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 24,
              marginTop: 22,
            }}
          >
            {paras.map((tokens, i) => (
              <p
                key={i}
                className="para"
                style={{
                  margin: 0,
                  maxWidth: '46ch',
                  fontFamily: "'Lexend Deca', 'Lexend', system-ui",
                  fontSize: 19.5,
                  lineHeight: 1.95,
                  letterSpacing: '.004em',
                  color: 'var(--text-primary)',
                  textWrap: 'pretty',
                }}
              >
                {/* No whitespace between the spans: a newline here renders as a space and
                    puts a gap before every comma. */}
                {tokens.map((tk, j) => (
                  <span key={j} style={{ color: tk.color, fontWeight: tk.weight }}>{tk.text}</span>
                ))}
              </p>
            ))}
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 13, marginTop: 'auto', paddingTop: 26 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
          {pages.map((_, i) => (
            <div
              key={i}
              style={{
                width: i === pageIndex ? 22 : 9,
                height: 5,
                borderRadius: 3,
                background: i <= pageIndex ? 'var(--accent)' : 'var(--border-strong)',
              }}
            />
          ))}
          <span
            style={{
              marginLeft: 6,
              font: "400 10.5px 'IBM Plex Mono', monospace",
              color: 'var(--text-muted)',
            }}
          >
            page {pageIndex + 1} of {pages.length} in this part · drag the page to turn it
          </span>
        </div>
        {/* The button turns the page the same way the drag does. The two used to differ
            — one slid, one swapped instantly — which made them feel like different apps.
            Where there is no page to slide to (finishing the book, falling off the front
            onto the shelf) the plain handler runs, because that is a screen change and
            should not be dressed as a page turn. */}
        {/* Finishing reaches Hardcover — a search, a status check and a write — so it
            can take the better part of a minute. The button says so and stops taking
            taps, because a second tap would mark the book read twice. The Spinner keeps
            its own 400ms threshold, so a finish that returns quickly shows nothing at
            all rather than a flash of "finishing". */}
        <Button
          size="lg"
          full
          disabled={finishing}
          onClick={canSwipeNext ? swipe.slideNext : goNext}
          style={{
            padding: '19px 22px',
            fontSize: 16,
            borderRadius: 13,
            minHeight: 62,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 12,
          }}
        >
          {finishing && <Spinner variant="mark" size={20} delay={0} />}
          {finishing ? 'Finishing — telling Hardcover…' : nextLabel}
        </Button>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 16,
          }}
        >
          <span
            style={{ font: "400 11.5px 'IBM Plex Mono', monospace", color: 'var(--text-muted)' }}
          >
            page {Math.round(progress * book.pages)} of {book.pages}
          </span>
          <QuietLink onClick={canSwipeBack ? swipe.slideBack : goBack}>{backLabel}</QuietLink>
        </div>
      </div>
    </div>
  );
}
