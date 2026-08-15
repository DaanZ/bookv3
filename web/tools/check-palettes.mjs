// Measures what the highlight palettes actually do: contrast against the page ground,
// and how much colour survives the legibility pass.
//
//   node web/tools/check-palettes.mjs
//
// The bands are chosen as a ramp, not for contrast, so `legible()` has to move them.
// This reports whether that move kept them apart and kept them coloured — the previous
// approach (mixing toward cream) cleared contrast while flattening saturation, which is
// why night highlights read as pastels of one another.

import { PALETTES, PALETTE_NAMES, paletteFor } from '../src/lib/reading.js';

// The behaviour this replaced, kept so the change can be measured rather than asserted:
// mix each band toward ink or cream until its luminance clears, and take the first N
// bands rather than sampling the ramp.
const INK_DARK = '#14201F';
const INK_CREAM = '#FDF6EA';

function baseline(name, day, count) {
  const rgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
  const hex = (c) =>
    '#' + c.map((v) => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, '0')).join('');
  const oldMix = (a, b, t) => {
    const A = rgb(a);
    const B = rgb(b);
    return hex(A.map((v, i) => v + (B[i] - v) * t));
  };
  const oldLum = (h) => {
    const [r, g, b] = rgb(h).map((v) => {
      const s = v / 255;
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  return PALETTES[name].slice(0, count).map((h) => {
    let out = h;
    let t = 0;
    while (t < 0.9 && (day ? oldLum(out) > 0.28 : oldLum(out) < 0.42)) {
      t += 0.1;
      out = oldMix(h, day ? INK_DARK : INK_CREAM, t);
    }
    return out;
  });
}

// From web/src/ds/tokens/colors.css.
const NIGHT_BG = '#0B1A1C';
const DAY_BG = '#FDF6EA';

const hex2rgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
const toLinear = (v) => {
  const s = v / 255;
  return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
};
const lum = (h) => {
  const [r, g, b] = hex2rgb(h).map(toLinear);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const contrast = (a, b) => {
  const x = lum(a);
  const y = lum(b);
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
};
const saturation = (h) => {
  const [r, g, b] = hex2rgb(h).map((v) => v / 255);
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  if (max === min) return 0;
  return l > 0.5 ? (max - min) / (2 - max - min) : (max - min) / (max + min);
};

const mean = (xs) => xs.reduce((a, b) => a + b, 0) / xs.length;

// CIE76 ΔE between neighbouring stops. Highlights are only useful if they read as
// different colours, so this is the number that says whether the ramp survived being
// made legible. Under about 10 two stops are hard to tell apart in running text.
function lab(hex) {
  let [r, g, b] = hex2rgb(hex).map(toLinear);
  let x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.9505;
  let y = r * 0.2126 + g * 0.7152 + b * 0.0722;
  let z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.089;
  const f = (v) => (v > 0.008856 ? Math.cbrt(v) : 7.787 * v + 16 / 116);
  [x, y, z] = [f(x), f(y), f(z)];
  return [116 * y - 16, 500 * (x - y), 200 * (y - z)];
}

function deltaE(a, b) {
  const A = lab(a);
  const B = lab(b);
  return Math.hypot(A[0] - B[0], A[1] - B[1], A[2] - B[2]);
}

function adjacent(stops) {
  return stops.slice(1).map((c, i) => deltaE(stops[i], c));
}

for (const day of [false, true]) {
  const ground = day ? DAY_BG : NIGHT_BG;
  console.log(`\n=== ${day ? 'DAY' : 'NIGHT'} on ${ground} ===`);
  for (const name of PALETTE_NAMES) {
    const stops = paletteFor(name, day, 8);
    const contrasts = stops.map((c) => contrast(c, ground));
    const sats = stops.map(saturation);
    const gaps = adjacent(stops);
    const was = baseline(name, day, 8);
    const wasGaps = adjacent(was);
    const wasSats = was.map(saturation);
    const wasContrast = Math.min(...was.map((c) => contrast(c, ground)));
    console.log(
      `${name.padEnd(8)} contrast ${wasContrast.toFixed(1)} → ${Math.min(...contrasts).toFixed(1)}   ` +
        `sat ${mean(wasSats).toFixed(2)} → ${mean(sats).toFixed(2)}   ` +
        `ΔE-min ${Math.min(...wasGaps).toFixed(1)} → ${Math.min(...gaps).toFixed(1)}   ` +
        `ΔE-mean ${mean(wasGaps).toFixed(1)} → ${mean(gaps).toFixed(1)}`,
    );
    console.log(`         was ${was.join(' ')}`);
    console.log(`         now ${stops.join(' ')}`);
  }
}

console.log('\n=== resampling, sunset at night ===');
for (const n of [1, 3, 5, 8, 12]) {
  console.log(`n=${String(n).padStart(2)}  ${paletteFor('sunset', false, n).join(' ')}`);
}
