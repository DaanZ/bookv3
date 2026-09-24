import Spinner from '../../components/Spinner';
import { QuietLink } from '../../components/ui';

import { money, MONO, readableName } from './format';

/**
 * A book that has been read and priced, waiting for a yes.
 *
 * No model picker and no button of its own. Dropping three files used to raise three
 * identical dialogs asking the same question, so the choice moved out to the batch and
 * a row is now what it always should have been: this book, this size, this price.
 */
export default function EstimateRow({ item, model, onCancel }) {
  const { file, estimate } = item;

  if (item.error) {
    return (
      <div style={{ padding: '14px 16px', borderRadius: 13, background: 'var(--chip-expired-bg)' }}>
        <span style={{ font: "400 12.5px/1.6 'Space Grotesk', system-ui", color: 'var(--chip-expired-fg)' }}>
          {readableName(file.name)}: {item.error}
        </span>
        <div style={{ marginTop: 8 }}>
          <QuietLink onClick={() => onCancel(item.id)}>Dismiss</QuietLink>
        </div>
      </div>
    );
  }

  if (!estimate) {
    // Reading a 20MB PDF and counting its tokens takes a few seconds. The Spinner keeps
    // its own 400ms threshold, so a small file that measures instantly shows nothing.
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 13,
          padding: '14px 16px',
          borderRadius: 13,
          background: 'var(--bg-surface-hover)',
        }}
      >
        <Spinner variant="mark" size={22} />
        <span style={{ font: `400 12px ${MONO}`, color: 'var(--text-muted)' }}>
          {readableName(file.name)} · reading and measuring…
        </span>
      </div>
    );
  }

  const chosen = estimate.options.find((o) => o.id === model);

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        padding: '14px 16px',
        borderRadius: 13,
        background: 'var(--bg-surface-hover)',
      }}
    >
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
        <span
          style={{
            fontFamily: 'var(--font-display-wide)',
            fontSize: 14.5,
            fontWeight: 600,
            color: 'var(--text-primary)',
          }}
        >
          {readableName(file.name)}
        </span>
        <span style={{ font: `400 11px ${MONO}`, color: 'var(--text-muted)' }}>
          {estimate.pages} pages · {estimate.chunks} parts
          {estimate.emptyPages > 0 ? ` · ${estimate.emptyPages} pages with no text` : ''}
        </span>
      </div>
      <span style={{ font: `600 13px ${MONO}`, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
        {money(chosen?.cost)}
      </span>
      <QuietLink onClick={() => onCancel(item.id)}>Remove</QuietLink>
    </div>
  );
}
