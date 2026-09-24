// The reading model's rules, pinned. Run with `npm test` in web/ (Node's own runner, no
// dependencies). Each test names a rule the code comments or CLAUDE.md state in words, so
// a failure says which promise broke rather than which number moved.

import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { describe, test } from 'node:test';

import {
  coalsFor,
  cum,
  frontCount,
  heatsOf,
  highlightCount,
  highlightKeys,
  legible,
  MAX_PAGES_PER_PART,
  newBudget,
  normaliseBody,
  paginate,
  PALETTE_NAMES,
  PALETTES,
  paletteFor,
  phraseCounter,
  progressOf,
  tokensOf,
  weights,
} from '../src/lib/reading.js';

// WCAG relative luminance, written out here rather than imported so the tests do not
// trust the code they are checking.
function luminance(hex) {
  const channel = (i) => {
    const v = parseInt(hex.slice(i, i + 2), 16) / 255;
    return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5);
}

function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const GRAPHITE = '#1C1C1C';

// The coal colours live in api/patches.py and reach the reader on the book payload, so the
// tests ask Python for them rather than keeping a third copy here. That also checks the
// hand-over itself: what `coals_for` returns is exactly what `coalsFor` is given.
const REPO = fileURLToPath(new URL('../../', import.meta.url));
function fromApi(expression) {
  const script = `import json
from api.patches import COALS, coals_for
print(json.dumps(${expression}))`;
  return JSON.parse(execFileSync('python', ['-c', script], { cwd: REPO, encoding: 'utf8' }));
}
const sentences = (n) => Array.from({ length: n }, (_, i) => `Sentence ${i + 1}.`).join(' ');

describe('normaliseBody', () => {
  test('strips the colour the pipeline bakes into <b>, keeping the boundary', () => {
    assert.equal(normaliseBody("a <b style='color: forestgreen;'>key</b> b"), 'a <b>key</b> b');
  });

  test('drops every other tag but keeps its text', () => {
    assert.equal(normaliseBody('<h3>Title</h3> and <em>this</em>'), 'Title and this');
  });

  test('treats a missing body as empty', () => {
    assert.equal(normaliseBody(undefined), '');
  });
});

describe('paginate', () => {
  test('two sentences to a paragraph, two paragraphs to a page', () => {
    const pages = paginate(sentences(8));
    assert.deepEqual(pages, [
      ['Sentence 1. Sentence 2.', 'Sentence 3. Sentence 4.'],
      ['Sentence 5. Sentence 6.', 'Sentence 7. Sentence 8.'],
    ]);
  });

  test(`never more than ${MAX_PAGES_PER_PART} pages in a part: long parts get denser pages`, () => {
    const pages = paginate(sentences(80));
    assert.equal(pages.length, MAX_PAGES_PER_PART);
    assert.equal(pages.flat().join(' '), sentences(80));
  });

  test('an empty part is one empty page, not no pages', () => {
    assert.deepEqual(paginate(''), [[]]);
  });
});

describe('tokensOf and the highlight budget', () => {
  test('the cap counts marks on the page, not distinct phrases', () => {
    const tokens = tokensOf('<b>a</b> <b>b</b> <b>a</b>', ['#1', '#2'], 2, newBudget());
    const marked = tokens.filter((t) => t.slot != null).map((t) => t.text);
    assert.deepEqual(marked, ['a', 'b']);
    assert.equal(tokens.at(-1).weight, 400, 'the third mark is past the cap and stays plain');
  });

  test('a repeated phrase keeps its slot, and so its colour', () => {
    const tokens = tokensOf('<b>Key</b> and <b>key</b>', ['#1', '#2'], 8, newBudget());
    const slots = tokens.filter((t) => t.slot != null).map((t) => t.slot);
    assert.deepEqual(slots, [0, 0]);
  });

  test('the budget carries across the sentences of one page', () => {
    const budget = newBudget();
    tokensOf('<b>one</b>', ['#1'], 1, budget);
    const second = tokensOf('<b>two</b>', ['#1'], 1, budget);
    assert.equal(second[0].slot, undefined);
  });

  test('an orphaned tag stranded by a sentence split is dropped, not printed', () => {
    const tokens = tokensOf('</b>plain text', [], 8, newBudget());
    assert.equal(tokens.map((t) => t.text).join(''), 'plain text');
  });

  test('highlightCount and highlightKeys agree with what tokensOf spends', () => {
    const page = ['<b>Alpha</b> then <b>Beta</b>.', 'Again <b>alpha</b> and <b>Gamma</b>.'];
    assert.deepEqual(highlightKeys(page, 8), ['alpha', 'beta', 'gamma']);
    assert.equal(highlightCount(page, 8), 3);
    assert.equal(highlightCount(page, 2), 2);
  });
});

describe('progress', () => {
  test('weights sum to the whole book', () => {
    for (const n of [2, 5, 14, 30]) {
      const total = weights(n).reduce((a, b) => a + b, 0);
      assert.ok(Math.abs(total - 1) < 1e-9, `n=${n} sums to ${total}`);
    }
  });

  test('the introduction carries no weight', () => {
    assert.equal(weights(14)[0], 0);
  });

  test('a one-part book is all in that part', () => {
    assert.deepEqual(weights(1), [1]);
  });

  test('the first third of the content carries 80% of the bar', () => {
    const n = 31;
    const content = n - 1;
    assert.ok(Math.abs(cum(n, 1 + content / 3) - 0.8) < 0.01);
    assert.ok(frontCount(n) <= Math.ceil(1 + content / 3));
  });

  test('the page you are on is in progress, not read: 100% belongs to the finish screen', () => {
    assert.equal(progressOf(14, 0, 0, 3), 0);
    assert.ok(progressOf(14, 13, 2, 3) < 1);
  });
});

describe('palettes', () => {
  test('paletteFor returns exactly as many stops as asked', () => {
    for (const n of [1, 3, 8, 12]) assert.equal(paletteFor('sunset', false, n).length, n);
  });

  test('every stop of every palette clears the contrast floor in both registers', () => {
    for (const name of PALETTE_NAMES) {
      for (const colour of paletteFor(name, false, 8)) {
        assert.ok(luminance(colour) >= 0.3 - 1e-3, `${name} night ${colour}`);
      }
      for (const colour of paletteFor(name, true, 8)) {
        assert.ok(luminance(colour) <= 0.24 + 1e-3, `${name} day ${colour}`);
      }
    }
  });

  test('the sweep is sampled across the whole ramp: sunset at night, the published stops', () => {
    // docs/colour-themes.md, section 3. A change here must regenerate that file.
    assert.deepEqual(paletteFor('sunset', false, 8), [
      '#8e92dc', '#b287e9', '#ba88e6', '#d482c4', '#e17e89', '#f1bba7', '#ffdab8', '#ffebac',
    ]);
  });

  test('an unknown palette name falls back to sunset', () => {
    assert.deepEqual(paletteFor('nope', false, 4), paletteFor('sunset', false, 4));
  });

  test('every palette has eight bands', () => {
    for (const name of PALETTE_NAMES) assert.equal(PALETTES[name].length, 8, name);
  });

  test('legible lifts a dark band at night and darkens a light one by day', () => {
    assert.ok(luminance(legible('#321951', false)) >= 0.3);
    assert.ok(luminance(legible('#FDC005', true)) <= 0.24);
  });
});

describe('coals', () => {
  test('heat comes from how often the book mentions a phrase, tags and case aside', () => {
    const count = phraseCounter([
      { body: '<b>Brainwashing</b> is old. brainwashing again.' },
      { body: '<p>More BRAINWASHING</p> and one hogwash.' },
    ]);
    assert.equal(count('brainwashing'), 3);
    assert.equal(count('hogwash'), 1);
    assert.equal(count('absent'), 0);
  });

  test('a paragraph break is a space: two paragraphs never fuse into one phrase', () => {
    const count = phraseCounter([{ body: 'the end\n\nstart here' }]);
    assert.equal(count('endstart'), 0);
    assert.equal(count('end start'), 1);
  });

  test('a full page of eight has two hot and two smouldering', () => {
    const heats = heatsOf([9, 8, 7, 6, 5, 4, 3, 2]);
    assert.deepEqual(heats, [2, 2, 1, 1, 1, 1, 0, 0]);
  });

  test('a page with one highlight has one hot coal', () => {
    assert.deepEqual(heatsOf([1]), [2]);
  });

  test('ties go to the phrase met first', () => {
    assert.deepEqual(heatsOf([1, 1, 1, 1]), [2, 1, 1, 0]);
  });

  test('a page with no highlights has no heats', () => {
    assert.deepEqual(heatsOf([]), []);
  });

  test('at night every family the API sends reads on graphite, used as sent', () => {
    const families = fromApi('sorted(COALS)');
    assert.ok(families.includes('fire'));
    for (const family of families) {
      const sent = fromApi(`coals_for(${JSON.stringify(family)})`);
      const { ink } = coalsFor(sent, false);
      assert.deepEqual(ink, sent.ink, `${family} is drawn as sent`);
      for (const colour of ink) {
        assert.ok(contrast(colour, GRAPHITE) >= 4.5, `${family} ${colour} ${contrast(colour, GRAPHITE).toFixed(2)}`);
      }
    }
  });

  test('a family the API has no coals for is sent the fire', () => {
    assert.deepEqual(fromApi("coals_for('uncategorised')"), fromApi("coals_for('fire')"));
    assert.deepEqual(fromApi('coals_for(None)'), fromApi("coals_for('fire')"));
  });

  test('a book with no coals (kept offline from before) burns in the same fire as the API', () => {
    assert.deepEqual(coalsFor(undefined, false), coalsFor(fromApi("coals_for('fire')"), false));
  });

  test('by day there is no glow, and the inks are dark enough for paper', () => {
    const { ink, glow } = coalsFor(fromApi("coals_for('business')"), true);
    assert.deepEqual(glow, ['none', 'none', 'none']);
    for (const colour of ink) assert.ok(luminance(colour) <= 0.24 + 1e-3, colour);
  });
});
