import { useCallback, useEffect, useRef, useState } from 'react';

import { Ambience, bedForCategory } from './ambience';
import { putAmbience } from './api';

// The ambience handoff's wiring rules, in one place:
//   1. Off by default; the choice belongs to the book, not the app, so {bed, level} is
//      stored per book and restored when that book reopens.
//   2. Suggest, don't impose — bedForCategory preselects, the rest are one tap away.
//   3. Duck while the resume strip is on screen; restore on page turn.
//   4. Silence at the finish screen — that moment is the reward.
//   5. One gesture to start. Never autoplay on load or on page turn.
//   6. Stop when the reader unmounts, or the tab is hidden for over a minute.

const HIDDEN_GRACE_MS = 60_000;
const DEFAULT_LEVEL = 0.3;

// The choice is stored beside this reader's bookmark in this book (api/positions.py)
// and arrives on the book payload, so it is per book *and* per profile: two people
// reading the same book keep their own bed, and either of them keeps it on whichever
// tablet they pick up. `on` is not stored — nothing may autoplay, so a bed is restored
// as a choice and never as sound.
export function useAmbience(book, keep = true) {
  const engineRef = useRef(null);
  const bookKey = book?.key || null;

  const [bed, setBed] = useState(book?.ambience?.bed || null);
  const [level, setLevelState] = useState(book?.ambience?.level ?? DEFAULT_LEVEL);
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

  // A new book arrives — or the same book as a different reader — so adopt what came
  // with it, and never carry sound across from the last one. Restoring the choice is
  // not the same as starting it.
  const stored = book?.ambience;
  useEffect(() => {
    if (!bookKey) return;
    setBed(stored?.bed || null);
    setLevelState(stored?.level ?? DEFAULT_LEVEL);
    setOn(false);
    if (engineRef.current?.playing) engineRef.current.stop();
  }, [bookKey, stored]);

  const persist = useCallback(
    (patch) => {
      // A guest has nowhere to keep it: the sound still plays, it is simply not
      // remembered, and the server would refuse the write anyway.
      if (!bookKey || !keep) return;
      // Fire and forget, like the position saves beside it: a bed that failed to
      // record is not worth an error across the reading surface.
      putAmbience(bookKey, { bed, level, ...patch }).catch(() => {});
    },
    [bookKey, keep, bed, level],
  );

  /** The user gesture that is allowed to start audio. */
  const playBed = useCallback(
    (key) => {
      engine().setLevel(level).play(key);
      setBed(key);
      setOn(true);
      persist({ bed: key });
    },
    [engine, level, persist],
  );

  const stop = useCallback(() => {
    engineRef.current?.stop();
    setOn(false);
  }, []);

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
