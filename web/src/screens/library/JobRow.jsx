import { Indexing, Summarising } from '../../components/Waiting';
import { Chip, ProgressBar, QuietLink } from '../../components/ui';

import { money, MONO, readableName, STATUS_TONE } from './format';

export default function JobRow({ job, onRemove, onResume, models = [], proven = [], palette, day }) {
  const total = job.chunksTotal;
  // A running job cannot be removed; the worker is still holding the file.
  const settled = job.status === 'done' || job.status === 'failed';

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        padding: '16px 18px',
        borderRadius: 13,
        background: 'var(--bg-surface-hover)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
          <span
            style={{
              fontFamily: 'var(--font-display-wide)',
              fontSize: 15,
              fontWeight: 600,
              color: 'var(--text-primary)',
            }}
          >
            {job.title || readableName(job.filename)}
          </span>
          <span style={{ font: "400 11.5px 'IBM Plex Mono', monospace", color: 'var(--text-muted)' }}>
            {job.author ? `${job.author} · ` : ''}
            {job.pages ? `${job.pages} pages · ` : ''}
            {(job.bytes / 1e6).toFixed(1)} MB
            {job.model ? ` · ${job.model}` : ''}
            {job.estimatedCost != null ? ` · quoted ${money(job.estimatedCost)}` : ''}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Chip tone={STATUS_TONE[job.status] || 'neutral'}>{job.status}</Chip>
          {/* A failed job can always be run again; whether that *resumes* depends on
              whether it got far enough to bank anything. Gating the control on having a
              checkpoint left the jobs that failed earliest — the ones most in need of a
              second go — with no way to start one. */}
          {job.status === 'failed' && (
            <QuietLink
              title={
                job.partsBought > 0
                  ? `Continue from part ${job.partsBought + 1} — the first ${job.partsBought} are already paid for`
                  : 'Run this book again on the same model'
              }
              onClick={() => onResume(job.id)}
            >
              {job.partsBought > 0 ? `Resume from ${job.partsBought + 1}` : 'Run again'}
            </QuietLink>
          )}
          {settled && <QuietLink onClick={() => onRemove(job.id)}>Remove</QuietLink>}
        </div>
      </div>

      {/* Summarising is the long stage — minutes — and gets the composite waiting state
          rather than a bar: there is no honest percentage for a dozen model calls of
          unknown length. Loading pages and reading meta finish fast and get nothing at
          all; the step line below already says what is happening. */}
      {job.status === 'running' && total > 0 && job.step !== 'indexing' && (
        <Summarising
          done={job.chunksDone}
          total={total}
          bounds={job.chunkBounds}
          palette={palette}
          day={day}
        />
      )}

      {job.status === 'running' && job.step === 'indexing' && <Indexing total={total || 0} />}

      {job.status === 'done' && (
        <>
          <ProgressBar pct="100%" fill="var(--shore-400)" />
          <span style={{ font: "400 10.5px 'IBM Plex Mono', monospace", color: 'var(--text-muted)' }}>
            {total || 0} parts written
          </span>
        </>
      )}

      {(job.status === 'queued' || (job.status === 'running' && !total)) && (
        <span style={{ font: "400 10.5px 'IBM Plex Mono', monospace", color: 'var(--text-muted)' }}>
          {job.step || 'waiting'}
        </span>
      )}

      {job.error && (
        <span style={{ font: "400 12px/1.6 'Space Grotesk', system-ui", color: 'var(--chip-expired-fg)' }}>
          {job.error}
        </span>
      )}

      {/* The usual reason a job fails is the model it was given, and the message says so
          — so the alternatives belong here, next to the sentence naming the culprit,
          rather than behind a re-upload. Choosing one drops any parts bought from the old
          model: half a book in one voice and half in another is worse than paying twice. */}
      {job.status === 'failed' && models.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span style={{ font: `400 10.5px ${MONO}`, color: 'var(--text-muted)' }}>
            try again with
          </span>
          {models
            .filter((id) => id !== job.model)
            .map((id) => (
              <button
                key={id}
                type="button"
                className="tap"
                onClick={() => onResume(job.id, id)}
                title={proven.includes(id) ? 'Has produced a highlighted book here' : 'Never tried here'}
                style={{
                  padding: '5px 10px',
                  borderRadius: 8,
                  border: `1px solid ${proven.includes(id) ? 'var(--accent)' : 'var(--border-strong)'}`,
                  background: 'transparent',
                  color: proven.includes(id) ? 'var(--accent)' : 'var(--text-secondary)',
                  font: `400 10.5px ${MONO}`,
                  cursor: 'pointer',
                }}
              >
                {id.split('/')[1] || id}
                {proven.includes(id) ? ' ✓' : ''}
              </button>
            ))}
        </div>
      )}
    </div>
  );
}
