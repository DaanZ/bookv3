// Two suggestions, pulling opposite ways on purpose.
//
// `fromLibrary` is the shelf's: what this reader has read points at what they might read
// next, so it needs a profile and says nothing without one.
//
// `recommendations` is the finish screen's: "switching topics beats stopping." When
// attention is spent, offer the book *furthest* from what was just read, so the screen is
// a doorway rather than a dead end.
//
// Both work over the category text rather than the patch family, because two books can
// share a family ("business") and still be far apart ("negotiation" vs "startup growth").

// 'uncategorised' earns its place here: it is `library.py`'s fallback for the 68 books
// whose JSON predates meta.category, and two books sharing it share nothing at all. Left
// in, it read as a subject — enough for "because you read X" to appear over a pair of
// books whose only common ground was that nobody had said what they were about.
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

/**
 * What to read next, from what this reader has already read.
 *
 * The opposite rule to the one below, and deliberately so. The finish screen offers the
 * book *furthest* from what was just put down, because attention is spent and switching
 * topics beats stopping. The shelf is the other moment — somebody choosing, unhurried —
 * so it offers what their own history points at.
 *
 * That history is the whole input, which is why this needs a profile and returns nothing
 * without one. A guest has read nothing here; there is no honest suggestion to make, and
 * inventing one from the shelf at large would be recommending the house's taste back to
 * a stranger.
 */
export function fromLibrary(books, limit = 3) {
  const read = books.filter((b) => b.state === 'read');
  if (read.length === 0) return [];

  // How much this reader has read of each subject word, so a shelf with six business
  // books pulls harder toward business than one with a single outlier in it.
  const weight = new Map();
  for (const book of read) {
    for (const word of tokenise(book.category)) {
      weight.set(word, (weight.get(word) || 0) + 1);
    }
  }
  const families = new Set(read.map((b) => b.family));

  return books
    .filter((b) => b.state === 'new')
    .map((book) => {
      const words = tokenise(book.category);
      let score = 0;
      for (const word of words) score += weight.get(word) || 0;
      // A shared family is a weaker signal than a shared word, and only breaks ties.
      if (families.has(book.family)) score += 0.4;
      // The book of theirs this one most looks like: what the row says out loud, so a
      // suggestion is never a machine being mysterious about why.
      const because = read
        .map((other) => ({
          other,
          shared: [...tokenise(other.category)].filter((w) => words.has(w)).length,
        }))
        .sort((a, b) => b.shared - a.shared)[0];
      return { book, score, because: because?.shared ? because.other : null };
    })
    .filter((entry) => entry.score > 0 && entry.because)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);
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
