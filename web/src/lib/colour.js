// Colour arithmetic: conversion, blending in linear light, and `legible`, which makes a
// colour readable on a register's ground while keeping it a colour. No palettes live here.

export function hex2rgb(h) {
  return [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
}

function rgb2hex(c) {
  return '#' + c.map((v) => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, '0')).join('');
}

function toLinear(v) {
  const s = v / 255;
  return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
}

function toSrgb(v) {
  const s = v <= 0.0031308 ? v * 12.92 : 1.055 * Math.pow(v, 1 / 2.4) - 0.055;
  return Math.max(0, Math.min(1, s)) * 255;
}

export function lum(h) {
  const [r, g, b] = hex2rgb(h).map(toLinear);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

// Blend in linear light, not in sRGB. Averaging gamma-encoded bytes darkens and muddies
// the midpoint of two saturated colours, which is exactly where the resampled stops land.
export function mix(a, b, t) {
  const A = hex2rgb(a).map(toLinear);
  const B = hex2rgb(b).map(toLinear);
  return rgb2hex(A.map((v, i) => toSrgb(v + (B[i] - v) * t)));
}

export function rgb2hsl([r, g, b]) {
  const R = r / 255;
  const G = g / 255;
  const B = b / 255;
  const max = Math.max(R, G, B);
  const min = Math.min(R, G, B);
  const l = (max + min) / 2;
  if (max === min) return [0, 0, l];
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  const h =
    max === R ? ((G - B) / d + (G < B ? 6 : 0)) : max === G ? (B - R) / d + 2 : (R - G) / d + 4;
  return [h / 6, s, l];
}

function hsl2hex(h, s, l) {
  if (s === 0) return rgb2hex([l * 255, l * 255, l * 255]);
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  const p = 2 * l - q;
  const channel = (t) => {
    let x = t;
    if (x < 0) x += 1;
    if (x > 1) x -= 1;
    if (x < 1 / 6) return p + (q - p) * 6 * x;
    if (x < 1 / 2) return q;
    if (x < 2 / 3) return p + (q - p) * (2 / 3 - x) * 6;
    return p;
  };
  return rgb2hex([channel(h + 1 / 3) * 255, channel(h) * 255, channel(h - 1 / 3) * 255]);
}

// How far a band has to clear the ground to be read as a highlight rather than as ink.
//
// Deliberately generous rather than maximal. Against the night ground (#1C1C1C) 0.30
// still measures about 5.7:1, comfortably past WCAG AA, and every point above that is
// paid for by the dark end of the ramp: a floor of 0.46 shoved sunset's deep purples up
// until they landed on their own neighbours, ΔE 2. The floor is a backstop for hues that
// would otherwise vanish, not the thing that sets the palette's brightness.
const NIGHT_MIN_LUM = 0.3;
const DAY_MAX_LUM = 0.24;

// Bands are chosen as a ramp, not for contrast, so several sit too close to the ground
// at one end or the other. Saturation is pushed first so the correction happens in
// chroma before it happens in lightness.
const SATURATION_BOOST = 1.3;
const SATURATION_FLOOR = 0.42;

// Below this a band has no hue worth amplifying — bee's near-black opens at #1A141A, and
// forcing saturation onto it would invent a colour the palette never had.
const NEUTRAL = 0.08;

/**
 * Make one band readable while keeping it a colour.
 *
 * The original mixed toward ink or cream until the luminance cleared, which works for
 * contrast and ruins the palette: blending with off-white pulls every band toward grey,
 * so night highlights arrived as pastels of one another. Hue is held and chroma raised
 * instead, and lightness is supplied by the caller — see `paletteFor`, which sets it
 * from the palette's own spread rather than per colour.
 */
export function legible(hex, day, lightness = null) {
  const [h, s0, l0] = rgb2hsl(hex2rgb(hex));
  const s = s0 > NEUTRAL ? Math.max(Math.min(1, s0 * SATURATION_BOOST), SATURATION_FLOOR) : s0;

  let l = lightness == null ? l0 : lightness;
  let out = hsl2hex(h, s, l);

  // Safety net for a hue whose luminance at that lightness still does not clear the
  // ground: saturated blues run dark and yellows run bright, and neither may vanish.
  let guard = 0;
  while (guard++ < 50) {
    if (day ? lum(out) <= DAY_MAX_LUM : lum(out) >= NIGHT_MIN_LUM) break;
    l += day ? -0.02 : 0.02;
    if (l <= 0.05 || l >= 0.94) break;
    out = hsl2hex(h, s, l);
  }
  return out;
}
