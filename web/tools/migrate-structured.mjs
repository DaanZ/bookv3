// Convert every book from one HTML `body` per part to paragraphs of sentences.
//
//   node web/tools/migrate-structured.mjs           # report what would change, write nothing
//   node web/tools/migrate-structured.mjs --write   # convert, after backing every file up
//
// Why here and not in Python: the conversion has to cut sentences exactly where the reader
// cuts them today, so a book reads the same the moment it is migrated. This calls the
// reader's own `paragraphsOf` instead of porting it. After this, nothing is guessed again:
// new summaries arrive from the model already as sentences (chunks.py).
//
// A part is written as {title, paragraphs: [{heading?, sentences: ["... **mark** ..."]}]}.
// An <h3> becomes the `heading` of the paragraph after it. Every part is checked before it
// is written: the same words in the same order as the reader showed before, and every **
// paired inside its sentence. A part that fails keeps its body and is reported.

import { copyFileSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { normaliseBody, paragraphsOf } from '../src/lib/reading.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const WRITE = process.argv.includes('--write');
const HEADING = '\u0001';

// Marks are removed without leaving a space, on both sides alike: '<b>Website</b>:' and
// '**Website**:' must both count as 'Website:'.
const words = (text) => text.replace(/<\/?b>|\*\*/g, '').replaceAll(HEADING, ' ').split(/\s+/).filter(Boolean);

function sentenceMarkdown(sentence) {
  let text = sentence.replace(/<b>([\s\S]*?)<\/b>/g, '**$1**').replace(/<\/?b>/g, '');
  // A highlight left open by the source (one in the library) is dropped, not guessed at.
  if ((text.match(/\*\*/g) || []).length % 2) text = text.replace(/\*\*/g, '');
  return text.replace(/\s+/g, ' ').trim();
}

export function structure(body) {
  // Mark headings before paragraphsOf turns them into plain paragraphs, so they can be
  // told apart afterwards.
  const marked = (body || '').replace(/<h3\b[^>]*>([\s\S]*?)<\/h3\s*>/gi, `\n\n${HEADING}$1\n\n`);
  const paragraphs = [];
  let pending = null;
  for (const sentences of paragraphsOf(marked)) {
    const first = sentences[0] || '';
    if (sentences.length === 1 && first.startsWith(HEADING)) {
      if (pending) paragraphs.push({ heading: pending, sentences: [] });
      pending = sentenceMarkdown(first.slice(1)).replace(/\*\*/g, '');
      continue;
    }
    const converted = sentences.map(sentenceMarkdown).filter(Boolean);
    paragraphs.push(pending ? { heading: pending, sentences: converted } : { sentences: converted });
    pending = null;
  }
  if (pending) paragraphs.push({ heading: pending, sentences: [] });
  return paragraphs;
}

function check(body, paragraphs) {
  const before = words(normaliseBody(body).replace(/\*\*/g, ''));
  const after = words(paragraphs.flatMap((p) => [p.heading || '', ...p.sentences]).join(' '));
  if (before.join(' ') !== after.join(' ')) return `words differ (${before.length} -> ${after.length})`;
  const unpaired = paragraphs.flatMap((p) => p.sentences).find((s) => (s.match(/\*\*/g) || []).length % 2);
  if (unpaired) return `unpaired ** in "${unpaired.slice(0, 50)}"`;
  return null;
}

// Python's json.dump(indent=4) escapes every non-ASCII character; matching it keeps the
// pipeline's later writes from rewriting every line of a migrated file.
const asJson = (data) =>
  JSON.stringify(data, null, 4).replace(/[\u007f-￿]/g, (c) => `\\u${c.charCodeAt(0).toString(16).padStart(4, '0')}`);

const stamp = new Date().toISOString().replace(/[-:]/g, '').replace('T', '-').slice(0, 15);
const backup = join(ROOT, 'data', 'backups', `migrate-${stamp}`);
const totals = { books: 0, parts: 0, headings: 0, sentences: 0, failed: 0, already: 0 };

for (const shelf of ['available', 'read']) {
  const folder = join(ROOT, 'books', shelf);
  for (const name of readdirSync(folder).filter((n) => n.endsWith('.json'))) {
    const path = join(folder, name);
    const book = JSON.parse(readFileSync(path, 'utf8').replace(/^﻿/, ''));
    let changed = false;
    for (const [index, part] of (book.parts || []).entries()) {
      if (Array.isArray(part.paragraphs)) { totals.already += 1; continue; }
      const paragraphs = structure(part.body);
      const problem = check(part.body, paragraphs);
      if (problem) {
        totals.failed += 1;
        console.log(`  kept body  ${name.slice(0, 55)} part ${index + 1}: ${problem}`);
        continue;
      }
      const { body, ...rest } = part;
      book.parts[index] = { ...rest, paragraphs };
      totals.parts += 1;
      totals.headings += paragraphs.filter((p) => p.heading).length;
      totals.sentences += paragraphs.reduce((n, p) => n + p.sentences.length, 0);
      changed = true;
    }
    if (changed) {
      totals.books += 1;
      if (WRITE) {
        mkdirSync(backup, { recursive: true });
        copyFileSync(path, join(backup, name));
        writeFileSync(path, asJson(book));
      }
    }
  }
}

console.log(`${WRITE ? 'Converted' : 'Would convert'}: ${totals.parts} parts in ${totals.books} books, ` +
  `${totals.sentences} sentences, ${totals.headings} headings; ${totals.failed} kept as body; ${totals.already} already structured.`);
if (WRITE && totals.books) console.log(`Originals saved in ${backup}`);
