// The three Tide core components the design uses, transcribed from the design system
// bundle (components/core/{Button,Chip,Card}.jsx) so the reader owns no styling of its
// own that the system already defines.

const BUTTON_VARIANTS = {
  primary: {
    background: 'var(--accent)',
    color: 'var(--accent-on)',
    border: '1px solid var(--accent)',
  },
  secondary: {
    background: 'transparent',
    color: 'var(--text-secondary)',
    border: '1px solid var(--border-strong)',
  },
  quiet: {
    background: 'transparent',
    color: 'var(--text-secondary)',
    border: 0,
    borderBottom: '1px dotted var(--text-muted)',
    borderRadius: 0,
    padding: '2px 0',
  },
};

const BUTTON_SIZES = {
  sm: { padding: '7px 12px', fontSize: 12 },
  md: { padding: '11px 16px', fontSize: 13 },
  lg: { padding: '14px 22px', fontSize: 14 },
};

export function Button({
  children,
  variant = 'primary',
  size = 'md',
  disabled = false,
  full = false,
  type = 'button',
  style,
  ...rest
}) {
  const v = BUTTON_VARIANTS[variant] || BUTTON_VARIANTS.primary;
  return (
    <button
      type={type}
      disabled={disabled}
      style={{
        fontFamily: 'var(--font-ui)',
        fontWeight: 500,
        lineHeight: 1.2,
        borderRadius: 'var(--radius-control)',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.4 : 1,
        transition:
          'background var(--dur-quick) var(--ease-move), color var(--dur-quick) var(--ease-move)',
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        width: full ? '100%' : undefined,
        ...BUTTON_SIZES[size],
        ...v,
        ...style,
      }}
      {...rest}
    >
      {children}
    </button>
  );
}

const CHIP_TONES = {
  current: { background: 'var(--chip-current-bg)', color: 'var(--chip-current-fg)' },
  claimed: { background: 'var(--chip-claimed-bg)', color: 'var(--chip-claimed-fg)' },
  seam: { background: 'var(--chip-seam-bg)', color: 'var(--chip-seam-fg)' },
  expired: { background: 'var(--chip-expired-bg)', color: 'var(--chip-expired-fg)' },
  neutral: { background: 'var(--chip-neutral-bg)', color: 'var(--chip-neutral-fg)' },
};

export function Chip({ children, tone = 'neutral', style, ...rest }) {
  return (
    <span
      style={{
        fontFamily: 'var(--font-data)',
        fontWeight: 600,
        fontSize: 'var(--size-chip)',
        letterSpacing: 'var(--track-chip)',
        textTransform: 'uppercase',
        padding: '3px 7px',
        borderRadius: 'var(--radius-physical)',
        whiteSpace: 'nowrap',
        ...(CHIP_TONES[tone] || CHIP_TONES.neutral),
        ...style,
      }}
      {...rest}
    >
      {children}
    </span>
  );
}

const ELEVATION = {
  plinth: { boxShadow: 'none' },
  table: { boxShadow: 'var(--shadow-subtle)' },
  seat: { boxShadow: 'var(--shadow-card)' },
  shelf: { boxShadow: 'var(--shadow-deep)' },
};

export function Card({ children, elevation = 'table', style, ...rest }) {
  return (
    <div
      style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--border-default)',
        // The catch of light on a machined edge.
        borderTopColor: 'var(--border-strong)',
        borderRadius: 'var(--radius-card)',
        display: 'flex',
        flexDirection: 'column',
        ...ELEVATION[elevation],
        ...style,
      }}
      {...rest}
    >
      {children}
    </div>
  );
}

// A 4px track with a fill that transitions its width in 260ms. Used on all three screens.
/**
 * @param gradient  the reading palette's stops. Given them, the bar wears the book's own
 *                  colours instead of a flat accent.
 *
 * The ramp is painted across the **whole track** and the unread part is covered over,
 * rather than the gradient being squeezed into the filled portion. That matters: squeezed,
 * every stop slides leftward as you read, so the bar changes colour under a page you have
 * already finished. Painted across the track, a position keeps its colour for the whole
 * book and reading uncovers more of the ramp — the same idea as the highlights, where the
 * first phrase on a page is the start of the palette and the last is its end.
 */
export function ProgressBar({ pct, fill = 'var(--accent)', gradient = null }) {
  const track = { height: 4, borderRadius: 2, background: 'var(--border-subtle)' };

  if (!gradient || gradient.length < 2) {
    return (
      <div style={track}>
        <div className="fill" style={{ height: 4, width: pct, borderRadius: 2, background: fill }} />
      </div>
    );
  }

  return (
    <div style={{ ...track, position: 'relative', overflow: 'hidden' }}>
      {/* The ramp is laid across the whole track and *clipped* to what has been read.
          It was covered over instead, with `--border-subtle` — which is rgba at .07, so
          the cover was 7% opaque and the full gradient showed straight through it. A book
          nobody had opened wore a finished bar. Clipping removes the pixels rather than
          painting over them, so nothing depends on the track colour being solid. */}
      <div
        className="fill"
        aria-hidden="true"
        style={{
          position: 'absolute',
          inset: 0,
          background: `linear-gradient(90deg, ${gradient.join(', ')})`,
          clipPath: `inset(0 calc(100% - ${pct}) 0 0)`,
        }}
      />
    </div>
  );
}

// A quiet action: 12px, dotted underline, never an accent.
export function QuietLink({ children, ...rest }) {
  return (
    <button
      type="button"
      className="tap"
      style={{
        width: 'auto',
        font: "500 12px 'Space Grotesk', system-ui",
        color: 'var(--text-secondary)',
        borderBottom: '1px dotted var(--text-muted)',
        paddingBottom: 2,
      }}
      {...rest}
    >
      {children}
    </button>
  );
}
