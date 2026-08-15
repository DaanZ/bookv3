import { useState } from 'react';

import { Button, Chip, QuietLink } from '../components/ui';

// Who is reading.
//
// This screen has no design file either, and unlike the library it is not an overview —
// it is one unit of work, the reader's own rule, so it is built like the shelf: a
// column of rows you choose between, and one thing to do at the bottom.
//
// A profile is a tone and a name. No password: this is a tablet in a house, and asking
// who is holding it is the whole of it. The tone does the work the category patch does
// on the shelf — you know which row is yours before you read the name.

function Tone({ profile, size = 44 }) {
  return (
    <div
      aria-hidden="true"
      style={{
        flex: 'none',
        width: size,
        height: size,
        borderRadius: 'var(--radius-physical)',
        background: profile.tone,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        font: `600 ${Math.round(size * 0.4)}px 'Space Grotesk', system-ui`,
        color: 'rgba(253,246,234,.92)',
      }}
    >
      {(profile.name || '?').trim().charAt(0).toUpperCase()}
    </div>
  );
}

function progressLine(profile) {
  if (!profile.read && !profile.reading) return 'nothing read yet';
  const parts = [];
  if (profile.reading) parts.push(`${profile.reading} in progress`);
  if (profile.read) parts.push(`${profile.read} read`);
  return parts.join(' · ');
}

function ProfileRow({ profile, active, busy, onPick, onRename, onDelete }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(profile.name);
  const [confirming, setConfirming] = useState(false);

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        padding: '16px 18px',
        borderRadius: 14,
        background: active ? 'var(--bg-surface-hover)' : 'transparent',
        border: `1px solid ${active ? 'var(--border-strong)' : 'var(--border-subtle)'}`,
        opacity: busy ? 0.5 : 1,
      }}
    >
      <Tone profile={profile} />

      {editing ? (
        <form
          style={{ flex: 1, display: 'flex', gap: 8, alignItems: 'center' }}
          onSubmit={(event) => {
            event.preventDefault();
            setEditing(false);
            if (draft.trim() && draft !== profile.name) onRename(profile.id, draft);
          }}
        >
          <input
            autoFocus
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            maxLength={40}
            style={{
              flex: 1,
              padding: '8px 12px',
              borderRadius: 'var(--radius-input)',
              border: '1px solid var(--border-strong)',
              background: 'transparent',
              color: 'var(--text-primary)',
              font: "400 14px 'Space Grotesk', system-ui",
              outline: 'none',
            }}
          />
          <Button size="sm" type="submit">
            Save
          </Button>
          <QuietLink
            onClick={() => {
              setDraft(profile.name);
              setEditing(false);
            }}
          >
            Cancel
          </QuietLink>
        </form>
      ) : (
        <>
          <button
            className="tap"
            onClick={() => onPick(profile.id)}
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'flex-start',
              gap: 4,
              background: 'transparent',
              border: 0,
              padding: 0,
              textAlign: 'left',
              cursor: 'pointer',
            }}
          >
            <span
              style={{
                fontFamily: 'var(--font-display-wide)',
                fontSize: 19,
                fontWeight: 600,
                color: 'var(--text-primary)',
              }}
            >
              {profile.name}
            </span>
            <span
              style={{ font: "400 11.5px 'IBM Plex Mono', monospace", color: 'var(--text-muted)' }}
            >
              {progressLine(profile)}
            </span>
          </button>

          {confirming ? (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <span
                style={{
                  font: "400 11px 'Space Grotesk', system-ui",
                  color: 'var(--chip-expired-fg)',
                }}
              >
                Delete {profile.name} and their reading?
              </span>
              <Button size="sm" variant="secondary" onClick={() => setConfirming(false)}>
                Keep
              </Button>
              <Button size="sm" onClick={() => onDelete(profile.id)}>
                Delete
              </Button>
            </div>
          ) : (
            <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
              {active && <Chip tone="claimed">reading</Chip>}
              {/* The owner's books are the shelf's books. Renaming hands the tablet
                  over; deleting would take the shelf's own history with it. */}
              {profile.owner && <Chip tone="neutral">owner</Chip>}
              <QuietLink onClick={() => setEditing(true)}>Rename</QuietLink>
              {!profile.owner && <QuietLink onClick={() => setConfirming(true)}>Delete</QuietLink>}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default function Profiles({
  profiles,
  activeId,
  busyId,
  error,
  onPick,
  onAdd,
  onRename,
  onDelete,
  onBack,
}) {
  const [name, setName] = useState('');

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        minHeight: 1112,
        boxSizing: 'border-box',
        padding: '40px 44px 34px',
      }}
    >
      <span
        style={{
          font: "600 10px 'IBM Plex Mono', monospace",
          letterSpacing: 'var(--track-eyebrow)',
          textTransform: 'uppercase',
          color: 'var(--text-muted)',
        }}
      >
        {profiles.length} {profiles.length === 1 ? 'reader' : 'readers'}
      </span>
      <h1
        style={{
          margin: '10px 0 0',
          fontFamily: 'var(--font-display-wide)',
          fontSize: 36,
          fontWeight: 600,
          lineHeight: 1.14,
          color: 'var(--text-primary)',
        }}
      >
        Who's reading?
      </h1>
      <p
        style={{
          margin: '12px 0 0',
          maxWidth: '46ch',
          fontFamily: 'var(--font-display-wide)',
          fontSize: 16,
          lineHeight: 1.8,
          color: 'var(--text-secondary)',
        }}
      >
        Everyone keeps their own page in every book — where you stopped, how many
        sittings it took, which ones you finished. The books are the same shelf; the
        reading is yours.
      </p>

      {error && (
        <div
          style={{
            marginTop: 20,
            padding: '14px 16px',
            borderRadius: 13,
            background: 'var(--chip-expired-bg)',
            color: 'var(--chip-expired-fg)',
            font: "400 12.5px/1.6 'Space Grotesk', system-ui",
          }}
        >
          {error}
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 26 }}>
        {profiles.map((profile) => (
          <ProfileRow
            key={profile.id}
            profile={profile}
            active={profile.id === activeId}
            busy={busyId === profile.id}
            onPick={onPick}
            onRename={onRename}
            onDelete={onDelete}
          />
        ))}
      </div>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (!name.trim()) return;
          onAdd(name);
          setName('');
        }}
        style={{ display: 'flex', gap: 10, alignItems: 'center', marginTop: 22 }}
      >
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Add a reader"
          maxLength={40}
          style={{
            flex: 1,
            padding: '11px 14px',
            borderRadius: 'var(--radius-input)',
            border: '1px dashed var(--border-strong)',
            background: 'transparent',
            color: 'var(--text-primary)',
            font: "400 13.5px 'Space Grotesk', system-ui",
            outline: 'none',
          }}
        />
        <Button type="submit" disabled={!name.trim()}>
          Add
        </Button>
      </form>

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 16,
          marginTop: 'auto',
          paddingTop: 26,
          borderTop: '1px solid var(--border-subtle)',
        }}
      >
        <span style={{ font: "400 11.5px 'IBM Plex Mono', monospace", color: 'var(--text-muted)' }}>
          data/positions/&lt;profile&gt;.json
        </span>
        <QuietLink onClick={onBack}>Back to shelf</QuietLink>
      </div>
    </div>
  );
}
