// The finish screen's suggestion: "switching topics beats stopping." When attention is
// spent, offer the book *furthest* from what was just read, so the screen is a doorway
// rather than a dead end.
//
// The shelf used to carry a second one, `fromLibrary` — the unread book nearest what the
// reader had finished. It was removed: the shelf now shuffles instead, which serves
// "find something new to start" better than steering toward more of the same.
//
// It works over the category text rather than the patch family, because two books can
// share a family ("business") and still be far apart ("negotiation" vs "startup growth").

// 'uncategorised' earns its place here: it is `library.py`'s fallback for the 68 books
// whose JSON predates meta.category, and two books sharing it share nothing at all. Left
// in, it read as a subject — enough to call two books related whose only common ground
// was that nobody had said what they were about.
const STOP = new Set([
  'and', 'the', 'of', 'a', 'for', 'in', 'to', 'non', 'general', 'uncategorised',
]);

function tokenise(category) {
  return new Set(
    (category || '')
      .toLowerCase()
      .split(/[^a-z]+/)
      .filter((w) => w.length > 2 && !STOP.has(w)),
  );
}

// Jaccard distance: 1 when the two categories share no words at all.
function distance(a, b) {
  const A = tokenise(a);
  const B = tokenise(b);
  if (A.size === 0 || B.size === 0) return 0.5; // Unknown is neither near nor far.
  let shared = 0;
  for (const word of A) if (B.has(word)) shared += 1;
  const union = A.size + B.size - shared;
  return union === 0 ? 0 : 1 - shared / union;
}

export function recommendations(books, finishedKey, finishedCategory, finishedFamily) {
  return books
    .filter((b) => b.key !== finishedKey && b.state !== 'read')
    .map((b) => ({
      book: b,
      // A different patch family is a visible signal of distance, so it breaks ties.
      score: distance(finishedCategory, b.category) + (b.family === finishedFamily ? 0 : 0.15),
    }))
    .sort((x, y) => y.score - x.score)
    .map((entry) => entry.book);
}
