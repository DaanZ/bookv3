import { useEffect, useId, useState } from 'react';

// The design system's Spinner, ported from the compiled bundle in the mark-and-waiting
// handoff. This project vendors the token layer but not the components, so it is a port
// rather than an import — the geometry, the timings and the delay are the system's, and
// none of them should be re-derived here.
//
// Two rules it owns, so no caller has to remember them:
//
// * **Nothing under 400ms.** A spinner that flashes reads as a fault, so it renders null
//   until the threshold passes. Every waiting state in the app inherits that by using it.
// * **The mark is never rotated.** It is a face; a spinning face reads as a toy. The rim
//   travels the hexagon outline by `stroke-dashoffset`, so it turns each of the six
//   corners instead of sweeping a circle.

// The hexagon, and the mark that sits inside it. Both on a 24 grid.
const HEX = 'M12 .9 L22.2 6.6 V17.4 L12 23.1 L1.8 17.4 V6.6 Z';
const MARK = 'M12 19.5 L5.7 12.8 L5.7 6.1 L10.4 9.7 L13.6 9.7 L18.3 6.1 L18.3 12.8 Z';

const BRASS = '#C9922E';

/**
 * @param variant 'rim' — the default, for any wait. 'seam' — only when two sources are
 *                being reconciled; gold means a join, and spending it on ordinary
 *                processing destroys what it means.
 * @param delay   ms before anything is shown. 400 is the system threshold; 0 opts out.
 * @param label   visible caption. Without one, a screen-reader-only label is emitted.
 */
export default function Spinner({
  variant = 'rim',
  size,
  label,
  delay = 400,
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
  const px = size || (variant === 'rim' ? 24 : 76);

  if (!shown) return null;

  const art =
    variant === 'seam' ? (
      <>
        <defs>
          <clipPath id={clipId}>
            <path d={MARK} />
          </clipPath>
        </defs>
        <path d={HEX} fill="none" stroke={BRASS} strokeWidth="1.1" strokeLinejoin="round" />
        <path d={MARK} fill="rgba(201,146,46,.22)" />
        {/* Gold is drawn, never faded in: the sweep travels the mark rather than
            appearing on it. */}
        <g clipPath={`url(#${clipId})`}>
          <rect className="seam-sweep" x="4" y="12" width="16" height="1.5" fill="#F6D894" />
        </g>
      </>
    ) : (
      <>
        {/* The mark traces its own outline: a dash travels the hexagon by
            `stroke-dashoffset`, so it turns each of the six corners and the shape stays
            a hexagon. Nothing rotates. Spinning the whole thing was a mistake — it makes
            the corners meaningless and reads as a generic loader stuck behind a logo. */}
        <path d={HEX} fill="none" stroke="rgba(201,146,46,.2)" strokeWidth="1.1" strokeLinejoin="round" />
        <path
          className="rim-run"
          d={HEX}
          pathLength="100"
          fill="none"
          stroke={BRASS}
          strokeWidth="1.4"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray="26 74"
        />
        <path d={MARK} fill={BRASS} opacity=".9" />
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
      <svg width={px} height={px} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        {art}
      </svg>
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
