import { useEffect, useId, useRef, useState } from 'react';
import { PALETTES } from '../lib/reading';

// The mark put to work, ported from the "Wachten" view of the Fox orange logo animation
// handoff (`Logo Animation.dc.html`) and the design system's own `_sncore/logo/eye-loader`.
//
// What replaced what: the old wait state traced the hexagon's outline with a travelling
// dash. That never actually ran — `@keyframes rim-run` is defined in the token layer but
// no rule ever bound it to the class, so the dash sat frozen at one position and the
// "animation" was a still picture. The handoff supersedes it anyway.
//
// The mark is now eight nested hexagon plates and a core, and the motion is the core
// looking around: every 2.6 seconds it picks a new point, travels there on an eased
// curve, and each plate chases it — further out means less travel and more lag, so the
// stack moves like something alive rather than something spinning. The outermost plate
// does not move at all, which is what keeps the silhouette still.
//
// Four rules come with it, and no caller should have to remember any of them:
//
// * **Nothing under 400ms.** A spinner that flashes reads as a fault.
// * **Nothing under 46px.** Below that the rings cannot resolve and the mark collapses
//   into one dark disc, so the wait state is text alone — the element refuses to draw
//   what it cannot draw properly. Both small call sites already say what they are doing.
// * **The mark is never rotated.** It is a face. The motion is the core's gaze.
// * **Reduced motion falls back to the mark at rest**, not to nothing.

const LAYERS = 8;
const LOADER_RADIUS = 11.6;
const CORE = 2.3;

// The core's step. 2.6s is the wait state's own tempo — faster than the idle mark's nine
// seconds, because a wait is work the reader caused and is watching.
const PERIOD = 2600;
const REACH = 2.5;

// Below this the rings stop resolving. The number is the design system's, not a guess.
const MIN_PX = 46;

const SEAM_HEX = 'M12 .9 L22.2 6.6 V17.4 L12 23.1 L1.8 17.4 V6.6 Z';
const SEAM_MARK = 'M12 19.5 L5.7 12.8 L5.7 6.1 L10.4 9.7 L13.6 9.7 L18.3 6.1 L18.3 12.8 Z';

// A pointy-top hexagon of radius r, centred in the 24 box.
const hexPath = (r) => {
  const points = Array.from({ length: 6 }, (_, k) => {
    const a = ((-90 + k * 60) * Math.PI) / 180;
    return `${(12 + r * Math.cos(a)).toFixed(3)},${(12 + r * Math.sin(a)).toFixed(3)}`;
  });
  return `M${points.join(' L')} Z`;
};

// Radii from the rim inward, ending just outside the core.
const ringRadius = (i, n, outer, core) => outer - (outer - core - 0.4) * (i / n);

const prefersStill = () =>
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/**
 * The gaze. `pos[0..7]` are the plates outside-in, `pos[8]` is the core.
 *
 * Each one approaches the target from wherever it currently is, per frame, rather than
 * transitioning to it — so a new target picked up mid-move continues from the position
 * reached instead of restarting from a standstill. `lead` is how far a plate is willing
 * to travel and `k` how hard it is pulled; both rise inward, which is what makes the lag.
 */
function useGaze(active) {
  const pos = useRef(Array.from({ length: LAYERS + 1 }, () => ({ x: 0, y: 0 })));
  const leg = useRef({ from: { x: 0, y: 0 }, to: { x: 0, y: 0 }, start: 0, dur: 1 });
  const [, tick] = useState(0);

  useEffect(() => {
    if (!active) return undefined;

    // Where the core is being asked to be this frame: eased in and out, so the gaze
    // leaves and arrives at rest instead of snapping to a new heading.
    const target = () => {
      const { from, to, start, dur } = leg.current;
      const t = Math.min(1, (performance.now() - start) / dur);
      const s = t < 0.5 ? 2 * t * t : 1 - 2 * (1 - t) * (1 - t);
      return { x: from.x + (to.x - from.x) * s, y: from.y + (to.y - from.y) * s };
    };

    const look = () => {
      const angle = Math.random() * Math.PI * 2;
      const reach = REACH * (0.35 + Math.random() * 0.65);
      leg.current = {
        from: target(),
        to: { x: Math.cos(angle) * reach, y: Math.sin(angle) * reach },
        start: performance.now(),
        dur: PERIOD * 0.72,
      };
    };

    let frame = null;
    const chase = () => {
      const { x, y } = target();
      let moved = false;
      for (let i = 0; i <= LAYERS; i += 1) {
        const lead = i === LAYERS ? 1 : 0.82 * (i / (LAYERS - 1));
        const k = i === LAYERS ? 0.2 : 0.045 + 0.155 * (i / (LAYERS - 1));
        const tx = x * lead;
        const ty = y * lead;
        const p = pos.current[i];
        p.x += (tx - p.x) * k;
        p.y += (ty - p.y) * k;
        if (Math.abs(tx - p.x) > 0.003 || Math.abs(ty - p.y) > 0.003) moved = true;
      }
      if (moved) tick((n) => n + 1);
      frame = requestAnimationFrame(chase);
    };

    look();
    const timer = setInterval(look, PERIOD);
    frame = requestAnimationFrame(chase);
    return () => {
      clearInterval(timer);
      cancelAnimationFrame(frame);
    };
  }, [active]);

  return pos.current;
}

/**
 * @param variant 'mark' — the default, for any wait. 'seam' — only when two sources are
 *                being reconciled; gold means a join, and spending it on ordinary
 *                processing destroys what it means.
 * @param delay   ms before anything is shown. 400 is the system threshold; 0 opts out.
 * @param palette which ramp the plates take. The five are the reader's own.
 * @param label   visible caption. Without one, a screen-reader-only label is emitted.
 */
export default function Spinner({
  variant = 'mark',
  size,
  label,
  delay = 400,
  palette = 'sunrise',
  style,
  ...rest
}) {
  const [shown, setShown] = useState(delay === 0);
  useEffect(() => {
    if (delay === 0) return undefined;
    const timer = setTimeout(() => setShown(true), delay);
    return () => clearTimeout(timer);
  }, [delay]);

  const clipId = useId();
  const px = size || (variant === 'seam' ? 68 : 76);
  const still = prefersStill();
  const drawable = variant === 'seam' || px >= MIN_PX;
  const pos = useGaze(shown && drawable && variant !== 'seam' && !still);

  if (!shown) return null;

  const bands = PALETTES[palette] || PALETTES.sunrise;
  // Pale outside is the mark's own rule: the iris lightens outward, and the core is the
  // darkest single area on it.
  const fillOf = (i) => bands[bands.length - 1 - i] || bands[0];

  const plates = Array.from({ length: LAYERS }, (_, i) => ({
    i,
    d: hexPath(ringRadius(i, LAYERS, LOADER_RADIUS, CORE)),
  }));
  const coreD = hexPath(CORE);

  const plate = (d, key, fill, p, turn, z) => (
    <g
      key={key}
      style={{
        transform: `translate3d(${p.x.toFixed(3)}px, ${p.y.toFixed(3)}px, ${z}px) rotateX(${(
          -p.y * turn
        ).toFixed(2)}deg) rotateY(${(p.x * turn).toFixed(2)}deg)`,
        transformOrigin: '12px 12px',
        transformStyle: 'preserve-3d',
      }}
    >
      <path d={d} fill={fill} strokeLinejoin="round" />
      {/* The clipped fall at the upper left. Light comes from there, so each plate drops
          a hairline of its own shadow onto itself and never past its own edge. */}
      <path
        d={d}
        fill="none"
        stroke="#14201F"
        strokeWidth="1.1"
        strokeLinejoin="round"
        opacity="0.24"
        transform="translate(-0.22,-0.3)"
        clipPath={`url(#${clipId}-${key})`}
        style={{ filter: 'blur(0.55px)' }}
      />
    </g>
  );

  const art =
    variant === 'seam' ? (
      <>
        <defs>
          <clipPath id={`${clipId}-seam`}>
            <path d={SEAM_MARK} />
          </clipPath>
        </defs>
        <path d={SEAM_HEX} fill="none" stroke="#C9922E" strokeWidth="1.1" strokeLinejoin="round" />
        <path d={SEAM_MARK} fill="rgba(201,146,46,.22)" />
        {/* Gold is drawn, never faded in: the sweep travels the mark rather than
            appearing on it. */}
        <g clipPath={`url(#${clipId}-seam)`}>
          <rect className="seam-sweep" x="4" y="12" width="16" height="1.5" fill="#F6D894" />
        </g>
      </>
    ) : (
      <>
        <defs>
          {plates.map(({ i, d }) => (
            <clipPath key={i} id={`${clipId}-${i}`}>
              <path d={d} />
            </clipPath>
          ))}
          <clipPath id={`${clipId}-core`}>
            <path d={coreD} />
          </clipPath>
        </defs>
        {plates.map(({ i, d }) =>
          plate(d, i, fillOf(i), pos[i], 3.4 * (0.35 + 0.65 * (i / (LAYERS - 1))), (i * 0.22).toFixed(2)),
        )}
        {plate(coreD, 'core', bands[0], pos[LAYERS], 5.2, 3.4)}
      </>
    );

  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        display: 'inline-flex',
        flexDirection: label ? 'column' : 'row',
        alignItems: 'center',
        gap: 14,
        ...style,
      }}
      {...rest}
    >
      {drawable && (
        <svg
          width={px}
          height={px}
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden="true"
          style={{ display: 'block', perspective: '320px', transformStyle: 'preserve-3d' }}
        >
          {art}
        </svg>
      )}
      {label ? (
        <span
          style={{
            fontFamily: 'var(--font-display-wide)',
            fontSize: 15,
            color: 'var(--text-primary)',
            textAlign: 'center',
          }}
        >
          {label}
        </span>
      ) : (
        <span
          style={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden', clip: 'rect(0 0 0 0)' }}
        >
          Working
        </span>
      )}
    </div>
  );
}
