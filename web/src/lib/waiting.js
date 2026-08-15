// The model behind the summarising bars.
//
// Front-weighted, like the reader's progress bar — but **not the same split**, and the
// two must not be merged. The reader uses the first 40% of parts for 80% of the bar;
// the waiting state uses the first third, per the mark-and-waiting handoff. They answer
// different questions (how far through am I, versus how much of the book is understood)
// and a shared constant would quietly change one when the other was tuned.

const FRONT_SHARE = 1 / 3;
const FRONT_WEIGHT = 0.8;

/** Each part's share of the book's knowledge. */
export function chunkWeights(n) {
  const front = Math.max(1, Math.round(n * FRONT_SHARE));
  const back = Math.max(1, n - front);
  return Array.from({ length: n }, (_, i) =>
    i < front ? FRONT_WEIGHT / front : (1 - FRONT_WEIGHT) / back,
  );
}

/** Weight carried by the first `k` parts — what "60% of the book's weight" means. */
export function cumulativeWeight(n, k) {
  return chunkWeights(n)
    .slice(0, Math.max(0, k))
    .reduce((a, b) => a + b, 0);
}

/**
 * The page range a part covers, as "31–44".
 *
 * `bounds` comes from the API, which computes it with the same `util/split.py` the
 * pipeline splits by — the Gaussian edges are not re-derived in JavaScript, because a
 * second implementation of that curve would drift from the one that cut the book.
 * Returns null when the job predates the field, so the line is simply omitted.
 */
export function pageRange(bounds, index) {
  const pair = bounds?.[index];
  if (!pair) return null;
  const [start, end] = pair;
  return `${start + 1}–${end}`;
}
