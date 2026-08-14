/**
 * bookv3 ambience — natural beds under the reader.
 *
 * Adapted from the `design_handoff_bookv3_ambience` module, which synthesized all five
 * beds with the Web Audio API. Four real recordings were supplied later, so this keeps
 * the same public contract and the same rules, and only changes where the sound comes
 * from: a bed plays its recording when it has one, and falls back to the original
 * synthesized recipe when it does not.
 *
 * The rules the handoff set, all still enforced here:
 *   · ambience is background, never a signal — it carries no state and no message
 *   · nothing starts — no swells, no arrivals, no loop seams
 *   · 4s fade in, 2s fade out (exit is two thirds of enter)
 *   · every modulation cycle is longer than 8s, so no motion reads as an event
 *   · one master gain, so level, ducking and stop are all the same control
 *   · level caps at 0.5 gain, so a slider at 100% is still a bed, not a soundtrack
 *
 * Usage:
 *   import { Ambience, PROFILES, bedForCategory } from './ambience.js';
 *   const amb = new Ambience();                 // no AudioContext until play()
 *   amb.play(bedForCategory('gardening'));      // must be inside a user gesture
 *   amb.setLevel(0.3);
 *   amb.duck(true);                             // -6dB while a prompt is on screen
 *   amb.stop();
 *
 * Browsers require a user gesture before audio starts: call play() from a click,
 * never on load. play() resumes a suspended context for you.
 */

export const PROFILES = {
  forest: {
    name: 'Forest',
    blurb:
      'Wind through canopy, no birds. Broadband and even; the drift is slow enough that you never catch it moving.',
    categories: ['gardening', 'nature', 'textiles', 'art', 'botan', 'travel'],
    cycle: 90,
    src: '/ambience/forest.mp3',
  },
  river: {
    name: 'River',
    blurb:
      'Moving water over stone. Brighter than the forest and completely steady — the closest thing to white noise that still sounds like a place.',
    categories: ['software', 'startup', 'architect', 'comput', 'program', 'technolog', 'engineer', 'data'],
    cycle: 40,
    src: '/ambience/river.mp3',
  },
  lake: {
    name: 'Lake',
    blurb:
      'Water lapping at a shore, mostly below 250Hz. The quietest bed here — use it when the text is dense.',
    categories: ['spirituality', 'cultural studies', 'history', 'religio', 'buddhis', 'medit'],
    cycle: 60,
  },
  fireplace: {
    name: 'Fireplace',
    blurb:
      'Low rumble with a slow breathing swell, and crackle kept far under the bed. Warm, close, and the only profile with any transient at all.',
    categories: ['self-help', 'philosophy', 'poetry', 'psycholog', 'fiction'],
    cycle: 12,
    src: '/ambience/fireplace.mp3',
  },
  wind: {
    // A sixth bed, added because a wind recording was supplied. Its loop is short, so
    // it leans hardest on the crossfade below; nothing else about it is special.
    name: 'Wind',
    blurb:
      'Open air with nothing in it. The most abstract of the beds — no water, no fire, nothing that suggests a room.',
    categories: ['science', 'physics', 'space', 'astronom', 'math'],
    cycle: 45,
    src: '/ambience/wind.mp3',
  },
  rain: {
    name: 'Rain',
    blurb:
      'Steady rain with the patter kept above speech and a soft body underneath. The most familiar bed, and the easiest to stop noticing.',
    categories: ['marketing', 'business', 'econom', 'manage', 'sales', 'entrepreneur'],
    cycle: 35,
  },
};

export const PROFILE_KEYS = Object.keys(PROFILES);

// "Politically charged material should default to silence — mood music over propaganda
// reads as manipulation; suggest a bed there, never start one." bedForCategory returns
// null for these, and the player shows no preselection rather than picking for you.
const NO_SUGGESTION = ['politic', 'propaganda', 'war', 'genocide', 'extremis', 'terror'];

/**
 * Does this category mention this keyword?
 *
 * A plain substring test is what the handoff used, and it misfires on real categories
 * from the pipeline: "Business/Startup Growth" contains "art" inside "st-art-up", which
 * sent a startup book to the forest. Single-word keywords therefore have to match at a
 * word boundary; multi-word ones ("self-help", "cultural studies") still match loosely,
 * because the pipeline punctuates them inconsistently.
 */
function mentions(category, keyword) {
  if (/[^a-z]/.test(keyword)) return category.includes(keyword);
  return category.split(/[^a-z]+/).some((word) => word.startsWith(keyword));
}

/**
 * Category from the book JSON's meta.category → bed key. Falls back to forest, and
 * returns null where a bed should not be suggested at all.
 */
export function bedForCategory(category = '') {
  const c = String(category).toLowerCase();
  if (NO_SUGGESTION.some((t) => mentions(c, t))) return null;
  for (const [key, p] of Object.entries(PROFILES)) {
    if (p.categories.some((t) => mentions(c, t))) return key;
  }
  return 'forest';
}

const FADE_IN = 4;
const FADE_OUT = 2;
const DUCK_DB = 0.5; // -6dB
const MAX_GAIN = 0.5; // level 1.0 never runs the master hotter than this
const XFADE = 3; // seconds of overlap when a recording loops

/**
 * Per-bed trim, so every bed arrives at the master at the same weight and the level
 * slider means one thing whichever bed is playing.
 *
 * These are measured, not guessed. The supplied recordings are mastered very low —
 * river sits at -50 dBFS RMS — while the synthesized beds run 35-40dB hotter (rain was
 * at -7 dBFS and peaked over 1.0 before this). Left alone, the same slider position is
 * inaudible on one bed and a soundtrack on the next.
 *
 * The common target is a pre-master RMS of ~0.09, which at the 0.5 master cap lands
 * around -27 dBFS at full level: a loud background, never a foreground.
 */
const TRIM = {
  forest: 2.21,
  river: 3.48,
  fireplace: 2.6, // peak-limited by its crackle; lands ~0.7dB under the others
  wind: 2.62,
  lake: 0.54,
  rain: 0.21,
};

export class Ambience {
  constructor({ level = 0.3 } = {}) {
    this.level = level;
    this.bed = null;
    this.playing = false;
    this.ducked = false;
    this._nodes = [];
    this._timers = [];
    this._media = [];
  }

  /* ── plumbing ─────────────────────────────────────────────────────────── */

  _ctx() {
    if (!this.ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      this.ctx = new AC();
      this.master = this.ctx.createGain();
      this.master.gain.value = 0;
      this.master.connect(this.ctx.destination);
    }
    if (this.ctx.state === 'suspended') this.ctx.resume();
    return this.ctx;
  }

  _target() {
    return this.level * MAX_GAIN * (this.ducked ? DUCK_DB : 1);
  }

  _ramp(to, seconds) {
    const t = this.ctx.currentTime;
    this.master.gain.cancelScheduledValues(t);
    this.master.gain.setValueAtTime(Math.max(0.0001, this.master.gain.value), t);
    this.master.gain.linearRampToValueAtTime(Math.max(0.0001, to), t + seconds);
  }

  _noise(seconds = 3) {
    const ctx = this.ctx;
    const buf = ctx.createBuffer(1, Math.floor(ctx.sampleRate * seconds), ctx.sampleRate);
    const d = buf.getChannelData(0);
    // Slightly pink: a one-pole lowpass over white removes the hiss edge.
    let prev = 0;
    for (let i = 0; i < d.length; i++) {
      const white = Math.random() * 2 - 1;
      prev = prev * 0.72 + white * 0.28;
      d[i] = prev * 1.9;
    }
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.loop = true;
    return this._keep(src);
  }

  _keep(node) {
    this._nodes.push(node);
    return node;
  }

  /** Sub-audio LFO onto an AudioParam. period is in SECONDS and must exceed 8. */
  _lfo(param, period, depth, offset = 0) {
    const ctx = this.ctx;
    const osc = this._keep(ctx.createOscillator());
    const amp = this._keep(ctx.createGain());
    osc.frequency.value = 1 / period;
    amp.gain.value = depth;
    if (offset) osc.detune.value = offset;
    osc.connect(amp);
    amp.connect(param);
    osc.start();
    return osc;
  }

  _band(input, type, freq, q, gain, bus) {
    const f = this._keep(this.ctx.createBiquadFilter());
    f.type = type;
    f.frequency.value = freq;
    if (q) f.Q.value = q;
    const g = this._keep(this.ctx.createGain());
    g.gain.value = gain;
    input.connect(f);
    f.connect(g);
    g.connect(bus);
    return { filter: f, gain: g };
  }

  /* ── recorded beds ────────────────────────────────────────────────────── */

  /**
   * A recording, looped without a seam.
   *
   * The files are 10 minutes of 44.1kHz stereo, which decodeAudioData would expand to
   * roughly 200MB of AudioBuffer each — untenable on the tablet this is for. So they
   * stream through a media element instead, and two elements alternate with an
   * equal-power crossfade so the loop point is never audible. That matters most for the
   * wind bed, which is only 22 seconds long and would otherwise seam every 22 seconds.
   */
  _recorded(src, bus) {
    const ctx = this.ctx;

    // The fireplace recording's crackle runs ~35dB over its own bed, which is well
    // past the 12dB the recording contract allows. Compressing the sum lets the bed
    // come up to the same weight as the other beds without the transients clipping,
    // and does nothing audible to the three steady recordings.
    const shaper = this._keep(ctx.createDynamicsCompressor());
    shaper.threshold.value = -38;
    shaper.knee.value = 8;
    shaper.ratio.value = 10;
    shaper.attack.value = 0.002; // fast enough to catch a crackle, not a click
    shaper.release.value = 0.3;
    shaper.connect(bus);

    const lanes = [0, 1].map(() => {
      const el = new Audio();
      el.src = src;
      el.preload = 'auto';
      el.crossOrigin = 'anonymous';
      const node = ctx.createMediaElementSource(el);
      const gain = ctx.createGain();
      gain.gain.value = 0;
      node.connect(gain);
      gain.connect(shaper);
      this._media.push(el);
      this._keep(gain);
      return { el, gain };
    });

    let active = 0;
    let handing = false;

    const fade = (lane, to, seconds) => {
      const t = ctx.currentTime;
      lane.gain.gain.cancelScheduledValues(t);
      lane.gain.gain.setValueAtTime(lane.gain.gain.value, t);
      lane.gain.gain.linearRampToValueAtTime(to, t + seconds);
    };

    const start = (lane) => {
      lane.el.currentTime = 0;
      const attempt = lane.el.play();
      if (attempt && attempt.catch) attempt.catch(() => {});
    };

    // The master fade already covers the entrance, so lane 0 comes up at full weight.
    lanes[0].gain.gain.value = 1;
    start(lanes[0]);

    const watch = () => {
      if (!this.playing) return;
      const current = lanes[active];
      const { duration, currentTime } = current.el;
      if (Number.isFinite(duration) && duration > 0) {
        const overlap = Math.min(XFADE, duration / 4);
        if (!handing && currentTime >= duration - overlap) {
          handing = true;
          const next = lanes[1 - active];
          start(next);
          fade(next, 1, overlap);
          fade(current, 0, overlap);
          active = 1 - active;
          // Release the handover only once the old lane is silent and rewound.
          this._timers.push(
            setTimeout(() => {
              current.el.pause();
              handing = false;
            }, overlap * 1000),
          );
        }
      }
      this._timers.push(setTimeout(watch, 250));
    };
    this._timers.push(setTimeout(watch, 250));
  }

  /* ── the beds ─────────────────────────────────────────────────────────── */

  _build(key, bus) {
    const ctx = this.ctx;
    const profile = PROFILES[key];
    if (!profile) throw new Error('unknown ambience profile: ' + key);

    // A bed with a recording plays it; the rest keep the synthesized recipes below.
    if (profile.src) {
      this._recorded(profile.src, bus);
      return;
    }

    // Wind has no synthesized recipe of its own; the forest bed already *is* wind
    // through canopy, so that is what it falls back to if its file ever goes missing.
    if (key === 'forest' || key === 'wind') {
      const n = this._noise();
      const canopy = this._band(n, 'bandpass', 760, 0.7, 0.9, bus);
      this._band(n, 'lowpass', 300, 0, 0.22, bus); // body under the wind
      this._lfo(canopy.filter.frequency, PROFILES.forest.cycle, 260);
      this._lfo(canopy.gain.gain, 33, 0.12); // breath, not gusts
      n.start();
      return;
    }

    if (key === 'river') {
      const n = this._noise();
      this._band(n, 'bandpass', 420, 0.6, 0.55, bus); // the body of the flow
      const bright = this._band(n, 'bandpass', 1800, 0.5, 0.6, bus);
      this._band(n, 'highpass', 4200, 0, 0.1, bus); // spray
      this._lfo(bright.gain.gain, PROFILES.river.cycle, 0.14);
      n.start();
      return;
    }

    if (key === 'fireplace') {
      const n = this._noise();
      const bed = this._band(n, 'lowpass', 520, 0, 0.8, bus);
      this._lfo(bed.gain.gain, PROFILES.fireplace.cycle, 0.16); // slow breathing
      const rumble = this._keep(ctx.createOscillator());
      const rg = this._keep(ctx.createGain());
      rumble.type = 'sine';
      rumble.frequency.value = 58;
      rg.gain.value = 0.06;
      rumble.connect(rg);
      rg.connect(bus);
      rumble.start();
      n.start();
      // Crackle: short, sparse, and 18dB under the bed. Remove this block if any
      // transient at all is unacceptable — the rest of the profile stands alone.
      const crackle = () => {
        const now = this.ctx.currentTime;
        const c = this.ctx.createOscillator();
        const g = this.ctx.createGain();
        c.type = 'triangle';
        c.frequency.value = 900 + Math.random() * 1600;
        g.gain.setValueAtTime(0.0001, now);
        g.gain.exponentialRampToValueAtTime(0.05, now + 0.004);
        g.gain.exponentialRampToValueAtTime(0.0001, now + 0.05);
        c.connect(g);
        g.connect(bus);
        c.start(now);
        c.stop(now + 0.06);
      };
      const tick = () => {
        if (!this.playing) return;
        crackle();
        this._timers.push(setTimeout(tick, 900 + Math.random() * 2600));
      };
      this._timers.push(setTimeout(tick, 1200));
      return;
    }

    if (key === 'lake') {
      const n = this._noise(4);
      const lap = this._band(n, 'lowpass', 240, 0, 0.85, bus);
      this._lfo(lap.gain.gain, PROFILES.lake.cycle, 0.3); // the swell
      this._lfo(lap.filter.frequency, 47, 60);
      const deep = this._keep(ctx.createOscillator());
      const dg = this._keep(ctx.createGain());
      deep.type = 'sine';
      deep.frequency.value = 108;
      dg.gain.value = 0.035;
      deep.connect(dg);
      dg.connect(bus);
      deep.start();
      n.start();
      return;
    }

    if (key === 'rain') {
      const n = this._noise();
      const patter = this._band(n, 'highpass', 1500, 0, 0.75, bus);
      this._band(n, 'bandpass', 2900, 1.1, 0.35, bus); // drops on glass
      this._band(n, 'lowpass', 220, 0, 0.16, bus); // roof, felt not heard
      this._lfo(patter.gain.gain, PROFILES.rain.cycle, 0.16); // the shower easing off
      n.start();
      return;
    }

    throw new Error('unknown ambience profile: ' + key);
  }

  /* ── controls ─────────────────────────────────────────────────────────── */

  /** Start (or switch to) a bed. Call from a user gesture. */
  play(key = 'forest') {
    this._ctx();
    this._teardown();
    const bus = this._keep(this.ctx.createGain());
    // Per-bed trim lives here, so it applies to recorded and synthesized beds alike
    // and the master stays the single control for level, ducking and stop.
    bus.gain.value = TRIM[key] ?? 1;
    bus.connect(this.master);
    this.playing = true;
    this.bed = key;
    this._build(key, bus);
    this._ramp(this._target(), FADE_IN);
    return this;
  }

  stop() {
    if (!this.ctx) {
      this.playing = false;
      return this;
    }
    this._ramp(0.0001, FADE_OUT);
    this.playing = false;
    this._timers.push(setTimeout(() => this._teardown(), (FADE_OUT + 0.1) * 1000));
    return this;
  }

  toggle(key = this.bed || 'forest') {
    return this.playing ? this.stop() : this.play(key);
  }

  /** 0..1. Takes effect immediately, over 160ms so it never clicks. */
  setLevel(level) {
    this.level = Math.max(0, Math.min(1, level));
    if (this.ctx && this.playing) this._ramp(this._target(), 0.16);
    return this;
  }

  /** -6dB while a resume strip, question or dialog is on screen. */
  duck(on = true) {
    this.ducked = !!on;
    if (this.ctx && this.playing) this._ramp(this._target(), 0.26);
    return this;
  }

  dispose() {
    this.stop();
    if (this.ctx) this.ctx.close();
    this.ctx = null;
  }

  _teardown() {
    this._timers.forEach(clearTimeout);
    this._timers = [];
    this._media.forEach((el) => {
      try {
        el.pause();
        // Drop the request too: a paused element keeps streaming its buffer otherwise.
        el.removeAttribute('src');
        el.load();
      } catch {
        // The element is already gone; nothing to release.
      }
    });
    this._media = [];
    this._nodes.forEach((n) => {
      try {
        if (n.stop) n.stop();
        else n.disconnect();
      } catch {
        // Already stopped or disconnected — teardown must never throw.
      }
    });
    this._nodes = [];
  }
}

// Also expose globally for pages that load this with a plain <script type="module">
// and want it off the window rather than importing it.
if (typeof window !== 'undefined') {
  window.BookvAmbience = { Ambience, PROFILES, PROFILE_KEYS, bedForCategory };
}
