// A book's Spiral Dynamics level, as a chip: a dot in the level's colour and the level's
// canonical name beside it, "StriveDrive" for 5 Orange. The dot says the colour and the
// name says the level, so no number or colour word is written; the name is also why
// colour is never the only signal. Graded by spiral.py, sent by the shelf as `book.spiral`;
// the hover gives the number, the colour and the decimal grade.

export const SPIRAL_MEMES = {
  3: 'PowerGods',
  4: 'TruthForce',
  5: 'StriveDrive',
  6: 'HumanBond',
  7: 'FlexFlow',
  8: 'GlobalView',
};

export const SPIRAL_DOTS = {
  3: '#D64541', // Red
  4: '#3D6FD6', // Blue
  5: '#EE8A2E', // Orange
  6: '#3DA35D', // Green
  7: '#E0B93A', // Yellow
  8: '#22B0AC', // Turquoise
};

export default function SpiralPill({ spiral, onAccent = false }) {
  if (!spiral) return null;
  return (
    <span
      // The pill shows the nearest whole level; the decimal grade is kept for the
      // progression from one book to the next and is in the hover text.
      title={`Spiral Dynamics ${spiral.score ?? spiral.level}: level ${spiral.level}, ${spiral.name}, ${spiral.meme} (${spiral.theme}). ${spiral.reason}`}
      style={{
        flex: 'none',
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '4px 9px',
        borderRadius: 4,
        // 10px rather than the chips' 8.5: mixed case is read as a word, not scanned as
        // a label, and needs the size.
        font: "600 10px 'IBM Plex Mono', monospace",
        letterSpacing: '0.01em',
        // Not uppercased like the other chips: the names are written in camel case
        // (StriveDrive), and in capitals the two words run together.
        textTransform: 'none',
        whiteSpace: 'nowrap',
        background: onAccent ? 'rgba(20,32,31,.16)' : 'var(--chip-neutral-bg)',
        color: onAccent ? 'var(--accent-on)' : 'var(--chip-neutral-fg)',
      }}
    >
      <span
        aria-hidden="true"
        style={{
          width: 7,
          height: 7,
          borderRadius: '50%',
          background: SPIRAL_DOTS[spiral.level],
          boxShadow: onAccent ? '0 0 0 1px rgba(20,32,31,.35)' : 'none',
        }}
      />
      {spiral.meme || spiral.name}
    </span>
  );
}
