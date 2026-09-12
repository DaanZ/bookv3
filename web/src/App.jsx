import { useCallback, useEffect, useMemo, useState } from 'react';

import { Card } from './components/ui';
import {
  addProfile,
  deleteProfile,
  finishBook,
  getBook,
  getProfiles,
  getSession,
  getShelf,
  putPosition,
  renameProfile,
  setProfile,
  setProfileHardcover,
  setProfilePin,
  unfinishBook,
  unlockProfile,
  unlockWithDevice,
  deviceTokenFor,
  rememberDevice,
  forgetDevice,
} from './lib/api';
import { PALETTE_NAMES, paletteFor } from './lib/reading';
import { usePrefs } from './lib/prefs';
import { useAmbience } from './lib/useAmbience';
import { fromLibrary, recommendations } from './lib/recommend';
import Finished from './screens/Finished';
import Library from './screens/Library';
import Profiles from './screens/Profiles';
import Reader from './screens/Reader';
import Shelf from './screens/Shelf';

// screen: 'shelf' | 'reader' | 'finish' | 'library' | 'profiles'. The whole app is one
// 834px card on a desk. Reading is one unit of work per screen; the library is the one
// surface that shows everything at once, because managing a collection needs the
// overview.
//
// Every request carries the reader (`setProfile`), so the shelf cannot be fetched before
// one is chosen — that ordering is why profiles load first and the shelf waits on them.

export default function App() {
  const [prefs, setPrefs, adoptPrefs] = usePrefs();
  const [shelf, setShelf] = useState({ books: [], counts: { total: 0, read: 0 } });
  const [filter, setFilter] = useState('reading');
  // How the rows are ordered, independent of which group is shown. The server already
  // returns them newest-first, so 'added' is simply that order left alone.
  const [sort, setSort] = useState('added');
  const [screen, setScreen] = useState('shelf');
  const [book, setBook] = useState(null);
  const [position, setPosition] = useState({ part: 0, page: 0 });
  const [finishResult, setFinishResult] = useState(null);
  const [recIndex, setRecIndex] = useState(0);
  const [error, setError] = useState(null);
  const [profiles, setProfiles] = useState([]);
  const [busyProfile, setBusyProfile] = useState(null);
  // The tablet is put away, or was opened onto a reader who locked theirs. Nothing is
  // fetched and there is no way off the picker until somebody proves who they are.
  const [locked, setLocked] = useState(false);
  // Finishing is not instant: it reaches Hardcover, which is a search, a status check and
  // a write — up to three calls that can each take twenty seconds. Without this the
  // button simply sat there and the reader was left guessing whether the tap had landed.
  const [finishing, setFinishing] = useState(false);
  // Every reader is a profile now, so there is always somewhere to keep the bed.
  const ambience = useAmbience(book, true);

  const who =
    profiles.find((p) => p.id === prefs.profile) || profiles.find((p) => p.owner);

  const day = prefs.theme === 'day';

  // Silence at the finish screen: that moment is the reward and should be quiet.
  const ambienceStop = ambience.stop;
  useEffect(() => {
    if (screen === 'finish' || screen === 'shelf') ambienceStop();
  }, [screen, ambienceStop]);

  const loadShelf = useCallback(async () => {
    try {
      const data = await getShelf();
      setShelf(data);
      // Land on the shelf the reader is most likely to want: what they were reading.
      setFilter((current) =>
        current === 'reading' && !data.books.some((b) => b.state === 'reading') ? 'new' : current,
      );
    } catch (ex) {
      setError(ex.message);
    }
  }, []);

  const loadProfiles = useCallback(async () => {
    try {
      const data = await getProfiles();
      setProfiles(data.profiles);
      return data.profiles;
    } catch (ex) {
      setError(ex.message);
      return [];
    }
  }, []);

  // Profiles first, then the shelf: the shelf is answered *as* somebody, so fetching it
  // before the header is set would show the owner's progress to whoever picked up the
  // tablet — and then quietly swap it a moment later, which is worse than waiting.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const rows = await loadProfiles();
      if (cancelled) return;
      // Does this machine log itself in? Asked before anything is chosen, because on a
      // trusted computer the PIN screen below must never paint at all — discovering
      // afterwards that it was not needed is the flicker this avoids.
      let session = null;
      try {
        session = await getSession();
      } catch {
        // Offline, or an older server with no /api/session. Fall through to the PIN,
        // which is the behaviour without this feature.
      }
      if (cancelled) return;

      const chosen = session?.auto && session.profile
        ? rows.find((p) => p.id === session.profile.id) || session.profile
        : rows.find((p) => p.id === prefs.profile) || rows.find((p) => p.owner);
      setProfile(chosen?.id || null);
      // A profile deleted from another tablet leaves a stale id here; fall back rather
      // than reading as somebody who no longer exists.
      if (chosen && chosen.id !== prefs.profile) setPrefs({ profile: chosen.id });
      // The settings are the reader's, and the server is where they live. The cached
      // copy has already painted; this is the reconcile, and it is silent when they
      // agree — which on the tablet somebody uses every day is every time.
      if (chosen?.prefs) adoptPrefs(chosen.prefs);

      // A PIN is only a lock if opening the app asks for it. Otherwise the tablet sits
      // on somebody's shelf all evening and the digits protected one tap nobody made.
      // A trusted machine has already been answered for; asking for its own PIN would
      // be asking it to prove something the server has stopped asking about.
      if (chosen?.hasPin && !session?.auto) {
        // A device that has already answered the PIN stays answered for ninety days.
        // Checked against the server rather than trusted from storage: the browser holds
        // the token, the server holds whether it is still good.
        const token = deviceTokenFor(chosen.id);
        let trusted = false;
        if (token) {
          try {
            trusted = Boolean((await unlockWithDevice(chosen.id, token))?.ok);
          } catch {
            // Expired, forgotten from the other end, or no server to ask. Either way the
            // PIN is the fallback, which is the behaviour without this feature at all.
            trusted = false;
          }
          if (!trusted) forgetDevice(chosen.id);
        }
        if (!trusted) {
          setLocked(true);
          setScreen('profiles');
          return;
        }
      }
      loadShelf();
    })();
    return () => {
      cancelled = true;
    };
    // Only on mount: switching profiles goes through `pickProfile`, which reloads both.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // The desk is outside the card, so it is painted on the document rather than a div.
  useEffect(() => {
    document.body.style.background = day ? '#E6DED0' : '#04181B';
  }, [day]);

  const openBook = useCallback(async (key) => {
    setError(null);
    try {
      const detail = await getBook(key);
      setBook(detail);
      setFinishResult(null);
      setRecIndex(0);
      if (detail.state === 'read') {
        setPosition({ part: 0, page: 0 });
        setScreen('finish');
      } else {
        setPosition({ part: detail.at, page: detail.page });
        setScreen('reader');
      }
    } catch (ex) {
      setError(ex.message);
    }
  }, []);

  const navigate = useCallback(
    (part, page) => {
      setPosition({ part, page });
      if (book) putPosition(book.key, part, page).catch((ex) => setError(ex.message));
    },
    [book, who],
  );

  const onFinish = useCallback(async () => {
    if (!book) return;
    setFinishing(true);
    try {
      const result = await finishBook(book.key);
      setFinishResult(result);
      // Re-read the book: finishing is what records the last sitting, so the
      // "read in N sittings over M days" line is only true after this round-trip.
      setBook(await getBook(book.key));
      setScreen('finish');
      loadShelf();
    } catch (ex) {
      setError(ex.message);
    }
    setFinishing(false);
  }, [book, loadShelf]);

  // Switching reader re-fetches everything: the same books, a different set of
  // bookmarks in them. Nothing is cached across the swap on purpose — a stale "part 3
  // of 7" from the last person is the exact bug profiles exist to prevent.
  // `pin` is what the picker collected, if that profile has one. `rows` is passed by the
  // callers that have just fetched a fresher list than state has — adding a reader, or
  // deleting the one you are — because switching to a profile this render has never seen
  // would otherwise leave the last reader's register up and miss their PIN entirely.
  const pickProfile = useCallback(
    async (id, pin, rows) => {
      // Checked before anything else moves: a wrong PIN must leave the app exactly
      // where it was, still as whoever it was, and the row shows what the server said.
      const target = (rows || profiles).find((p) => p.id === id);
      if (target?.hasPin) {
        // `remember` defaults on: a PIN asked for every time on the tablet in your own
        // house is a PIN that gets switched off, and then it protects nothing.
        const result = await unlockProfile(id, pin, true);
        if (result?.device) rememberDevice(id, result.device);
      }

      setLocked(false);
      setProfile(id);
      setPrefs({ profile: id });
      // Their register, their palette, their highlight cap — adopted before the shelf
      // paints, so switching reader is one change of room rather than two.
      adoptPrefs((rows || profiles).find((p) => p.id === id)?.prefs);
      setBook(null);
      setFinishResult(null);
      setFilter('reading');
      setScreen('shelf');
      await loadShelf();
      loadProfiles();
    },
    [loadShelf, loadProfiles, setPrefs, adoptPrefs, profiles],
  );

  // Errors are thrown, not swallowed: the row that asked for the PIN is where the
  // answer belongs, not a banner across the top of the card.
  const onVerifyPin = useCallback(async (id, pin) => {
    const result = await unlockProfile(id, pin);
    // Kept rather than discarded. Every unlock mints a token now, so throwing this one
    // away would leave an orphan on the profile until it expired — and the reader has
    // just proved the PIN, which is precisely when a session is worth holding.
    if (result?.device) rememberDevice(id, result.device);
    return result;
  }, []);

  // Linking is per reader, and the token never comes back — the row only learns whether
  // one is set, so the list is reloaded rather than patched in place.
  const onSetHardcover = useCallback(
    async (id, token) => {
      setError(null);
      setBusyProfile(id);
      try {
        await setProfileHardcover(id, token);
        await loadProfiles();
      } catch (ex) {
        setError(ex.message);
      }
      setBusyProfile(null);
    },
    [loadProfiles],
  );

  const onSetPin = useCallback(
    async (id, pin, current) => {
      await setProfilePin(id, pin, current);
      await loadProfiles();
    },
    [loadProfiles],
  );

  const lock = useCallback(() => {
    setLocked(true);
    setBook(null);
    setFinishResult(null);
    setScreen('profiles');
  }, []);

  const onAddProfile = useCallback(
    async (name) => {
      setError(null);
      try {
        const created = await addProfile(name);
        const rows = await loadProfiles();
        pickProfile(created.id, null, rows);
      } catch (ex) {
        setError(ex.message);
      }
    },
    [loadProfiles, pickProfile],
  );

  const onRenameProfile = useCallback(
    async (id, name) => {
      setError(null);
      setBusyProfile(id);
      try {
        await renameProfile(id, name);
        await loadProfiles();
      } catch (ex) {
        setError(ex.message);
      }
      setBusyProfile(null);
    },
    [loadProfiles],
  );

  const onDeleteProfile = useCallback(
    async (id) => {
      setError(null);
      setBusyProfile(id);
      try {
        await deleteProfile(id);
        const rows = await loadProfiles();
        // Deleting the reader you are — fall back to the owner rather than carrying on
        // as an id the server no longer knows.
        if (id === prefs.profile) pickProfile((rows.find((p) => p.owner) || {}).id, null, rows);
      } catch (ex) {
        setError(ex.message);
      }
      setBusyProfile(null);
    },
    [loadProfiles, pickProfile, prefs.profile],
  );

  const toShelf = useCallback(() => {
    setScreen('shelf');
    setBook(null);
    loadShelf();
  }, [loadShelf]);

  // The finish undone. Clears this reader's record and, for the owner, refiles the book
  // — then lands on the shelf, because the screen it was called from is about a finish
  // that no longer happened.
  const onUnfinish = useCallback(async () => {
    if (!book) return;
    try {
      await unfinishBook(book.key);
      setFinishResult(null);
      toShelf();
    } catch (ex) {
      setError(ex.message);
    }
  }, [book, toShelf]);

  const visible = useMemo(() => {
    const rows = shelf.books.filter((b) => b.state === filter);
    // 'added' is the order the shelf endpoint already sorted them into, so leave it
    // alone rather than re-deriving it here from a date the client would have to parse.
    return sort === 'title'
      ? [...rows].sort((a, b) => a.title.localeCompare(b.title))
      : rows;
  }, [shelf.books, filter, sort]);

  const recs = useMemo(
    () => (book ? recommendations(shelf.books, book.key, book.category, book.family) : []),
    [shelf.books, book],
  );

  // What this reader's own history points at. Empty for a reader who has finished
  // nothing here, because there is nothing to reason from.
  const suggestion = useMemo(() => fromLibrary(shelf.books)[0] || null, [shelf.books]);

  const themeLabel = day ? 'day · cane paper' : 'night · deep water';

  return (
    // A register change is never animated — Deep to Shore is a different room; it loads.
    <div
      className={day ? 'shore' : ''}
      style={{
        minHeight: '100vh',
        background: day ? '#E6DED0' : '#04181B',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 18,
        padding: '26px 12px 60px',
      }}
    >
      <Chrome
        prefs={prefs}
        setPrefs={setPrefs}
        day={day}
        who={who}
        onProfiles={() => setScreen('profiles')}
      />

      {error && (
        <div
          style={{
            width: 'min(834px, 100%)',
            padding: '12px 16px',
            borderRadius: 13,
            background: 'var(--chip-expired-bg)',
            color: 'var(--chip-expired-fg)',
            font: "400 12.5px 'Space Grotesk', system-ui",
            display: 'flex',
            alignItems: 'center',
          }}
        >
          <span>{error}</span>
          {/* An error that names a thing to do should be able to do it. Being told to
              pick a profile with no way to reach one is how this error was met the first
              time it appeared. */}
          {/needs a name|pick a profile/i.test(error) && (
            <button
              type="button"
              onClick={() => setScreen('profiles')}
              style={{
                marginLeft: 12,
                border: 0,
                background: 'transparent',
                color: 'inherit',
                font: "600 12.5px 'Space Grotesk', system-ui",
                textDecoration: 'underline',
                textUnderlineOffset: 3,
                cursor: 'pointer',
              }}
            >
              Choose a profile
            </button>
          )}
        </div>
      )}

      <div style={{ width: 'min(834px, 100%)' }}>
        <Card
          elevation="shelf"
          style={{ padding: 0, overflow: 'hidden', width: '100%', gap: 0 }}
        >
          {screen === 'shelf' && (
            <Shelf
              books={visible}
              counts={shelf.counts}
              themeLabel={themeLabel}
              who={who}
              suggestion={suggestion}
              filter={filter}
              onFilter={setFilter}
              sort={sort}
              onSort={setSort}
              onOpen={openBook}
              onLibrary={() => setScreen('library')}
              onProfiles={() => setScreen('profiles')}
              palette={prefs.palette}
              day={day}
              onLock={who?.hasPin ? lock : null}
            />
          )}

          {screen === 'profiles' && (
            <Profiles
              profiles={profiles}
              // Nobody is the active reader while the tablet is locked, so nobody's row
              // offers to change a PIN.
              activeId={locked ? null : who?.id}
              busyId={busyProfile}
              error={null}
              locked={locked}
              onPick={pickProfile}
              onAdd={onAddProfile}
              onRename={onRenameProfile}
              onDelete={onDeleteProfile}
              onSetPin={onSetPin}
              onSetHardcover={onSetHardcover}
              onVerify={onVerifyPin}
              onBack={toShelf}
            />
          )}

          {screen === 'library' && (
            <Library
              books={shelf.books}
              counts={shelf.counts}
              // The summarising bars are drawn from the reading palette, so the library
              // needs the same two preferences the reader colours highlights with.
              palette={prefs.palette}
              day={day}
              onShelf={toShelf}
              onChanged={loadShelf}
            />
          )}

          {screen === 'reader' && book && (
            <Reader
              book={book}
              part={position.part}
              page={position.page}
              prefs={prefs}
              ambience={ambience}
              canFinish
              onNavigate={navigate}
              onShelf={toShelf}
              onFinish={onFinish}
              finishing={finishing}
            />
          )}

          {screen === 'finish' && book && (
            <Finished
              book={book}
              who={who}
              result={finishResult}
              recommendation={recs.length ? recs[recIndex % recs.length] : null}
              counts={shelf.counts}
              onOpenRec={() => openBook(recs[recIndex % recs.length].key)}
              onNextRec={() => setRecIndex((i) => i + 1)}
              onShelf={toShelf}
              onReset={onUnfinish}
            />
          )}
        </Card>
      </div>
    </div>
  );
}

/**
 * Day/night as one switch rather than two buttons.
 *
 * Two buttons made the register look like a pair of choices, one of which happened to be
 * lit. It is one setting with two positions, and a switch says that in its shape — where
 * the knob sits *is* the answer, readable without reading either word.
 *
 * The knob moves; the register does not. `--dur-instant` is deliberate: the design
 * system's rule that the Deep-to-Shore swap is never animated is about the room, not
 * about the light switch on its wall, and a switch whose knob teleports feels broken
 * while a page that fades between registers feels cheap.
 */
function RegisterSwitch({ day, onChange }) {
  const edge = day ? 'rgba(20,32,31,.18)' : 'rgba(253,246,234,.2)';
  const label = (on) => ({
    flex: 1,
    zIndex: 1,
    padding: '6px 12px',
    textAlign: 'center',
    font: "500 12px 'Space Grotesk', system-ui",
    color: on ? 'var(--accent-on)' : day ? 'rgba(20,32,31,.6)' : 'rgba(253,246,234,.6)',
    transition: 'color var(--dur-instant, 90ms) var(--ease-move, ease)',
  });

  return (
    <button
      type="button"
      role="switch"
      aria-checked={!day}
      aria-label={`Register: ${day ? 'day' : 'night'}. Switch to ${day ? 'night' : 'day'}.`}
      onClick={() => onChange(day ? 'night' : 'day')}
      style={{
        position: 'relative',
        display: 'flex',
        alignItems: 'center',
        width: 132,
        padding: 0,
        borderRadius: 999,
        border: `1px solid ${edge}`,
        background: 'transparent',
        cursor: 'pointer',
        overflow: 'hidden',
      }}
    >
      <span
        aria-hidden="true"
        style={{
          position: 'absolute',
          top: 0,
          bottom: 0,
          left: 0,
          width: '50%',
          borderRadius: 999,
          background: 'var(--accent)',
          transform: day ? 'translateX(0)' : 'translateX(100%)',
          transition: 'transform var(--dur-quick, 160ms) var(--ease-move, ease)',
        }}
      />
      <span style={label(day)}>Day</span>
      <span style={label(!day)}>Night</span>
    </button>
  );
}

/**
 * Whose reading this is, worn as a mark rather than spelled out.
 *
 * The profile lived only in the shelf's footer, so on every other screen there was
 * nothing at all saying who you were — and the answer changes what the shelf shows and
 * what you are allowed to do. Its tone is the profile's own colour, so it reads as a
 * face at a glance before the letter is legible.
 */
function ProfileMark({ who, onProfiles, day }) {
  if (!who) return null;
  return (
    <button
      type="button"
      onClick={onProfiles}
      title={`${who.name} — switch reader`}
      aria-label={`Reading as ${who.name}. Switch reader.`}
      style={{
        display: 'grid',
        placeItems: 'center',
        width: 28,
        height: 28,
        padding: 0,
        borderRadius: 8,
        border: `1px solid ${day ? 'rgba(20,32,31,.18)' : 'rgba(253,246,234,.2)'}`,
        background: who.tone || 'var(--bg-surface-hover)',
        color: '#FDF6EA',
        font: "600 12px 'Space Grotesk', system-ui",
        cursor: 'pointer',
        flexShrink: 0,
      }}
    >
      {(who.name || '?').trim().charAt(0).toUpperCase()}
    </button>
  );
}

function Chrome({ prefs, setPrefs, day, who, onProfiles }) {
  const ink = day ? 'rgba(20,32,31,.55)' : 'rgba(253,246,234,.5)';
  const style = (on) => ({
    width: 'auto',
    padding: '7px 13px',
    borderRadius: 10,
    font: "500 12px 'Space Grotesk', system-ui",
    background: on ? 'var(--accent)' : 'transparent',
    color: on ? 'var(--accent-on)' : day ? 'rgba(20,32,31,.6)' : 'rgba(253,246,234,.6)',
    border: `1px solid ${on ? 'var(--accent)' : day ? 'rgba(20,32,31,.18)' : 'rgba(253,246,234,.2)'}`,
  });

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 18,
        width: 'min(834px, 100%)',
        padding: '0 2px',
        flexWrap: 'wrap',
      }}
    >
      <span
        style={{
          font: "600 10px 'IBM Plex Mono', monospace",
          letterSpacing: 'var(--track-eyebrow)',
          textTransform: 'uppercase',
          color: ink,
        }}
      >
        Snippers · {prefs.palette} palette · highlights in band order
      </span>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginLeft: 'auto' }}>
        {/* Who, then how it looks: the mark sits left of the register switch because it
            qualifies everything to its right. */}
        <ProfileMark who={who} onProfiles={onProfiles} day={day} />
        <RegisterSwitch day={day} onChange={(theme) => setPrefs({ theme })} />
        {/* The palette shown rather than named. "sunset" and "coral" mean nothing until
            you have seen them, and the point of the control is to choose colours — so it
            wears the colours it would give you, in the register you are reading in.
            Sampled through paletteFor, so these are the exact stops a page would use,
            not the raw bands. The name stays as the accessible label. */}
        <button
          className="tap"
          aria-label={`Palette: ${prefs.palette}. Switch to the next palette.`}
          title={`${prefs.palette} — switch palette`}
          style={{ ...style(false), color: ink, display: 'flex', alignItems: 'center', gap: 5 }}
          onClick={() =>
            setPrefs({
              palette:
                PALETTE_NAMES[(PALETTE_NAMES.indexOf(prefs.palette) + 1) % PALETTE_NAMES.length],
            })
          }
        >
          <span style={{ display: 'flex', gap: 2 }}>
            {paletteFor(prefs.palette, day, 6).map((colour) => (
              <span
                key={colour}
                style={{ width: 7, height: 12, borderRadius: 1.5, background: colour }}
              />
            ))}
          </span>
          {prefs.palette}
        </button>
      </div>
    </div>
  );
}
