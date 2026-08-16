// The reading model: how a part becomes pages, how far through the book that is,
// and which highlighted phrase takes which colour. Ported from the design of record
// (`bookv3 Demo.dc.html`) — the numbers here are the design, not preferences.

// The five SNCore palettes, in band order. Highlights are handed out in this order:
// first phrase on the page takes band 1, second band 2, and so on to band 8.
export const PALETTES = {
  sunset: ['#313575', '#321951', '#633090', '#723466', '#822E37', '#BA5834', '#F68318', '#FDC005'],
  sunrise: ['#0A2F33', '#12564F', '#1F7F76', '#3EA296', '#8A4A12', '#C56A15', '#EF8A1E', '#F7A94A'],
  coral: ['#6C2E7B', '#E75480', '#FF8A5B', '#FFC857', '#1FA7A6', '#0D3B66', '#8B7FD6', '#FFD8C7'],
  bee: ['#1A141A', '#423738', '#67482F', '#8E5915', '#B97515', '#E59312', '#D3AF85', '#F4B315'],
  rainbow: ['#073A4B', '#0C617C', '#108AB1', '#03B1AB', '#06D7A0', '#FFD167', '#F78C6A', '#F04770'],
};

export const PALETTE_NAMES = ['sunset', 'sunrise', 'coral', 'bee', 'rainbow'];

const INK_DARK = '#14201F';
const INK_CREAM = '#FDF6EA';

function hex2rgb(h) {
  return [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
}

function rgb2hex(c) {
  return '#' + c.map((v) => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, '0')).join('');
}

function toLinear(v) {
  const s = v / 255;
  return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
}

function toSrgb(v) {
  const s = v <= 0.0031308 ? v * 12.92 : 1.055 * Math.pow(v, 1 / 2.4) - 0.055;
  return Math.max(0, Math.min(1, s)) * 255;
}

function lum(h) {
  const [r, g, b] = hex2rgb(h).map(toLinear);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

// Blend in linear light, not in sRGB. Averaging gamma-encoded bytes darkens and muddies
// the midpoint of two saturated colours, which is exactly where the resampled stops land.
function mix(a, b, t) {
  const A = hex2rgb(a).map(toLinear);
  const B = hex2rgb(b).map(toLinear);
  return rgb2hex(A.map((v, i) => toSrgb(v + (B[i] - v) * t)));
}

function rgb2hsl([r, g, b]) {
  const R = r / 255;
  const G = g / 255;
  const B = b / 255;
  const max = Math.max(R, G, B);
  const min = Math.min(R, G, B);
  const l = (max + min) / 2;
  if (max === min) return [0, 0, l];
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  const h =
    max === R ? ((G - B) / d + (G < B ? 6 : 0)) : max === G ? (B - R) / d + 2 : (R - G) / d + 4;
  return [h / 6, s, l];
}

function hsl2hex(h, s, l) {
  if (s === 0) return rgb2hex([l * 255, l * 255, l * 255]);
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  const p = 2 * l - q;
  const channel = (t) => {
    let x = t;
    if (x < 0) x += 1;
    if (x > 1) x -= 1;
    if (x < 1 / 6) return p + (q - p) * 6 * x;
    if (x < 1 / 2) return q;
    if (x < 2 / 3) return p + (q - p) * (2 / 3 - x) * 6;
    return p;
  };
  return rgb2hex([channel(h + 1 / 3) * 255, channel(h) * 255, channel(h - 1 / 3) * 255]);
}

// How far a band has to clear the ground to be read as a highlight rather than as ink.
//
// Deliberately generous rather than maximal. Against the night ground (#0B1A1C) 0.30
// still measures about 5.5:1, comfortably past WCAG AA, and every point above that is
// paid for by the dark end of the ramp: a floor of 0.46 shoved sunset's deep purples up
// until they landed on their own neighbours, ΔE 2. The floor is a backstop for hues that
// would otherwise vanish, not the thing that sets the palette's brightness.
const NIGHT_MIN_LUM = 0.3;
const DAY_MAX_LUM = 0.24;

// Bands are chosen as a ramp, not for contrast, so several sit too close to the ground
// at one end or the other. Saturation is pushed first so the correction happens in
// chroma before it happens in lightness.
const SATURATION_BOOST = 1.3;
const SATURATION_FLOOR = 0.42;

// Below this a band has no hue worth amplifying — bee's near-black opens at #1A141A, and
// forcing saturation onto it would invent a colour the palette never had.
const NEUTRAL = 0.08;

// The lightness window each register gets. Night runs bright on a near-black ground,
// day runs dark on cream; both are ordered dark-stop-first so the palette's own ramp
// direction survives.
const NIGHT_LIGHTNESS = [0.56, 0.86];
const DAY_LIGHTNESS = [0.16, 0.44];

/**
 * Make one band readable while keeping it a colour.
 *
 * The original mixed toward ink or cream until the luminance cleared, which works for
 * contrast and ruins the palette: blending with off-white pulls every band toward grey,
 * so night highlights arrived as pastels of one another. Hue is held and chroma raised
 * instead, and lightness is supplied by the caller — see `paletteFor`, which sets it
 * from the palette's own spread rather than per colour.
 */
export function legible(hex, day, lightness = null) {
  const [h, s0, l0] = rgb2hsl(hex2rgb(hex));
  const s = s0 > NEUTRAL ? Math.max(Math.min(1, s0 * SATURATION_BOOST), SATURATION_FLOOR) : s0;

  let l = lightness == null ? l0 : lightness;
  let out = hsl2hex(h, s, l);

  // Safety net for a hue whose luminance at that lightness still does not clear the
  // ground: saturated blues run dark and yellows run bright, and neither may vanish.
  let guard = 0;
  while (guard++ < 50) {
    if (day ? lum(out) <= DAY_MAX_LUM : lum(out) >= NIGHT_MIN_LUM) break;
    l += day ? -0.02 : 0.02;
    if (l <= 0.05 || l >= 0.94) break;
    out = hsl2hex(h, s, l);
  }
  return out;
}

/** The ramp read as a continuous spectrum: t = 0 is the first band, t = 1 the last. */
function sampleRamp(bands, t) {
  const x = Math.max(0, Math.min(1, t)) * (bands.length - 1);
  const i = Math.min(bands.length - 2, Math.floor(x));
  return mix(bands[i], bands[i + 1], x - i);
}

/**
 * `count` colours spanning the whole palette, in band order.
 *
 * It used to take the first `count` bands, so a page with four highlights only ever saw
 * the dark end of the ramp and the palette's character never arrived. The ramp is a
 * gradient, so it is sampled: four highlights take four stops evenly across the whole
 * spectrum, twelve take twelve. Either way the first highlight on the page is the start
 * of the palette and the last is its end.
 */
export function paletteFor(name, day, count) {
  const bands = PALETTES[name] || PALETTES.sunset;
  const n = Math.max(1, Math.round(count) || 1);
  const stops = Array.from({ length: n }, (_, i) => sampleRamp(bands, n === 1 ? 0 : i / (n - 1)));

  // Rescale the palette's own lightness spread into the register's window, rather than
  // handing each stop a lightness by its index. The bands already separate themselves —
  // sunrise's four oranges run 0.30 to 0.63 — and imposing an even ramp threw that away,
  // pushing stops that were distinct on top of each other. A linear remap keeps every
  // gap the palette designed, just moved to where it can be seen.
  const lightnesses = stops.map((hex) => rgb2hsl(hex2rgb(hex))[2]);
  const low = Math.min(...lightnesses);
  const high = Math.max(...lightnesses);
  const [from, to] = day ? DAY_LIGHTNESS : NIGHT_LIGHTNESS;
  const span = high - low;

  return stops.map((hex, i) => {
    // Every stop at the same lightness: nothing to preserve, so sit in the middle and
    // let hue do the separating.
    const t = span < 0.01 ? 0.5 : (lightnesses[i] - low) / span;
    return legible(hex, day, from + (to - from) * t);
  });
}

// Progress is a logistic curve, not two flat rates.
//
// The old model split the parts in two and gave each half a constant weight, so the bar
// moved at one speed and then abruptly at another — a step at the boundary that is an
// artefact of the arithmetic, not anything about the book. A logistic fits the same
// intuition without the cliff: understanding accumulates slowly at first, fastest
// through the early-middle, and tails off as the later parts elaborate what is already
// known.
//
// The introduction is excluded. It sets up the book rather than being part of it, so
// finishing it should not read as progress through the argument — part 1 carries no
// weight and the curve is fitted over what remains.

// Where the curve is steepest, as a fraction of the content parts. Early, because that
// is where the book is doing its work.
const LOGISTIC_MIDPOINT = 1 / 6;

// The constraint being fitted: the first third of the content carries 80%.
const FIT_AT = 1 / 3;
const FIT_TO = 0.8;

// How much of the bar is shared out evenly, underneath the curve.
//
// A pure logistic satisfies the 80% constraint by collapsing everything after it: the
// last third of a book carried about 1% of the bar, and in a thirty-part book a whole
// part moved it by 0.015% — a page turn with no visible effect. That is the same
// dishonesty as a bar that overstates, pointed the other way: it tells a reader with a
// third of the book left that they are at 99%.
//
// So the curve is blended with a flat share before it is fitted. The logistic still
// decides the shape and the front is still where the weight is; this only guarantees
// that finishing any part moves the bar somewhere a reader can see. At 0.18 the last
// third carries about 7% instead of 1%, the smallest part in a long book is worth
// 0.6%, and the 80%-by-the-first-third constraint is still met exactly, because the
// steepness is re-solved against the blend rather than against the curve alone.
const FLAT_SHARE = 0.18;

const logistic = (x, midpoint, steepness) => 1 / (1 + Math.exp(-steepness * (x - midpoint)));

/** Cumulative share of the book after `x` content parts, for a given steepness. */
function share(x, span, steepness) {
  const midpoint = span * LOGISTIC_MIDPOINT;
  const low = logistic(0, midpoint, steepness);
  const high = logistic(span, midpoint, steepness);
  const curve = high - low < 1e-9 ? x / span : (logistic(x, midpoint, steepness) - low) / (high - low);
  return (1 - FLAT_SHARE) * curve + FLAT_SHARE * (x / span);
}

/**
 * The steepness that puts `FIT_TO` of the book in its first `FIT_AT`.
 *
 * Solved rather than hard-coded: the constraint is the design, and the value that
 * satisfies it depends on how many parts a book has. Bisection converges in well under
 * the iterations given, and the curve is monotonic in steepness, so there is one answer.
 */
function steepnessFor(span) {
  let low = 0.01;
  let high = 40;
  for (let i = 0; i < 60; i += 1) {
    const mid = (low + high) / 2;
    if (share(span * FIT_AT, span, mid) < FIT_TO) low = mid;
    else high = mid;
  }
  return (low + high) / 2;
}

export function weights(n) {
  if (n <= 1) return Array.from({ length: Math.max(0, n) }, () => (n === 1 ? 1 : 0));

  // Part 1 is the introduction and carries nothing; the curve spans the rest.
  const span = n - 1;
  const steepness = steepnessFor(span);
  return Array.from({ length: n }, (_, i) =>
    i === 0 ? 0 : share(i, span, steepness) - share(i - 1, span, steepness),
  );
}

export function cum(n, i) {
  return weights(n).slice(0, i).reduce((a, b) => a + b, 0);
}

/** The part by which the bar has reached 80% — the fitted point, reported honestly. */
export function frontCount(n) {
  if (n <= 1) return n;
  const w = weights(n);
  let running = 0;
  for (let i = 0; i < n; i += 1) {
    running += w[i];
    if (running >= FIT_TO - 1e-9) return i + 1;
  }
  return n;
}

// progress = weight of the parts behind you + the part you are in, scaled by how far
// through its pages you are. pageIndex, not pageIndex + 1: the page you are on is in
// progress, not read. 100% belongs to the finish screen only.
export function progressOf(partCount, partIndex, pageIndex, pageCount) {
  if (!partCount) return 0;
  const through = pageCount ? pageIndex / pageCount : 0;
  return cum(partCount, partIndex) + weights(partCount)[partIndex] * through;
}

// Two sentences to a paragraph, two paragraphs to a page, so a part is two or three
// pages and the bar moves inside a chapter.
const PARAGRAPHS_PER_PAGE = 2;

// …but never more than this many pages in one part. "Page 6 of 10 in this part" is a
// chapter that has stopped feeling finishable, which is the opposite of what the page
// count is for. Past the limit the page gets denser rather than the part getting longer:
// the number of pages is what the reader is judging distance by, so that is the number
// held still.
export const MAX_PAGES_PER_PART = 5;

export function paginate(body) {
  const sentences = normaliseBody(body)
    .split(/\n\n+/)
    .flatMap((par) => par.split(/(?<=[.?!”"])\s+/).filter((s) => s.trim()));
  const paras = [];
  for (let i = 0; i < sentences.length; i += 2) paras.push(sentences.slice(i, i + 2).join(' '));

  // Only long parts are affected. A part that already fits keeps two paragraphs a page,
  // so the common case reads exactly as it did.
  const perPage = Math.max(
    PARAGRAPHS_PER_PAGE,
    Math.ceil(paras.length / MAX_PAGES_PER_PART),
  );

  const pages = [];
  for (let i = 0; i < paras.length; i += perPage) pages.push(paras.slice(i, i + perPage));
  return pages.length ? pages : [paras];
}

// The cap counts marks on the page, not distinct phrases: after the budget is spent the
// rest of the page stays plain, so the eye never has more than `cap` anchors to hold.
export function tokensOf(text, palette, cap, budget) {
  const out = [];
  const re = /<b>([\s\S]*?)<\/b>/g;
  let last = 0;
  let m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push({ text: plain(text.slice(last, m.index)), weight: 400, color: 'inherit' });
    const key = m[1].toLowerCase().replace(/[^a-z ]/g, '');
    const known = budget.map.has(key);
    if (budget.used < cap && (known || budget.map.size < cap)) {
      if (!known) budget.map.set(key, budget.map.size);
      budget.used += 1;
      out.push({ text: m[1], weight: 600, color: palette[budget.map.get(key)] });
    } else {
      out.push({ text: m[1], weight: 400, color: 'inherit' });
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push({ text: plain(text.slice(last)), weight: 400, color: 'inherit' });
  return out;
}

// A sentence split can strand a closing tag at the head of a page when a highlight ends
// on a sentence boundary. An orphan never pairs, so it is dropped rather than printed.
function plain(text) {
  return text.replace(/<\/?b>/g, '');
}

export function newBudget() {
  return { map: new Map(), used: 0 };
}

/**
 * How many distinct phrases on this page will actually take a colour.
 *
 * The palette is built to this number, so it has to agree with `tokensOf` exactly — a
 * count that is one too high leaves the last stop unused and shortens the sweep, one too
 * low reads `palette[n]` as undefined and prints a highlight in body ink. Rather than
 * restate the budget rules and risk them drifting apart, it runs the real thing over a
 * throwaway palette and asks the budget what it did.
 */
export function highlightCount(sentences, cap) {
  const budget = newBudget();
  for (const sentence of sentences || []) tokensOf(sentence, [], cap, budget);
  return budget.map.size;
}

// The pipeline stores bodies as HTML, and `chunks.format_text` writes the highlight as
// `<b style='color: forestgreen;'>` — the colour is baked into the tag. The UI decides
// how a highlight is shown, so the attributes are dropped here and only the <b> boundary
// is kept as the source of truth for *what* is important. <h3> and <em> lose their tags
// but keep their text; anything else would print as literal angle brackets on the page.
export function normaliseBody(html) {
  return (html || '')
    .replace(/<b\b[^>]*>/gi, '<b>')
    .replace(/<\/b\s*>/gi, '</b>')
    .replace(/<(?!\/?b>)[^>]*>/g, '');
}
