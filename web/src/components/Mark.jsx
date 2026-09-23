import { useId } from 'react';

import {
  FRONT_GRADIENT,
  FRONT_TRANSFORM,
  GLYPH,
  GLYPH_TRANSFORM,
  PAGES,
  VIEWBOX,
  pageTransform,
} from '../lib/mark';

/**
 * The Snippers S with its pages behind it. Drawn from `lib/mark.js`, the same numbers
 * the favicon and app icons are exported from.
 *
 * @param pages  which set of pages: `small` (one, for chrome), `icon`, `full`, `bare`
 * @param size   rendered height in px; the width follows the square crop
 * @param label  accessible name, or null when a visible word already names it
 */
export default function Mark({ pages = 'small', size = 16, label = null }) {
  // useId's punctuation is not safe inside url(#…) in every engine, so keep the letters.
  const gradient = `mark-${useId().replace(/[^\w-]/g, '')}`;
  const layers = PAGES[pages] || PAGES.small;
  const viewBox = VIEWBOX[pages] || VIEWBOX.small;

  return (
    <svg
      viewBox={viewBox}
      width={size}
      height={size}
      role={label ? 'img' : undefined}
      aria-label={label || undefined}
      aria-hidden={label ? undefined : true}
      style={{ display: 'block', flexShrink: 0 }}
    >
      <defs>
        <linearGradient id={gradient} x1="0" y1="1" x2="0" y2="0">
          {FRONT_GRADIENT.map((stop) => (
            <stop key={stop.offset} offset={stop.offset} stopColor={stop.color} />
          ))}
        </linearGradient>
      </defs>
      {/* Furthest page first, so each nearer one covers all but its right edge. */}
      {[...layers].reverse().map(([offset, scale, fill, opacity]) => (
        <g key={offset} transform={pageTransform(offset, scale)}>
          <path d={GLYPH} transform={GLYPH_TRANSFORM} fill={fill} opacity={opacity} />
        </g>
      ))}
      <g transform={FRONT_TRANSFORM}>
        <path d={GLYPH} transform={GLYPH_TRANSFORM} fill={`url(#${gradient})`} />
      </g>
    </svg>
  );
}
