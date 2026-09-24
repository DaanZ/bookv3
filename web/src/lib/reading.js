// The reading model, as one import. Ported from the design of record
// (`bookv3 Demo.dc.html`) — the numbers in these modules are the design, not preferences.
//
//   colour.js    conversion, linear-light blending, `legible`
//   palettes.js  the five palettes and `paletteFor`, the band-order sweep
//   coals.js     the reading page's highlights: heat per phrase, colours from the book
//   pages.js     pagination, the progress curve, the highlight budget
//
// Screens and tools import from here; the split is for reading the code, not for callers.
// `web/test/reading.test.mjs` pins the rules — run `npm test` after touching any of them.

export { legible } from './colour.js';
export { PALETTES, PALETTE_NAMES, paletteFor } from './palettes.js';
export { HEATS, coalsFor, heatsOf, phraseCounter } from './coals.js';
export {
  MAX_PAGES_PER_PART,
  cum,
  frontCount,
  highlightCount,
  highlightKeys,
  newBudget,
  normaliseBody,
  paginate,
  progressOf,
  tokensOf,
  weights,
} from './pages.js';
