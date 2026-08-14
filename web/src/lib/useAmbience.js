import { useCallback, useEffect, useRef, useState } from 'react';

import { Ambience, bedForCategory } from './ambience';

// The ambience handoff's wiring rules, in one place:
//   1. Off by default; the choice belongs to the book, not the app, so {bed, level, on}
//      is stored per book and restored when that book reopens.
//   2. Suggest, don't impose — bedForCategory preselects, the rest are one tap away.
//   3. Duck while the resume strip is on screen; restore on page turn.
//   4. Silence at the finish screen — that moment is the reward.
//   5. One gesture to start. Never autoplay on load or on page turn.
//   6. Stop when the reader unmounts, or the tab is hidden for over a minute.

const KEY = 'bookv3.ambience';
const HIDDEN_GRACE_MS = 60_000;

function loadAll() {
  try {
    const stored = JSON.parse(localStorage.getItem(KEY) || '{}');
    return typeof stored === 'object' && stored ? stored : {};
  } catch {
    return {};
  }
}

function saveFor(bookKey, entry) {
  if (!bookKey) return;
  try {
    const all = loadAll();
    all[bookKey] = entry;
    localStorage.setItem(KEY, JSON.stringify(all));
  } catch {
    // Private mode or a full quota — the session still works, it just won't persist.
  }
}

export function settingsFor(bookKey) {
  return loadAll()[bookKey] || null;
}

export function useAmbience(book) {
  const engineRef = useRef(null);
  const bookKey = book?.key || null;

  const stored = bookKey ? settingsFor(bookKey) : null;
  const [bed, setBed] = useState(stored?.bed || null);
  const [level, setLevelState] = useState(stored?.level ?? 0.3);
  const [on, setOn] = useState(false);

  // The bed this book's category suggests. null means "say nothing" — politically
  // charged material defaults to silence rather than being scored.
  const suggested = book ? bedForCategory(book.category) : null;

  // Constructed on first use, never on mount: the handoff is explicit that no
  // AudioContext exists until a gesture asks for one. playBed sets the level straight
  // after, so the constructor's default is never the one that plays.
  const engine = useCallback(() => {
    if (!engineRef.current) engineRef.current = new Ambience();
    return engineRef.current;
  }, []);

  // A new book arrives: adopt its stored choice, and never carry sound across from
  // the last one. Restoring the choice is not the same as starting it.
  useEffect(() => {
    if (!bookKey) return;
    const saved = settingsFor(bookKey);
    setBed(saved?.bed || null);
    setLevelState(saved?.level ?? 0.3);
    setOn(false);
    if (engineRef.current?.playing) engineRef.current.stop();
  }, [bookKey]);

  const persist = useCallback(
    (patch) => saveFor(bookKey, { bed, level, on, ...patch }),
    [bookKey, bed, level, on],
  );

  /** The user gesture that is allowed to start audio. */
  const playBed = useCallback(
    (key) => {
      engine().setLevel(level).play(key);
      setBed(key);
      setOn(true);
      persist({ bed: key, on: true });
    },
    [engine, level, persist],
  );

  const stop = useCallback(() => {
    engineRef.current?.stop();
    setOn(false);
    persist({ on: false });
  }, [persist]);

  const toggle = useCallback(
    (key) => {
      if (on && key === bed) stop();
      else playBed(key);
    },
    [on, bed, stop, playBed],
  );

  const setLevel = useCallback(
    (next) => {
      setLevelState(next);
      engineRef.current?.setLevel(next);
      persist({ level: next });
    },
    [persist],
  );

  const duck = useCallback((should) => {
    engineRef.current?.duck(should);
  }, []);

  // Hidden for over a minute: it is still a live audio graph. A quick tab switch
  // should not cost the reader their bed, so the grace period matters.
  useEffect(() => {
    let timer = null;
    const onVisibility = () => {
      if (document.hidden) {
        timer = setTimeout(() => {
          engineRef.current?.stop();
          setOn(false);
        }, HIDDEN_GRACE_MS);
      } else if (timer) {
        clearTimeout(timer);
        timer = null;
      }
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      if (timer) clearTimeout(timer);
    };
  }, []);

  // Tear the graph down for good when the app unmounts.
  useEffect(() => () => engineRef.current?.dispose(), []);

  return { bed, level, on, suggested, playBed, stop, toggle, setLevel, duck };
}
