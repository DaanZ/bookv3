// The palettes and the band-order sweep: `paletteFor` samples a palette's ramp to however
// many stops a surface needs and moves each into the register's legible window. It colours
// the progress bar, the shelf, the waiting states and the print sheet; the reading page's
// highlights are coals (coals.js).

import { hex2rgb, legible, mix, rgb2hsl } from './colour.js';

// The five SNCore palettes, in band order: the order `paletteFor` sweeps them in, from
// the first band at one end of a bar to the last at the other.
export const PALETTES = {
  sunset: ['#313575', '#321951', '#633090', '#723466', '#822E37', '#BA5834', '#F68318', '#FDC005'],
  sunrise: ['#0A2F33', '#12564F', '#1F7F76', '#3EA296', '#8A4A12', '#C56A15', '#EF8A1E', '#F7A94A'],
  coral: ['#6C2E7B', '#E75480', '#FF8A5B', '#FFC857', '#1FA7A6', '#0D3B66', '#8B7FD6', '#FFD8C7'],
  bee: ['#1A141A', '#423738', '#67482F', '#8E5915', '#B97515', '#E59312', '#D3AF85', '#F4B315'],
  rainbow: ['#073A4B', '#0C617C', '#108AB1', '#03B1AB', '#06D7A0', '#FFD167', '#F78C6A', '#F04770'],
};

export const PALETTE_NAMES = ['sunset', 'sunrise', 'coral', 'bee', 'rainbow'];

// The lightness window each register gets. Night runs bright on a near-black ground,
// day runs dark on cream; both are ordered dark-stop-first so the palette's own ramp
// direction survives.
const NIGHT_LIGHTNESS = [0.56, 0.86];
const DAY_LIGHTNESS = [0.16, 0.44];

/** The ramp read as a continuous spectrum: t = 0 is the first band, t = 1 the last. */
function sampleRamp(bands, t) {
  const x = Math.max(0, Math.min(1, t)) * (bands.length - 1);
  const i = Math.min(bands.length - 2, Math.floor(x));
  return mix(bands[i], bands[i + 1], x - i);
}

/**
 * `count` colours spanning the whole palette, in band order.
 *
 * It used to take the first `count` bands, so a page with four highlights only ever saw
 * the dark end of the ramp and the palette's character never arrived. The ramp is a
 * gradient, so it is sampled: four highlights take four stops evenly across the whole
 * spectrum, twelve take twelve. Either way the first highlight on the page is the start
 * of the palette and the last is its end.
 */
export function paletteFor(name, day, count) {
  const bands = PALETTES[name] || PALETTES.sunset;
  const n = Math.max(1, Math.round(count) || 1);
  const stops = Array.from({ length: n }, (_, i) => sampleRamp(bands, n === 1 ? 0 : i / (n - 1)));

  // Rescale the palette's own lightness spread into the register's window, rather than
  // handing each stop a lightness by its index. The bands already separate themselves —
  // sunrise's four oranges run 0.30 to 0.63 — and imposing an even ramp threw that away,
  // pushing stops that were distinct on top of each other. A linear remap keeps every
  // gap the palette designed, just moved to where it can be seen.
  const lightnesses = stops.map((hex) => rgb2hsl(hex2rgb(hex))[2]);
  const low = Math.min(...lightnesses);
  const high = Math.max(...lightnesses);
  const [from, to] = day ? DAY_LIGHTNESS : NIGHT_LIGHTNESS;
  const span = high - low;

  return stops.map((hex, i) => {
    // Every stop at the same lightness: nothing to preserve, so sit in the middle and
    // let hue do the separating.
    const t = span < 0.01 ? 0.5 : (lightnesses[i] - low) / span;
    return legible(hex, day, from + (to - from) * t);
  });
}
