// The reading model is the part of this app most worth protecting: it decides how far
// through a book you are, how a part breaks into pages, and which phrase takes which
// colour. All of it is pure, so it can be tested without a browser.
//
//   node --test web/src/
//
// These assert the *rules from the design*, not the current arithmetic. Where a number
// is an implementation choice it is checked as a property (sums to 1, never decreases)
// rather than pinned to a literal, so the model can be retuned without rewriting tests.

import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  MAX_PAGES_PER_PART,
  PALETTES,
  PALETTE_NAMES,
  cum,
  frontCount,
  highlightCount,
  legible,
  newBudget,
  normaliseBody,
  paginate,
  paletteFor,
  progressOf,
  tokensOf,
  weights,
} from './reading.js';

const SIZES = [2, 3, 4, 5, 6, 7, 10, 12, 21, 40];
const near = (a, b, tol = 1e-9) => Math.abs(a - b) <= tol;

describe('weights', () => {
  it('gives every book a bar that adds up to exactly one', () => {
    for (const n of SIZES) {
      const total = weights(n).reduce((a, b) => a + b, 0);
      assert.ok(near(total, 1, 1e-9), `${n} parts summed to ${total}`);
    }
  });

  it('gives the introduction no weight, because it sets up the book', () => {
    for (const n of SIZES) assert.equal(weights(n)[0], 0, `${n} parts`);
  });

  it('never hands out a negative share, so the bar cannot go backwards', () => {
    for (const n of SIZES) {
      for (const w of weights(n)) assert.ok(w >= 0, `${n} parts produced ${w}`);
    }
  });

  it('handles the degenerate books', () => {
    assert.deepEqual(weights(0), []);
    assert.deepEqual(weights(1), [1]);
  });

  it('puts 80% of the bar in the first third of the content', () => {
    // The curve is fitted so that 80% lands exactly one third of the way through the
    // content parts — a fractional point. Parts are whole, so the discrete statement is
    // that the bar has cleared 80% by the time that third is finished, and had not
    // cleared it the part before.
    for (const n of SIZES.filter((s) => s >= 4)) {
      const span = n - 1; // content parts; part 1 is the introduction
      const third = span / 3;
      const done = cum(n, 1 + Math.ceil(third));
      assert.ok(done >= 0.8 - 1e-9, `${n} parts: only ${(done * 100).toFixed(1)}% by part ${1 + Math.ceil(third)}`);

      // Not overshooting: a whole part earlier, it is still short of the mark.
      if (Math.floor(third) >= 1 && !Number.isInteger(third)) {
        const before = cum(n, 1 + Math.floor(third));
        assert.ok(before < 0.8, `${n} parts: already ${(before * 100).toFixed(1)}% too early`);
      }
    }
  });

  it('is front-loaded: the earliest content part outweighs the last', () => {
    for (const n of SIZES.filter((s) => s >= 3)) {
      const w = weights(n);
      assert.ok(w[1] > w[n - 1], `${n} parts: ${w[1]} vs ${w[n - 1]}`);
    }
  });
});

describe('cum', () => {
  it('starts at nothing and ends at everything', () => {
    for (const n of SIZES) {
      assert.equal(cum(n, 0), 0);
      assert.ok(near(cum(n, n), 1), `${n} parts ended at ${cum(n, n)}`);
    }
  });

  it('never decreases as parts are read', () => {
    for (const n of SIZES) {
      for (let i = 1; i <= n; i += 1) {
        assert.ok(cum(n, i) >= cum(n, i - 1), `${n} parts fell back at ${i}`);
      }
    }
  });
});

describe('frontCount', () => {
  it('names a real part number', () => {
    for (const n of SIZES) {
      const front = frontCount(n);
      assert.ok(front >= 1 && front <= n, `${n} parts reported ${front}`);
    }
  });

  it('names the part by which the bar has actually reached 80%', () => {
    // The reader is told "the first N parts carry 80% of the bar". That sentence has to
    // be true, or the bar is explaining itself with a number it does not honour.
    for (const n of SIZES.filter((s) => s >= 3)) {
      assert.ok(cum(n, frontCount(n)) >= 0.8 - 1e-9, `${n} parts`);
      assert.ok(cum(n, frontCount(n) - 1) < 0.8, `${n} parts overshot`);
    }
  });
});

describe('progressOf', () => {
  it('is zero on the first page of the first part', () => {
    assert.equal(progressOf(7, 0, 0, 3), 0);
  });

  it('never reaches 100%: that belongs to the finish screen alone', () => {
    for (const n of SIZES) {
      const pages = 3;
      const last = progressOf(n, n - 1, pages - 1, pages);
      assert.ok(last < 1, `${n} parts reached ${last} on the last page`);
    }
  });

  it('counts the page you are on as in progress, not read', () => {
    // pageIndex, not pageIndex + 1. Opening a part must not advance the bar.
    const atOpen = progressOf(6, 2, 0, 4);
    assert.equal(atOpen, cum(6, 2));
  });

  it('only ever moves forward as you read', () => {
    const parts = 9;
    const pages = 3;
    let previous = -1;
    for (let part = 0; part < parts; part += 1) {
      for (let page = 0; page < pages; page += 1) {
        const now = progressOf(parts, part, page, pages);
        assert.ok(now >= previous, `went backwards at part ${part} page ${page}`);
        previous = now;
      }
    }
  });

  it('survives a book with no parts', () => {
    assert.equal(progressOf(0, 0, 0, 0), 0);
  });
});

describe('paginate', () => {
  const sentence = (i) => `This is sentence number ${i} and it says something.`;
  const body = (count) => Array.from({ length: count }, (_, i) => sentence(i)).join(' ');

  it('puts two sentences in a paragraph and two paragraphs on a page', () => {
    const pages = paginate(body(8));
    assert.equal(pages.length, 2);
    assert.equal(pages[0].length, 2);
    assert.ok(pages[0][0].includes('number 0') && pages[0][0].includes('number 1'));
  });

  it('never gives a part more pages than the cap, however long it is', () => {
    for (const count of [40, 80, 200, 500]) {
      const pages = paginate(body(count));
      assert.ok(
        pages.length <= MAX_PAGES_PER_PART,
        `${count} sentences produced ${pages.length} pages`,
      );
    }
  });

  it('keeps every sentence when a long part is compressed', () => {
    const pages = paginate(body(120));
    const text = pages.flat().join(' ');
    for (const i of [0, 47, 119]) {
      assert.ok(text.includes(`number ${i} `), `lost sentence ${i}`);
    }
  });

  it('respects paragraph breaks in the source', () => {
    const pages = paginate('One. Two.\n\nThree. Four.');
    // The blank line ends a paragraph, so "Two." and "Three." never share one.
    const joined = pages.flat();
    assert.ok(!joined.some((p) => p.includes('Two.') && p.includes('Three.')));
  });

  it('always returns at least one page, even for nothing', () => {
    assert.equal(paginate('').length, 1);
    assert.equal(paginate(undefined).length, 1);
  });
});

describe('normaliseBody', () => {
  it("drops the pipeline's baked-in forest green but keeps the boundary", () => {
    const out = normaliseBody("<b style='color: forestgreen;'>leads</b> and more");
    assert.equal(out, '<b>leads</b> and more');
  });

  it('keeps the text of other tags and throws the tags away', () => {
    assert.equal(normaliseBody('<h3>Title</h3> and <em>stress</em>'), 'Title and stress');
  });

  it('is not fooled by an uppercase or spaced closing tag', () => {
    assert.equal(normaliseBody('<B>x</B >'), '<b>x</b>');
  });

  it('survives an empty body', () => {
    assert.equal(normaliseBody(''), '');
    assert.equal(normaliseBody(null), '');
  });
});

describe('tokensOf', () => {
  const palette = ['#111111', '#222222', '#333333'];

  it('marks a highlighted phrase and leaves the rest as body text', () => {
    const tokens = tokensOf('a <b>bee</b> c', palette, 8, newBudget());
    assert.deepEqual(
      tokens.map((t) => [t.text, t.weight]),
      [
        ['a ', 400],
        ['bee', 600],
        [' c', 400],
      ],
    );
  });

  it('gives the same phrase the same colour twice on a page', () => {
    const budget = newBudget();
    const first = tokensOf('<b>ocean</b>', palette, 8, budget);
    const second = tokensOf('<b>Ocean.</b>', palette, 8, budget);
    assert.equal(first[0].color, second[0].color);
  });

  it('hands colours out in reading order', () => {
    const tokens = tokensOf('<b>one</b> <b>two</b>', palette, 8, newBudget());
    const marked = tokens.filter((t) => t.weight === 600);
    assert.equal(marked[0].color, palette[0]);
    assert.equal(marked[1].color, palette[1]);
  });

  it('spends the cap on instances, not distinct phrases, then stops marking', () => {
    const budget = newBudget();
    const tokens = tokensOf('<b>a</b> <b>a</b> <b>b</b>', palette, 2, budget);
    const marked = tokens.filter((t) => t.weight === 600);
    // Two instances of "a" spend the whole budget; "b" renders plain.
    assert.equal(marked.length, 2);
    assert.equal(budget.used, 2);
    const plainB = tokens.find((t) => t.text === 'b');
    assert.equal(plainB.weight, 400);
  });

  it('holds the cap across every sentence on the page, not per sentence', () => {
    const budget = newBudget();
    let marked = 0;
    for (const s of ['<b>p</b>', '<b>q</b>', '<b>r</b>', '<b>s</b>']) {
      marked += tokensOf(s, palette, 2, budget).filter((t) => t.weight === 600).length;
    }
    assert.equal(marked, 2);
  });

  it('drops a closing tag stranded by a sentence split', () => {
    // "...ends here.</b> Next" — the orphan must not print as literal text.
    const tokens = tokensOf('</b> Next sentence', palette, 8, newBudget());
    assert.ok(!tokens.some((t) => t.text.includes('</b>')));
    assert.equal(tokens.map((t) => t.text).join(''), ' Next sentence');
  });

  it('never loses a character of the reader’s text', () => {
    const text = 'Before <b>middle</b> after.';
    const tokens = tokensOf(text, palette, 8, newBudget());
    assert.equal(tokens.map((t) => t.text).join(''), 'Before middle after.');
  });
});

describe('highlightCount', () => {
  it('agrees exactly with what tokensOf will colour', () => {
    // The palette is built to this number. One too high shortens the sweep; one too low
    // reads palette[n] as undefined and prints a highlight in body ink.
    const cases = [
      [['<b>a</b> <b>b</b> <b>c</b>'], 8],
      [['<b>a</b> <b>a</b> <b>b</b>'], 8],
      [['<b>a</b>', '<b>b</b>', '<b>c</b>', '<b>d</b>'], 3],
      [['no marks here'], 8],
      [[], 8],
    ];
    for (const [sentences, cap] of cases) {
      const budget = newBudget();
      for (const s of sentences) tokensOf(s, [], cap, budget);
      assert.equal(highlightCount(sentences, cap), budget.map.size, JSON.stringify(sentences));
    }
  });

  it('never promises more colours than the cap allows', () => {
    const sentences = Array.from({ length: 30 }, (_, i) => `<b>w${i}</b>`);
    for (const cap of [1, 3, 8]) {
      assert.ok(highlightCount(sentences, cap) <= cap, `cap ${cap}`);
    }
  });
});

describe('paletteFor', () => {
  const hex = /^#[0-9a-f]{6}$/i;

  it('returns exactly as many colours as the page asked for', () => {
    for (const name of PALETTE_NAMES) {
      for (const count of [1, 2, 4, 8, 12]) {
        for (const day of [true, false]) {
          const stops = paletteFor(name, day, count);
          assert.equal(stops.length, count, `${name} ${count} ${day ? 'day' : 'night'}`);
          for (const stop of stops) assert.match(stop, hex);
        }
      }
    }
  });

  it('spans the whole ramp rather than only its dark end', () => {
    // Taking the first N bands meant a four-highlight page never saw the palette's
    // character. The stops are sampled across the spectrum instead.
    const four = paletteFor('rainbow', false, 4);
    const distinct = new Set(four);
    assert.equal(distinct.size, 4, 'stops collapsed onto each other');
  });

  it('falls back to a real palette when handed a name it does not know', () => {
    const stops = paletteFor('not-a-palette', false, 3);
    assert.equal(stops.length, 3);
    for (const stop of stops) assert.match(stop, hex);
  });

  it('copes with a count of one', () => {
    assert.equal(paletteFor('sunset', true, 1).length, 1);
  });
});

describe('legible', () => {
  const luminance = (h) => {
    const [r, g, b] = [1, 3, 5]
      .map((i) => parseInt(h.slice(i, i + 2), 16) / 255)
      .map((s) => (s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4)));
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };

  it('brings every band clear of the ground it sits on', () => {
    for (const name of PALETTE_NAMES) {
      for (const band of PALETTES[name]) {
        assert.ok(luminance(legible(band, false)) >= 0.28, `${name} ${band} on night`);
        assert.ok(luminance(legible(band, true)) <= 0.26, `${name} ${band} on day`);
      }
    }
  });

  it('always answers with a colour', () => {
    for (const name of PALETTE_NAMES) {
      for (const band of PALETTES[name]) {
        assert.match(legible(band, true), /^#[0-9a-f]{6}$/i);
      }
    }
  });
});
