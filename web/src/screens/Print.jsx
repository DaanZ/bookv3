import { useEffect, useMemo, useState } from 'react';

import { getBook } from '../lib/api';
import {
  MAX_PAGES_PER_PART,
  PALETTE_NAMES,
  highlightCount,
  newBudget,
  paginate,
  paletteFor,
  tokensOf,
} from '../lib/reading';

// One book laid out for paper, so a summary can be handed to somebody who does not have
// the app — printed, or saved as a PDF from the browser's own print dialog.
//
// Open it at `/#print/<book key>`. It is a hash rather than a screen inside the app for
// the same reason the bench is: the reader gains no route to wander into, and the URL is
// a thing you can send somebody.
//
// **Print is not the screen with a white background.** Four things change, and each one
// is a decision rather than a default:
//
// * **The day register, always; the reader's own palette.** Which of the five palettes
//   is a choice and is honoured, so a printout looks like the book they read. Which
//   *register* is not: the night stops are built to sit on deep water and come out
//   washed and pale on white, so `paletteFor(name, true, n)` regardless of what the
//   tablet was set to. Paper is paper.
// * **The marks keep their weight.** Colour is the first thing a black-and-white printer
//   throws away, and a photocopy of this should still show what mattered. 600 survives;
//   a colour alone does not.
// * **The screen's pagination is kept as the unit of highlighting, not as pages.** The
//   reader's budget is eight marks per screen page, so the eye never holds more than
//   eight anchors at once. On paper those blocks simply run together into flowing prose,
//   but each keeps its own budget and its own sweep of the palette — which means the PDF
//   marks the same phrases the reader saw, rather than inventing a second scheme.
// * **Nothing is interactive.** No ambience, no position, no finish. This view reads the
//   book and writes nothing: sending somebody a PDF should not move your bookmark.

// A little over what the reader uses per page, because an A4 page holds two or three of
// those blocks and a cap that is right for a tablet reads sparse in print.
const MARKS_PER_BLOCK = 8;

/** Which palette this browser last read in. Falls back to the app's own default. */
function readerPalette() {
  try {
    const stored = JSON.parse(localStorage.getItem('bookv3.prefs') || '{}');
    return PALETTE_NAMES.includes(stored?.palette) ? stored.palette : 'sunset';
  } catch {
    return 'sunset';
  }
}

function Block({ paragraphs, palette }) {
  // One budget per block, exactly as the reader builds one per page.
  const budget = newBudget();
  return (
    <>
      {paragraphs.map((text, i) => (
        <p
          key={i}
          style={{
            margin: '0 0 0.62em',
            font: "400 10.5pt/1.62 'Lexend', Georgia, serif",
            textAlign: 'justify',
            hyphens: 'auto',
            orphans: 2,
            widows: 2,
          }}
        >
          {tokensOf(text, palette, MARKS_PER_BLOCK, budget).map((token, j) => (
            <span key={j} style={{ color: token.color, fontWeight: token.weight }}>
              {token.text}
            </span>
          ))}
        </p>
      ))}
    </>
  );
}

function Part({ part, index, total, palette }) {
  const blocks = useMemo(() => paginate(part.body), [part.body]);
  return (
    <section style={{ breakInside: 'auto', marginTop: index === 0 ? 0 : '1.6em' }}>
      <h2
        style={{
          // `break-after: avoid` keeps a heading with the paragraph it introduces. A
          // title alone at the foot of a page is the commonest way printed text looks
          // careless, and it is one line of CSS to prevent.
          breakAfter: 'avoid',
          breakInside: 'avoid',
          margin: '0 0 0.55em',
          font: "600 13pt/1.3 'Space Grotesk', system-ui, sans-serif",
          color: '#14201F',
        }}
      >
        <span style={{ color: '#8A6512', marginRight: '0.6em', fontVariantNumeric: 'tabular-nums' }}>
          {String(index + 1).padStart(2, '0')}
        </span>
        {part.title}
        <span
          style={{ float: 'right', font: "400 8.5pt 'IBM Plex Mono', monospace", color: '#7D8A84' }}
        >
          {index + 1}/{total}
        </span>
      </h2>
      {blocks.map((paragraphs, i) => (
        <Block key={i} paragraphs={paragraphs} palette={palette} />
      ))}
    </section>
  );
}

export default function Print({ bookKey }) {
  const [book, setBook] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getBook(bookKey)
      .then((data) => !cancelled && setBook(data))
      .catch((ex) => !cancelled && setError(ex.message));
    return () => {
      cancelled = true;
    };
  }, [bookKey]);

  // The palette the marks take, in the reader's own choice rather than a fixed one: a
  // printout should look like the book they read. Taken from the cached preference
  // rather than the profile, because this view deliberately makes no authenticated call
  // beyond fetching the book — and `true` for the register regardless, because the
  // choice on offer is a palette, not whether paper is white.
  //
  // Built to the largest budget any block will spend, so a block that marks fewer
  // phrases simply uses the first stops: the same sweep, shorter.
  const palette = useMemo(() => paletteFor(readerPalette(), true, MARKS_PER_BLOCK), []);

  useEffect(() => {
    document.title = book ? `${book.title} — Snippers` : 'Snippers';
  }, [book]);

  if (error) {
    return <div style={{ padding: 40, font: "400 14px 'Space Grotesk', system-ui" }}>{error}</div>;
  }
  if (!book) {
    return <div style={{ padding: 40, font: "400 14px 'Space Grotesk', system-ui" }}>Laying out…</div>;
  }

  const marks = book.parts.reduce(
    (sum, part) => sum + paginate(part.body).reduce((n, block) => n + highlightCount(block, MARKS_PER_BLOCK), 0),
    0,
  );

  return (
    <>
      <style>{`
        @page { size: A4; margin: 20mm 18mm 18mm; }

        /* The browser's print dialog draws its own header and footer, including page
           numbers, so this does not try to. Fighting it produces two of everything. */
        @media print {
          .no-print { display: none !important; }
          html, body { background: #FFFFFF !important; }
        }

        /* On screen this is a preview of the sheet, so it is shown as one: a white page
           on a grey desk, at the width it will actually print. */
        @media screen {
          body { background: #E6E2DA !important; }
          .sheet {
            width: 174mm;
            margin: 24px auto;
            padding: 20mm 18mm;
            background: #FFFFFF;
            box-shadow: 0 2px 18px rgba(0,0,0,.14);
          }
        }

        .sheet { color: #14201F; }
        .sheet a { color: #8A6512; text-decoration: none; }
      `}</style>

      <div
        className="no-print"
        style={{
          position: 'sticky',
          top: 0,
          display: 'flex',
          alignItems: 'center',
          gap: 14,
          padding: '12px 18px',
          background: '#14201F',
          color: '#FDF6EA',
          font: "400 12px 'IBM Plex Mono', monospace",
        }}
      >
        <strong style={{ font: "500 13px 'Space Grotesk', system-ui" }}>Print preview</strong>
        <span style={{ opacity: 0.7 }}>
          {book.parts.length} parts · {marks} marks · {readerPalette()} on paper
        </span>
        <button
          type="button"
          onClick={() => window.print()}
          style={{
            marginLeft: 'auto',
            padding: '7px 14px',
            borderRadius: 9,
            border: 0,
            cursor: 'pointer',
            background: '#EF8A1E',
            color: '#14201F',
            font: "500 12px 'Space Grotesk', system-ui",
          }}
        >
          Print / Save as PDF
        </button>
      </div>

      <article className="sheet">
        {/* Front matter. It says what this is before the first paragraph, because a
            summary handed to somebody with no context reads as a very short book, and
            the person who wrote the real one deserves the top of the page. */}
        <header style={{ breakAfter: 'avoid', marginBottom: '1.8em' }}>
          <div
            style={{
              font: "400 8.5pt 'IBM Plex Mono', monospace",
              letterSpacing: '.08em',
              textTransform: 'uppercase',
              color: '#8A6512',
            }}
          >
            Snippers · a summary, not the book
          </div>
          <h1
            style={{
              margin: '0.5em 0 0.1em',
              font: "600 22pt/1.18 'Space Grotesk', system-ui, sans-serif",
            }}
          >
            {book.title}
          </h1>
          {book.subtitle && (
            <div style={{ font: "400 12pt/1.35 'Space Grotesk', system-ui", color: '#5D6B66' }}>
              {book.subtitle}
            </div>
          )}
          <div style={{ margin: '0.7em 0 0', font: "400 10.5pt 'Space Grotesk', system-ui" }}>
            {book.author}
          </div>
          <div
            style={{
              marginTop: '0.35em',
              font: "400 8.5pt 'IBM Plex Mono', monospace",
              color: '#7D8A84',
            }}
          >
            {[
              book.category,
              book.pages ? `${book.pages} pages in the original` : null,
              book.isbn ? `ISBN ${book.isbn}` : null,
            ]
              .filter(Boolean)
              .join('  ·  ')}
          </div>
          <p
            style={{
              margin: '1.4em 0 0',
              paddingTop: '1em',
              borderTop: '1px solid #C3B9A6',
              font: "400 9pt/1.55 'Space Grotesk', system-ui",
              color: '#5D6B66',
              maxWidth: '58ch',
            }}
          >
            {book.parts.length} parts, condensed from the book named above. The coloured
            phrases are the ones worth carrying away — they run in palette order through
            each passage, so the colour tells you where you are in a run of ideas rather
            than what kind of idea it is. Read the original if any of it lands.
          </p>
        </header>

        {book.parts.map((part, i) => (
          <Part key={i} part={part} index={i} total={book.parts.length} palette={palette} />
        ))}

        <footer
          style={{
            marginTop: '2.4em',
            paddingTop: '1em',
            borderTop: '1px solid #C3B9A6',
            font: "400 8.5pt 'IBM Plex Mono', monospace",
            color: '#7D8A84',
          }}
        >
          {book.hardcover?.url ? (
            <>
              The book on Hardcover: <a href={book.hardcover.url}>{book.hardcover.url}</a>
            </>
          ) : (
            <>Summarised with Snippers.</>
          )}
        </footer>
      </article>
    </>
  );
}

// Kept so the layout constant is visible to anyone reading the reader alongside this.
export { MAX_PAGES_PER_PART };
