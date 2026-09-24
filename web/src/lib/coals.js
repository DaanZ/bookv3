import { legible } from './colour.js';
import { normaliseBody } from './pages.js';

// ── Coals ──────────────────────────────────────────────────────────────────────────
//
// Highlights are drawn as coals in a fire: the most important phrases on a page burn
// hottest and draw the eye first, the rest glow or smoulder. Staring into the hearth,
// but what you are watching is the part of the page that matters.
//
// Three heats, and the colours they burn in belong to the book's shelf. The room is
// always graphite and orange; the category decides what its coals look like, so a
// psychology book and a programming book feel different before a word is read, and
// nothing else on the page changes.
//
// The colours arrive with the book (`book.coals`, from `coals_for` in api/patches.py),
// beside the family list they are keyed by. They used to be a second table here, keyed by
// family name, and a family renamed on one side fell through to the fire without a sound.
export const HEATS = ['smouldering', 'glowing', 'hot'];

// Only for a book that arrives without `coals`: one kept offline from before the API sent
// them. The same colours as the API's `fire`, and the one copy of them in the web app.
const FALLBACK = {
  ink: ['#E65A64', '#F68318', '#FDC005'],
  glow: ['#B22E37', '#C95F0C', '#E0A200'],
};

function alpha(hex, a) {
  return hex + Math.round(a * 255).toString(16).padStart(2, '0');
}

/**
 * The ink and glow for each heat, index = heat, from the book's `coals`.
 *
 * The glow is layered the way a coal looks: a smouldering one has a haze of its own
 * colour, a hot one a bright core that cools outward through the glowing colour. By day
 * there is no glow — light does not glow on paper, so heat is carried by weight — and the
 * inks, designed for night, are pulled dark enough to read on cream by `legible`.
 */
export function coalsFor(coals, day) {
  const { ink, glow } = coals?.ink?.length === 3 && coals?.glow?.length === 3 ? coals : FALLBACK;
  if (day) return { ink: ink.map((hex) => legible(hex, true)), glow: ['none', 'none', 'none'] };
  return {
    ink,
    glow: [
      `0 0 10px ${alpha(glow[0], 0.9)}`,
      `0 0 4px ${alpha(ink[1], 0.55)}, 0 0 16px ${alpha(glow[1], 0.7)}`,
      `0 0 3px ${alpha(ink[2], 0.75)}, 0 0 12px ${alpha(glow[2], 0.65)}, 0 0 28px ${alpha(glow[1], 0.55)}`,
    ],
  };
}

// The same normalisation `tokensOf` gives a phrase to use as its key: lower case, letters
// and spaces only. Whitespace becomes a space rather than vanishing, so the last word of
// one paragraph does not fuse with the first of the next.
function keyText(text) {
  return text.toLowerCase().replace(/\s+/g, ' ').replace(/[^a-z ]/g, '');
}

/**
 * How often each highlighted phrase occurs across the whole book, as a lookup.
 *
 * This is what decides heat, because the pipeline's `<b>` says only *that* a phrase
 * matters, not how much. A phrase the book keeps returning to is one of its subjects;
 * one it mentions once is colour. "Brainwashing" in a book about brainwashing burns hot
 * and "hogwash" smoulders, which is the right way round. Counted in the plain text,
 * highlighted or not, so a subject that is only bolded once still counts every mention.
 */
export function phraseCounter(parts) {
  const text = ` ${keyText((parts || []).map((part) => normaliseBody(part.body).replace(/<\/?b>/g, ' ')).join(' '))} `;
  const cache = new Map();
  return (key) => {
    if (cache.has(key)) return cache.get(key);
    let count = 0;
    const needle = key.trim();
    if (needle) {
      for (let at = text.indexOf(needle); at >= 0; at = text.indexOf(needle, at + needle.length)) {
        count += 1;
      }
    }
    cache.set(key, count);
    return count;
  };
}

/**
 * A heat for each highlighted phrase on a page, in slot order, from how often each
 * recurs in the book.
 *
 * Relative to the page, not absolute: every page has something hottest, because the
 * point is where to look *here*. The top quarter burns hot, the bottom quarter
 * smoulders, the rest glow — so a full page of eight has two of each extreme, and a
 * page with one highlight has one hot coal. Ties go to the phrase met first.
 */
export function heatsOf(counts) {
  const n = counts.length;
  const hot = Math.ceil(n / 4);
  const cold = Math.floor(n / 4);
  const ranked = counts.map((count, slot) => ({ count, slot })).sort((a, b) => b.count - a.count || a.slot - b.slot);
  const heats = new Array(n);
  ranked.forEach(({ slot }, rank) => {
    heats[slot] = rank < hot ? 2 : rank >= n - cold ? 0 : 1;
  });
  return heats;
}
