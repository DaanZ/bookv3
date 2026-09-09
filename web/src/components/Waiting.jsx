import { useMemo } from 'react';

import Spinner from './Spinner';
import { Chip } from './ui';
import { paletteFor } from '../lib/reading';
import { chunkWeights, cumulativeWeight, pageRange } from '../lib/waiting';

// The waiting states for a book being processed, from the mark-and-waiting handoff.
//
// The rule underneath both: **a count of what was done, never a percentage bar.** There
// is no honest percentage for a dozen model calls of unknown length, so nothing here
// interpolates or estimates — every number shown is a part that finished.

const MONO = "'IBM Plex Mono', monospace";

/**
 * w1 · Summarising — the rim tracing the chunk cascade.
 *
 * One composite, not two loaders: the mark traces its own hexagon while the bars fill
 * behind it. The bars are **weighted by knowledge, not pages** — the first third of the
 * parts carries 80% of the book, so finishing part 4 of 11 visibly fills most of the
 * row, because it did. That is the whole reason the design exists, and it is why the two
 * text lines carry different numbers: pages are narrow at the front, knowledge is dense
 * there.
 */
export function Summarising({ done, total, bounds, palette = 'sunset', day = false }) {
  const weights = chunkWeights(total);
  const current = Math.min(done, total - 1);

  // The bars are the book's own palette, one stop per part, sampled across the whole
  // ramp exactly as a reading page samples it. So the row fills in the colours this book
  // will be highlighted in, and a long book still sweeps the full spectrum rather than
  // running out of bands — `paletteFor` interpolates to whatever number is asked for.
  const stops = useMemo(() => paletteFor(palette, day, total), [palette, day, total]);

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
      <Spinner variant="mark" size={46} palette={palette} />

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 9, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: 4, height: 48 }}>
          {weights.map((weight, i) => {
            const finished = i < done;
            const live = i === done;
            return (
              <div
                key={i}
                // Width is this part's share of the book's knowledge, not its page count.
                style={{
                  flex: weight,
                  height: finished ? 34 : live ? 48 : 16,
                  borderRadius: 3,
                  // A part that is done or running wears its own colour; one that has
                  // not started stays the faint ground, so the row still reads as a
                  // position at a glance and not as a stripe of decoration.
                  background: finished || live ? stops[i] : 'rgba(253,246,234,.10)',
                  // The live bar breathes in time with the rim, so the composite reads
                  // as one thing rather than two clocks.
                  animation: live ? 'w-chunk var(--spin-rim) var(--ease-move) infinite' : 'none',
                  transition: 'height var(--dur-settle, 260ms) var(--ease-move, ease)',
                }}
              />
            );
          })}
        </div>

        {/* Both lines are driven from the same part number as the bars, so they cannot
            disagree with each other or with the row. */}
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 14 }}>
          <span style={{ font: `400 11.5px ${MONO}`, color: 'var(--text-secondary)' }}>
            {done} of {total} parts summarised ·{' '}
            {Math.round(cumulativeWeight(total, done) * 100)}% of the book&rsquo;s weight
          </span>
          <span
            style={{ font: `400 11.5px ${MONO}`, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}
          >
            part {current + 1}
            {pageRange(bounds, current) ? ` · pages ${pageRange(bounds, current)}` : ''} ·{' '}
            {Math.round(weights[current] * 100)}% of the weight
          </span>
        </div>
      </div>
    </div>
  );
}

/**
 * w2 · Indexing — the seam sweep.
 *
 * The only place gold is allowed in a run. The seam means two sources meeting, and
 * indexing — checking the written book against the rest of the library — is exactly
 * that. Using it for ordinary processing would destroy what it means.
 */
export function Indexing({ total }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
      <Spinner variant="seam" size={68} />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
        <Chip tone="claimed">indexing</Chip>
        <span
          style={{
            fontFamily: 'var(--font-display-wide)',
            fontSize: 14,
            color: 'var(--text-secondary)',
          }}
        >
          Indexing {total} parts against your library
        </span>
      </div>
    </div>
  );
}
