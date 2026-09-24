import { money, MONO, thousands } from './format';

/** One model to spend on, with what it would cost for this book. */
export default function ModelChoice({ option, selected, onPick }) {
  const unusable = !option.fits;
  return (
    <button
      type="button"
      onClick={() => onPick(option.id)}
      disabled={unusable}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 14,
        width: '100%',
        padding: '9px 12px',
        borderRadius: 10,
        border: `1px solid ${selected ? 'var(--accent)' : 'var(--border-subtle)'}`,
        background: selected ? 'var(--bg-surface-hover)' : 'transparent',
        cursor: unusable ? 'not-allowed' : 'pointer',
        opacity: unusable ? 0.45 : 1,
        textAlign: 'left',
      }}
    >
      <span style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
        <span style={{ font: `400 12.5px ${MONO}`, color: 'var(--text-primary)' }}>
          {option.id}
        </span>
        <span style={{ font: `400 10.5px ${MONO}`, color: 'var(--text-muted)' }}>
          {unusable
            ? `context ${thousands(option.contextLength)} — too small for the biggest part`
            : `$${option.inputPerMillion.toFixed(2)} in · $${option.outputPerMillion.toFixed(2)} out per 1M`}
          {/* Whether this model has ever produced a highlighted book here. Cheap and
              untried is the combination that wastes a book, so it is said up front
              rather than discovered. */}
          {!unusable && (option.proven ? ' · proven here' : ' · never tried here')}
        </span>
      </span>
      <span
        style={{
          font: `600 13px ${MONO}`,
          color: selected ? 'var(--accent)' : 'var(--text-secondary)',
          whiteSpace: 'nowrap',
        }}
      >
        {money(option.cost)}
      </span>
    </button>
  );
}
