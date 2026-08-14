import { PROFILES, PROFILE_KEYS } from '../lib/ambience';

// The ambience player. Collapsed it is one quiet word in the reader header; open it is
// a panel of beds with the suggested one marked.
//
// Deliberately plain: no icons (the design system ships none, and nominates Lucide only
// as a flagged substitution), and no gold anywhere — in Tide gold is only ever a join,
// and a sound control is not a join. The panel borrows the resume strip's shape without
// its seam.

export default function AmbiencePlayer({ ambience, open, onClose }) {
  if (!open) return null;

  const { bed, level, on, suggested, playBed, stop, setLevel } = ambience;

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 14,
        marginTop: 20,
        padding: '16px 18px',
        borderRadius: 13,
        background: 'var(--bg-surface-hover)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
        <span
          style={{
            font: "600 9.5px 'IBM Plex Mono', monospace",
            letterSpacing: 'var(--track-eyebrow)',
            textTransform: 'uppercase',
            color: 'var(--text-muted)',
          }}
        >
          {on ? `sound · ${PROFILES[bed]?.name.toLowerCase()}` : 'sound · off'}
        </span>
        <button
          type="button"
          className="tap"
          onClick={onClose}
          style={{
            width: 'auto',
            font: "500 12px 'Space Grotesk', system-ui",
            color: 'var(--text-secondary)',
            borderBottom: '1px dotted var(--text-muted)',
            paddingBottom: 2,
          }}
        >
          Close
        </button>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7 }}>
        {PROFILE_KEYS.map((key) => {
          const active = on && bed === key;
          return (
            <button
              key={key}
              type="button"
              className="tap"
              onClick={() => (active ? stop() : playBed(key))}
              title={PROFILES[key].blurb}
              style={{
                width: 'auto',
                padding: '7px 13px',
                borderRadius: 10,
                font: "500 12px 'Space Grotesk', system-ui",
                background: active ? 'var(--accent)' : 'transparent',
                color: active ? 'var(--accent-on)' : 'var(--text-secondary)',
                border: `1px solid ${active ? 'var(--accent)' : 'var(--border-strong)'}`,
              }}
            >
              {PROFILES[key].name}
              {key === suggested && !active ? ' ·' : ''}
            </button>
          );
        })}
        {on && (
          <button
            type="button"
            className="tap"
            onClick={stop}
            style={{
              width: 'auto',
              padding: '7px 13px',
              borderRadius: 10,
              font: "500 12px 'Space Grotesk', system-ui",
              background: 'transparent',
              color: 'var(--text-muted)',
              border: '1px solid var(--border-default)',
            }}
          >
            Off
          </button>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span
          style={{
            font: "400 10.5px 'IBM Plex Mono', monospace",
            color: 'var(--text-muted)',
            whiteSpace: 'nowrap',
          }}
        >
          level {Math.round(level * 100)}%
        </span>
        <input
          type="range"
          min="0"
          max="100"
          value={Math.round(level * 100)}
          onChange={(e) => setLevel(Number(e.target.value) / 100)}
          aria-label="Ambience level"
          style={{ flex: 1, accentColor: 'var(--accent)', cursor: 'pointer' }}
        />
      </div>

      <p
        style={{
          margin: 0,
          maxWidth: '54ch',
          font: "400 12px/1.6 'Space Grotesk', system-ui",
          color: 'var(--text-muted)',
        }}
      >
        {on
          ? PROFILES[bed]?.blurb
          : suggested
            ? `${PROFILES[suggested].name} suits this book. Nothing plays until you pick one.`
            : 'No bed is suggested for this book. Pick one if you want it.'}
      </p>
    </div>
  );
}
