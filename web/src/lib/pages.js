// How a part becomes pages, how far through the book that is, and which phrases on a page
// are highlighted: pagination, the front-weighted progress curve and the highlight budget.

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

const logistic = (x, midpoint, steepness) => 1 / (1 + Math.exp(-steepness * (x - midpoint)));

/** Cumulative share of the book after `x` content parts, for a given steepness. */
function share(x, span, steepness) {
  const midpoint = span * LOGISTIC_MIDPOINT;
  const low = logistic(0, midpoint, steepness);
  const high = logistic(span, midpoint, steepness);
  if (high - low < 1e-9) return x / span;
  return (logistic(x, midpoint, steepness) - low) / (high - low);
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
      const slot = budget.map.get(key);
      out.push({ text: m[1], weight: 600, color: palette[slot], slot });
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
  return highlightKeys(sentences, cap).length;
}

/** The phrases on this page that will take a colour, keyed as `tokensOf` keys them, in slot order. */
export function highlightKeys(sentences, cap) {
  const budget = newBudget();
  for (const sentence of sentences || []) tokensOf(sentence, [], cap, budget);
  return [...budget.map.keys()];
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
