import { useCallback, useEffect, useMemo, useState } from 'react';

import { Card } from './components/ui';
import { finishBook, getBook, getShelf, putPosition } from './lib/api';
import { PALETTE_NAMES } from './lib/reading';
import { usePrefs } from './lib/prefs';
import { recommendations } from './lib/recommend';
import Finished from './screens/Finished';
import Reader from './screens/Reader';
import Shelf from './screens/Shelf';

// screen: 'shelf' | 'reader' | 'finish'. The whole app is one 834px card on a desk.

export default function App() {
  const [prefs, setPrefs] = usePrefs();
  const [shelf, setShelf] = useState({ books: [], counts: { total: 0, read: 0 } });
  const [filter, setFilter] = useState('reading');
  const [screen, setScreen] = useState('shelf');
  const [book, setBook] = useState(null);
  const [position, setPosition] = useState({ part: 0, page: 0 });
  const [finishResult, setFinishResult] = useState(null);
  const [recIndex, setRecIndex] = useState(0);
  const [error, setError] = useState(null);

  const day = prefs.theme === 'day';

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

  useEffect(() => {
    loadShelf();
  }, [loadShelf]);

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
              filter={filter}
              onFilter={setFilter}
              onOpen={openBook}
            />
          )}

          {screen === 'reader' && book && (
            <Reader
              book={book}
              part={position.part}
              page={position.page}
              prefs={prefs}
              onNavigate={navigate}
              onShelf={toShelf}
              onFinish={onFinish}
            />
          )}

          {screen === 'finish' && book && (
            <Finished
              book={book}
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
