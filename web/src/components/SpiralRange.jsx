// Pick a band of the spiral: two handles on one track, in tenths, over the Spiral Dynamics
// grades of the books on this screen (api/spiral.py). The track runs from the lowest grade
// here to the highest, not 3 to 8: the library bunches between about 4.4 and 7.4, and a
// full-width track left most of the slider over nothing.
//
// Two native range inputs laid over each other, so both handles stay keyboard and
// screen-reader controls; app.css lets only their thumbs take the pointer.

import { useMemo } from 'react';

import { SPIRAL_DOTS, SPIRAL_MEMES } from './SpiralPill';

const MONO = "'IBM Plex Mono', monospace";

// The level a grade shows as, as the pill shows it (api/spiral.py `level_of`): its whole
// number. Taken in tenths first, since 6.0 can arrive as 5.999999999999999.
const levelOf = (score) => Math.floor(Math.round(score * 10) / 10);
const tenths = (score) => Math.round(score * 10);

/**
 * @param scores  every graded book's score on this screen, before the band narrows it
 * @param value   [low, high], or null for the whole range
 * @param count   books shown with the band applied
 */
export default function SpiralRange({ scores, value, onChange, count }) {
  const { min, max, bins } = useMemo(() => {
    const t = scores.map(tenths);
    const lo = Math.min(...t);
    const hi = Math.max(...t);
    const out = [];
    for (let x = lo; x <= hi; x += 1) out.push({ at: x / 10 });
    return { min: lo / 10, max: hi / 10, bins: out };
  }, [scores]);

  if (!scores.length || min === max) return null;

  const low = value ? Math.max(value[0], min) : min;
  const high = value ? Math.min(value[1], max) : max;
  const whole = low <= min && high >= max;
  const pct = (v) => ((v - min) / (max - min)) * 100;
  // Back to null when the band covers everything, so "the whole range" stays one state.
  const set = (l, h) => onChange(l <= min && h >= max ? null : [l, h]);

  // The chosen band's colour: each level's colour across the part of the track it covers.
  const stops = bins.map((b) => `${SPIRAL_DOTS[levelOf(b.at)]} ${pct(b.at)}%`).join(', ');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12 }}>
        <span style={{ font: `400 11.5px ${MONO}`, color: 'var(--text-muted)' }}>
          spiral {low.toFixed(1)} {SPIRAL_MEMES[levelOf(low)]} to {high.toFixed(1)} {SPIRAL_MEMES[levelOf(high)]}
          {` · ${count} ${count === 1 ? 'book' : 'books'}`}
        </span>
        {!whole && (
          <button
            type="button"
            className="tap"
            onClick={() => onChange(null)}
            style={{ width: 'auto', font: "500 12px 'Space Grotesk', system-ui", color: 'var(--text-secondary)', borderBottom: '1px dotted var(--text-muted)' }}
          >
            Whole spiral
          </button>
        )}
      </div>

      <div className="spiral-range" style={{ position: 'relative', height: 28 }}>
        {/* The track: faint across the whole range, the chosen band in its levels' colours.
            Inset by the thumb's half-width so the colours line up with the handles. */}
        <div style={{ position: 'absolute', left: 11, right: 11, top: 12, height: 4 }}>
          <div style={{ position: 'absolute', inset: 0, borderRadius: 2, background: 'var(--border-subtle)' }} />
          <div
            style={{
              position: 'absolute',
              inset: 0,
              borderRadius: 2,
              background: `linear-gradient(90deg, ${stops})`,
              clipPath: `inset(0 ${100 - pct(high)}% 0 ${pct(low)}%)`,
            }}
          />
        </div>
        <input
          type="range"
          min={min}
          max={max}
          step={0.1}
          value={low}
          aria-label="Lowest spiral grade"
          onChange={(e) => set(Math.min(Number(e.target.value), high), high)}
        />
        <input
          type="range"
          min={min}
          max={max}
          step={0.1}
          value={high}
          aria-label="Highest spiral grade"
          onChange={(e) => set(low, Math.max(Number(e.target.value), low))}
        />
      </div>
    </div>
  );
}
