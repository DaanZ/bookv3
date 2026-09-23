// The Snippers mark: one S, and behind it the pages it came from, fanning out from the
// spine and cooling from flame through red into night purple.
//
// This module is the source of truth for the mark. `components/Mark.jsx` draws it in the
// app and `tools/export-mark.mjs` writes the favicon, app icons and tray artwork from the
// same numbers, so a change here reaches every surface on the next export.
//
// **The S is an outline, not a font.** It is the capital S of Space Grotesk Bold (SIL
// Open Font License), extracted once with fontTools so that a favicon, a PNG and a tray
// icon do not depend on a webfont having loaded. Font units: 1000 to the em, y up,
// baseline at 0, bounds x 34..574 and y -14..714.
export const GLYPH =
  'M309 -14Q228 -14 166.0 15.0Q104 44 69.0 98.0Q34 152 34 228V256H164V228Q164 165 203.0 133.5Q242 102 309 102Q377 102 410.5 129.0Q444 156 444 198Q444 227 427.5 245.0Q411 263 379.5 274.5Q348 286 303 296L280 301Q208 317 156.5 341.5Q105 366 77.5 406.0Q50 446 50 510Q50 574 80.5 619.5Q111 665 166.5 689.5Q222 714 297 714Q372 714 430.5 688.5Q489 663 522.5 612.5Q556 562 556 486V456H426V486Q426 526 410.5 550.5Q395 575 366.0 586.5Q337 598 297 598Q237 598 208.5 575.5Q180 553 180 514Q180 488 193.5 470.0Q207 452 234.0 440.0Q261 428 303 419L326 414Q401 398 456.5 373.0Q512 348 543.0 307.0Q574 266 574 202Q574 138 541.5 89.5Q509 41 449.5 13.5Q390 -14 309 -14Z';

// Where the glyph sits in the mark's 900 x 1000 drawing space: a 1100-unit S on a
// baseline at y 900, the same geometry the design canvas was drawn in.
export const GLYPH_TRANSFORM = 'translate(40 900) scale(1.1 -1.1)';

// The front S: gold where the coals are, cooling to red at the top. Offset 0 is the
// top, and every gradient over the glyph must be drawn y1=1 -> y2=0 to get that: the
// gradient's box is the path's own, which is flipped (font y points up), so the usual
// y1=0 -> y2=1 paints it upside down.
export const FRONT_GRADIENT = [
  { offset: 0, color: '#B22E37' },
  { offset: 0.55, color: '#F68318' },
  { offset: 1, color: '#FDC005' },
];

// Condensed to 72%. Every page behind it is drawn from the same left edge, a little
// further out and a little wider, like leaves fanning from a spine.
export const FRONT_SCALE = 0.72;

/**
 * The pages behind the S, nearest first: [x offset, horizontal scale, fill, opacity].
 *
 * Three sets, because a page that reads at 700px is noise at 32. Pages drop out as the
 * mark shrinks, and at 16px the S stands alone — that is the design, not a shortcut.
 */
export const PAGES = {
  full: [
    [62, 0.74, '#F68318', 1],
    [86, 0.76, '#B22E37', 1],
    [112, 0.785, '#B22E37', 0.85],
    [140, 0.81, '#633090', 1],
    [172, 0.84, '#633090', 0.8],
    [206, 0.87, '#313575', 1],
    [244, 0.905, '#313575', 0.7],
    [286, 0.94, '#321951', 0.6],
  ],
  icon: [
    [60, 0.74, '#F68318', 1],
    [84, 0.76, '#B22E37', 1],
    [118, 0.79, '#633090', 1],
    [160, 0.83, '#633090', 0.8],
    [206, 0.87, '#313575', 0.6],
  ],
  small: [[130, 0.8, '#B22E37', 1]],
  bare: [],
};

/** The SVG transform for one page: fan out from the S's left edge at x = 40. */
export function pageTransform(offset, scale) {
  return `translate(${offset + 40} 0) scale(${scale} 1) translate(-40 0)`;
}

export const FRONT_TRANSFORM = pageTransform(0, FRONT_SCALE);

// Square crops of the drawing space, sized to the pages each set actually uses.
// `tile` leaves room for a rounded tile's corners; `maskable` keeps the whole mark
// inside the 80% safe zone an OS mask is allowed to cut into.
//
// Each is centred on its own content: the S runs y 115..915 in every set, and x from 67
// to the right edge of the furthest page (795 for `icon`, 675 for `small`, 494 bare).
export const VIEWBOX = {
  full: '0 0 900 1000',
  icon: '-69 15 1000 1000',
  small: '-129 15 1000 1000',
  bare: '-220 15 1000 1000',
  maskable: '-159 -75 1180 1180',
};
