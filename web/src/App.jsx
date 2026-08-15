import { useCallback, useEffect, useMemo, useState } from 'react';

import { Card } from './components/ui';
import {
  addProfile,
  deleteProfile,
  finishBook,
  getBook,
  getProfiles,
  getShelf,
  putPosition,
  renameProfile,
  setProfile,
} from './lib/api';
import { PALETTE_NAMES } from './lib/reading';
import { usePrefs } from './lib/prefs';
import { useAmbience } from './lib/useAmbience';
import { recommendations } from './lib/recommend';
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
  const [screen, setScreen] = useState('shelf');
  const [book, setBook] = useState(null);
  const [position, setPosition] = useState({ part: 0, page: 0 });
  const [finishResult, setFinishResult] = useState(null);
  const [recIndex, setRecIndex] = useState(0);
  const [error, setError] = useState(null);
  const [profiles, setProfiles] = useState([]);
  const [busyProfile, setBusyProfile] = useState(null);
  const ambience = useAmbience(book);

  const who = profiles.find((p) => p.id === prefs.profile) || profiles.find((p) => p.owner);

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
      const chosen = rows.find((p) => p.id === prefs.profile) || rows.find((p) => p.owner);
      setProfile(chosen?.id || null);
      // A profile deleted from another tablet leaves a stale id here; fall back rather
      // than reading as somebody who no longer exists.
      if (chosen && chosen.id !== prefs.profile) setPrefs({ profile: chosen.id });
      // The settings are the reader's, and the server is where they live. The cached
      // copy has already painted; this is the reconcile, and it is silent when they
      // agree — which on the tablet somebody uses every day is every time.
      if (chosen?.prefs) adoptPrefs(chosen.prefs);
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
    [book],
  );

  const onFinish = useCallback(async () => {
    if (!book) return;
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
  }, [book, loadShelf]);

  // Switching reader re-fetches everything: the same books, a different set of
  // bookmarks in them. Nothing is cached across the swap on purpose — a stale "part 3
  // of 7" from the last person is the exact bug profiles exist to prevent.
  // `rows` is passed by the callers that have just fetched a fresher list than state
  // has — adding a reader, or deleting the one you are. Without it, switching to a
  // profile this render has never seen would leave the last reader's register up.
  const pickProfile = useCallback(
    async (id, rows) => {
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

  const onAddProfile = useCallback(
    async (name) => {
      setError(null);
      try {
        const created = await addProfile(name);
        const rows = await loadProfiles();
        pickProfile(created.id, rows);
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
        if (id === prefs.profile) pickProfile((rows.find((p) => p.owner) || {}).id, rows);
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

  const visible = useMemo(
    () => shelf.books.filter((b) => b.state === filter),
    [shelf.books, filter],
  );

  const recs = useMemo(
    () => (book ? recommendations(shelf.books, book.key, book.category, book.family) : []),
    [shelf.books, book],
  );

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
      <Chrome prefs={prefs} setPrefs={setPrefs} day={day} />

      {error && (
        <div
          style={{
            width: 'min(834px, 100%)',
            padding: '12px 16px',
            borderRadius: 13,
            background: 'var(--chip-expired-bg)',
            color: 'var(--chip-expired-fg)',
            font: "400 12.5px 'Space Grotesk', system-ui",
          }}
        >
          {error}
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
              filter={filter}
              onFilter={setFilter}
              onOpen={openBook}
              onLibrary={() => setScreen('library')}
              onProfiles={() => setScreen('profiles')}
            />
          )}

          {screen === 'profiles' && (
            <Profiles
              profiles={profiles}
              activeId={who?.id}
              busyId={busyProfile}
              error={null}
              onPick={pickProfile}
              onAdd={onAddProfile}
              onRename={onRenameProfile}
              onDelete={onDeleteProfile}
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
              onNavigate={navigate}
              onShelf={toShelf}
              onFinish={onFinish}
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
            />
          )}
        </Card>
      </div>
    </div>
  );
}

function Chrome({ prefs, setPrefs, day }) {
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
        bookv3 · {prefs.palette} palette · highlights in band order
      </span>
      <div style={{ display: 'flex', gap: 6, marginLeft: 'auto' }}>
        <button className="tap" style={style(day)} onClick={() => setPrefs({ theme: 'day' })}>
          Day
        </button>
        <button className="tap" style={style(!day)} onClick={() => setPrefs({ theme: 'night' })}>
          Night
        </button>
        <button
          className="tap"
          style={style(prefs.focusMode)}
          onClick={() => setPrefs({ focusMode: !prefs.focusMode })}
        >
          Pointer focus
        </button>
        <button
          className="tap"
          style={{ ...style(false), color: ink }}
          onClick={() =>
            setPrefs({
              palette:
                PALETTE_NAMES[(PALETTE_NAMES.indexOf(prefs.palette) + 1) % PALETTE_NAMES.length],
            })
          }
        >
          Next palette
        </button>
      </div>
    </div>
  );
}
