// How many pages each part of a real book comes out at.
//
//   node web/tools/check-pagination.mjs books/available/Flow.json
//
// The cap is on pages, not on page length, so the thing to watch here is the right-hand
// column: how much text a page carries once a long part is compressed to fit.

import { readFileSync } from 'node:fs';

import { MAX_PAGES_PER_PART, paginate, normaliseBody } from '../src/lib/reading.js';

const book = JSON.parse(readFileSync(process.argv[2], 'utf8'));

console.log(`${book.meta?.title ?? process.argv[2]} — cap ${MAX_PAGES_PER_PART} pages/part\n`);
console.log('part  pages  paras/page  chars/page (max)');

let worst = 0;
let over = 0;
for (const [i, part] of (book.parts || []).entries()) {
  const pages = paginate(part.body);
  const perPage = Math.max(...pages.map((p) => p.length));
  const chars = Math.max(...pages.map((p) => normaliseBody(p.join(' ')).length));
  worst = Math.max(worst, chars);
  if (pages.length > MAX_PAGES_PER_PART) over += 1;
  console.log(
    `${String(i + 1).padStart(4)}  ${String(pages.length).padStart(5)}  ` +
      `${String(perPage).padStart(10)}  ${String(chars).padStart(9)}`,
  );
}

console.log(`\nparts over the cap: ${over}`);
console.log(`densest page: ${worst} characters`);
