import { useState } from 'react';

import { Button, Chip, QuietLink } from '../components/ui';

// Who is reading.
//
// This screen has no design file either, and unlike the library it is not an overview —
// it is one unit of work, the reader's own rule, so it is built like the shelf: a
// column of rows you choose between, and one thing to do at the bottom.
//
// A profile is a tone and a name, and optionally a PIN. The tone does the work the
// category patch does on the shelf — you know which row is yours before you read the
// name.
//
// The PIN locks the switch, not the API: it stops the next person to pick up the tablet
// reading as you, which is the problem a house has. It is not a login, and the screen
// should not imply one — hence "locked", not "signed out".

/**
 * Four to eight digits, on a numeric keypad, submitted by pressing enter or the button.
 *
 * `type="password"` with `inputMode="numeric"`: a tablet should offer the keypad, and
 * the digits should not be legible over the shoulder of the person entering them —
 * which, this being a lock against the room rather than the network, is most of what a
 * PIN field is for.
 */
function PinForm({ label, busy, error, onSubmit, onCancel, confirm = false }) {
  const [pin, setPin] = useState('');
  const [again, setAgain] = useState('');
  const [mismatch, setMismatch] = useState(null);

  const field = {
    width: confirm ? 96 : 120,
    padding: '8px 12px',
    borderRadius: 'var(--radius-input)',
    border: '1px solid var(--border-strong)',
    background: 'transparent',
    color: 'var(--text-primary)',
    font: "400 14px 'IBM Plex Mono', monospace",
    letterSpacing: '0.3em',
    outline: 'none',
  };

  return (
    <form
      style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'flex-end' }}
      onSubmit={(event) => {
        event.preventDefault();
        if (confirm && pin !== again) {
          setMismatch('Those do not match.');
          return;
        }
        setMismatch(null);
        onSubmit(pin);
      }}
    >
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <span style={{ font: "400 11px 'Space Grotesk', system-ui", color: 'var(--text-muted)' }}>
          {label}
        </span>
        <input
          autoFocus
          type="password"
          inputMode="numeric"
          autoComplete="off"
          value={pin}
          maxLength={8}
          placeholder="····"
          onChange={(event) => setPin(event.target.value.replace(/\D/g, ''))}
          style={field}
        />
        {confirm && (
          <input
            type="password"
            inputMode="numeric"
            autoComplete="off"
            value={again}
            maxLength={8}
            placeholder="again"
            onChange={(event) => setAgain(event.target.value.replace(/\D/g, ''))}
            style={field}
          />
        )}
        <Button size="sm" type="submit" disabled={busy || pin.length < 4}>
          {busy ? '…' : 'OK'}
        </Button>
        <QuietLink onClick={onCancel}>Cancel</QuietLink>
      </div>
      {(mismatch || error) && (
        <span style={{ font: "400 11px 'Space Grotesk', system-ui", color: 'var(--chip-expired-fg)' }}>
          {mismatch || error}
        </span>
      )}
    </form>
  );
}

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

/**
 * A Hardcover token, which is a credential rather than a lock.
 *
 * Its own field because `PinForm` strips everything that is not a digit, and this is a
 * long opaque string. Masked for the same reason a PIN is — it is read off a screen in a
 * room — but with no length rule of ours to enforce: Hardcover decides what is valid, and
 * the honest way to find out is to use it.
 */
function TokenForm({ busy, error, onSubmit, onCancel }) {
  const [token, setToken] = useState('');

  return (
    <form
      style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'flex-end' }}
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(token.trim());
      }}
    >
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <span style={{ font: "400 11px 'Space Grotesk', system-ui", color: 'var(--text-muted)' }}>
          Hardcover API token
        </span>
        <input
          autoFocus
          type="password"
          autoComplete="off"
          spellCheck="false"
          value={token}
          placeholder="eyJhbGciOi…"
          onChange={(event) => setToken(event.target.value)}
          style={{
            width: 220,
            padding: '8px 12px',
            borderRadius: 'var(--radius-input)',
            border: '1px solid var(--border-strong)',
            background: 'transparent',
            color: 'var(--text-primary)',
            font: "400 12px 'IBM Plex Mono', monospace",
            outline: 'none',
          }}
        />
        <Button size="sm" type="submit" disabled={busy || token.trim().length < 20}>
          {busy ? '…' : 'Link'}
        </Button>
        <QuietLink onClick={onCancel}>Cancel</QuietLink>
      </div>
      {error && (
        <span style={{ font: "400 11px 'Space Grotesk', system-ui", color: 'var(--chip-expired-fg)' }}>
          {error}
        </span>
      )}
    </form>
  );
}

function ProfileRow({ profile, active, busy, mine, onPick, onRename, onDelete, onSetPin,
                     onVerify, onSetHardcover }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(profile.name);
  const [confirming, setConfirming] = useState(false);
  // null | 'unlock' | 'set' | 'current' | 'remove'. Changing a PIN is 'current' and then
  // 'set': two plain prompts rather than one form asking for three numbers at once.
  const [asking, setAsking] = useState(null);
  const [current, setCurrent] = useState(null);
  const [pinError, setPinError] = useState(null);
  const [working, setWorking] = useState(false);

  const ask = (mode) => {
    setPinError(null);
    setCurrent(null);
    setAsking(mode);
  };

  const close = () => {
    setAsking(null);
    setCurrent(null);
    setPinError(null);
  };

  const submitPin = async (value) => {
    setWorking(true);
    setPinError(null);
    try {
      if (asking === 'unlock') {
        await onPick(profile.id, value);
      } else if (asking === 'current') {
        // Checked before the new one is asked for, so a wrong current PIN is caught
        // here rather than after typing a replacement twice.
        await onVerify(profile.id, value);
        setCurrent(value);
        setAsking('set');
      } else if (asking === 'set') {
        await onSetPin(profile.id, value, current);
        close();
      } else if (asking === 'remove') {
        await onSetPin(profile.id, null, value);
        close();
      } else if (asking === 'hardcover') {
        await onSetHardcover(profile.id, value);
        close();
      }
    } catch (ex) {
      setPinError(ex.message);
    }
    setWorking(false);
  };

  const PIN_LABELS = {
    unlock: `${profile.name}'s PIN`,
    set: current ? 'New PIN' : 'PIN',
    current: 'Current PIN',
    remove: 'Current PIN',
  };

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
            onClick={() => (profile.hasPin ? ask('unlock') : onPick(profile.id))}
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
              {profile.hasPin && (
                <span
                  title="Locked with a PIN"
                  style={{ marginLeft: 9, fontSize: 13, verticalAlign: 'middle' }}
                >
                  🔒
                </span>
              )}
            </span>
            <span
              style={{ font: "400 11.5px 'IBM Plex Mono', monospace", color: 'var(--text-muted)' }}
            >
              {progressLine(profile)}
            </span>
          </button>

          {asking === 'hardcover' ? (
            <TokenForm busy={working} error={pinError} onSubmit={submitPin} onCancel={close} />
          ) : asking ? (
            <PinForm
              label={PIN_LABELS[asking]}
              busy={working}
              error={pinError}
              confirm={asking === 'set'}
              onSubmit={submitPin}
              onCancel={close}
            />
          ) : confirming ? (
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
              {/* Only on your own row. Setting a PIN on somebody else's profile from
                  the picker would be locking them out of their own books, which is a
                  different thing from locking yours. */}
              {mine &&
                (profile.hasPin ? (
                  <>
                    <QuietLink onClick={() => ask('current')}>Change PIN</QuietLink>
                    <QuietLink onClick={() => ask('remove')}>Remove PIN</QuietLink>
                  </>
                ) : (
                  <QuietLink onClick={() => ask('set')}>Set a PIN</QuietLink>
                ))}
              {mine &&
                (profile.hasHardcover ? (
                  <QuietLink
                    title="Finished books stop being marked on Hardcover"
                    onClick={() => onSetHardcover(profile.id, null)}
                  >
                    Unlink Hardcover
                  </QuietLink>
                ) : (
                  <QuietLink
                    title="Finished books get marked read on your Hardcover shelf"
                    onClick={() => ask('hardcover')}
                  >
                    Link Hardcover
                  </QuietLink>
                ))}
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
  locked,
  onPick,
  onAdd,
  onRename,
  onDelete,
  onSetPin,
  onSetHardcover,
  onVerify,
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
        {locked ? 'locked' : `${profiles.length} ${profiles.length === 1 ? 'reader' : 'readers'}`}
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
        The catalogue is open to anyone. A profile is what makes it yours: your own page
        in every book, how many sittings it took, which ones you finished — and books
        suggested from the ones you have read. A PIN on your name means the tablet asks
        for it before it opens your shelf.
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
            mine={profile.id === activeId}
            onPick={onPick}
            onRename={onRename}
            onDelete={onDelete}
            onSetPin={onSetPin}
            onSetHardcover={onSetHardcover}
            onVerify={onVerify}
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
        {/* Nowhere to go back to while the tablet is locked: picking a reader is the
            only way on from here, which is what makes it a lock. */}
        {!locked && <QuietLink onClick={onBack}>Back to shelf</QuietLink>}
      </div>
    </div>
  );
}
