// Writes every file the Snippers mark appears in, from `src/lib/mark.js`.
//
//   node web/tools/export-mark.mjs
//
// The SVGs are written here. The PNGs and the Windows icon need a rasteriser, and
// there is no dependency-free one in Node, so the SVG sources go to a temporary folder
// and `rasterise-mark.py` (cairosvg + Pillow, both already used by this repo's Python
// side) turns them into pixels.
//
// Which pages a size gets is the design, not a rendering accident: five pages from
// 128px up, one page from 32px, and at 16px and 24px the S alone. A page that reads at
// 512px is a smudge at 16.
//
// Outputs:
//   web/public/assets/favicon.svg           tab icon, one page, on a graphite tile
//   web/public/assets/favicon-maskable.svg  installed app, full-bleed graphite
//   web/public/assets/favicon-{16,32,64,180,512}.png
//   assets/bookv3.ico                       seven sizes, for the taskbar and a shortcut
//   assets/tray-mark.png                    the mark alone, no tile: the tray paints
//                                           its own tile in the colour of its state

import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

import {
  FRONT_GRADIENT,
  FRONT_TRANSFORM,
  GLYPH,
  GLYPH_TRANSFORM,
  PAGES,
  VIEWBOX,
  pageTransform,
} from '../src/lib/mark.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = join(HERE, '..', '..');
const PUBLIC_ASSETS = join(REPO, 'web', 'public', 'assets');

// The night register's surface. The tile is the reading room the mark lives in.
const TILE = '#1C1C1C';

/**
 * One mark as a standalone SVG document.
 *
 * @param pages    which page set
 * @param viewBox  which crop; defaults to the set's own
 * @param tile     'rounded' | 'bleed' | null
 */
function svg(pages, { viewBox = VIEWBOX[pages], tile = 'rounded' } = {}) {
  const [x, y, w, h] = viewBox.split(' ').map(Number);
  const ground =
    tile === 'rounded'
      ? `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${w * 0.22}" fill="${TILE}"/>`
      : tile === 'bleed'
        ? `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${TILE}"/>`
        : '';
  const stops = FRONT_GRADIENT.map(
    (stop) => `<stop offset="${stop.offset}" stop-color="${stop.color}"/>`,
  ).join('');
  const layers = [...PAGES[pages]]
    .reverse()
    .map(
      ([offset, scale, fill, opacity]) =>
        `<g transform="${pageTransform(offset, scale)}"><path d="${GLYPH}" transform="${GLYPH_TRANSFORM}" fill="${fill}" opacity="${opacity}"/></g>`,
    )
    .join('');
  return [
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${viewBox}" width="512" height="512">`,
    `<defs><linearGradient id="front" x1="0" y1="1" x2="0" y2="0">${stops}</linearGradient></defs>`,
    ground,
    layers,
    `<g transform="${FRONT_TRANSFORM}"><path d="${GLYPH}" transform="${GLYPH_TRANSFORM}" fill="url(#front)"/></g>`,
    '</svg>',
    '',
  ].join('\n');
}

writeFileSync(join(PUBLIC_ASSETS, 'favicon.svg'), svg('small'));
writeFileSync(
  join(PUBLIC_ASSETS, 'favicon-maskable.svg'),
  svg('icon', { viewBox: VIEWBOX.maskable, tile: 'bleed' }),
);

const sources = mkdtempSync(join(tmpdir(), 'snippers-mark-'));
writeFileSync(join(sources, 'bare.svg'), svg('bare'));
writeFileSync(join(sources, 'small.svg'), svg('small'));
writeFileSync(join(sources, 'icon.svg'), svg('icon'));
writeFileSync(join(sources, 'tray.svg'), svg('small', { tile: null }));

execFileSync('python', [join(HERE, 'rasterise-mark.py'), sources, REPO], { stdio: 'inherit' });
console.log('mark exported');
