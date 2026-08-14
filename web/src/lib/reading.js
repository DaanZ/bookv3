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

function lum(h) {
  const [r, g, b] = hex2rgb(h).map((v) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function mix(a, b, t) {
  const A = hex2rgb(a);
  const B = hex2rgb(b);
  return rgb2hex(A.map((v, i) => v + (B[i] - v) * t));
}

// Keep the band's hue and its place in the ramp; only move it far enough to be read.
export function legible(h, day) {
  let out = h;
  let t = 0;
  while (t < 0.9 && (day ? lum(out) > 0.28 : lum(out) < 0.42)) {
    t += 0.1;
    out = mix(h, day ? INK_DARK : INK_CREAM, t);
  }
  return out;
}

export function paletteFor(name, day, cap) {
  const bands = PALETTES[name] || PALETTES.sunset;
  return bands.slice(0, cap).map((h) => legible(h, day));
}

// The first 40% of the parts carry 80% of the progress: the front of a book is where
// the information is, so finishing part 4 of 10 should read as most of the way there.
export function weights(n) {
  const front = Math.max(1, Math.round(n * 0.4));
  const back = Math.max(1, n - front);
  return Array.from({ length: n }, (_, i) => (i < front ? 0.8 / front : 0.2 / back));
}

export function cum(n, i) {
  return weights(n).slice(0, i).reduce((a, b) => a + b, 0);
}

export function frontCount(n) {
  return Math.max(1, Math.round(n * 0.4));
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
export function paginate(body) {
  const sentences = normaliseBody(body)
    .split(/\n\n+/)
    .flatMap((par) => par.split(/(?<=[.?!”"])\s+/).filter((s) => s.trim()));
  const paras = [];
  for (let i = 0; i < sentences.length; i += 2) paras.push(sentences.slice(i, i + 2).join(' '));
  const pages = [];
  for (let i = 0; i < paras.length; i += 2) pages.push(paras.slice(i, i + 2));
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
