import { useCallback, useEffect, useRef, useState } from 'react';

import { setProfilePrefs } from './api';

// theme, palette and maxHighlights persist; the design lists them as the
// settings a reader owns rather than the app. The shelf's order and spiral bands
// persist with them. They now live on the *profile*
// (api/profiles.py), so they follow the person rather than the glass: two people
// sharing a tablet no longer share a register, and the same person on a second tablet
// does not start over.
//
// localStorage still holds a copy, and is not the source of truth. It exists for the
// first paint: the profile's settings arrive a round-trip after mount, and without a
// cache the app would open in the default register and then swap — which is exactly
// the thing the design says is never animated because it is a different room.
const KEY = 'bookv3.prefs';

const DEFAULTS = {
  // Who is reading. Per browser rather than per profile — this is the tablet's memory
  // of who picked it up last, not something the profile carries with it.
  profile: null,
  theme: 'night',
  palette: 'sunset',
  maxHighlights: 8,
  // How the reader last left the shelf: its order, and the spiral band each slider was
  // narrowed to ([low, high], or null for every book). Saved to the profile like the
  // settings above, so the shelf opens as they left it, on this tablet or another.
  shelfSort: 'shuffled',
  spiralBands: { new: null, read: null },
};

// The keys that belong to the reader and travel to the server. `profile` is not one:
// it is this tablet's answer to "who is holding me".
const OWNED = ['theme', 'palette', 'maxHighlights', 'shelfSort', 'spiralBands'];

// Changes are sent this long after the last one. A slider sends a change for every tenth
// it passes, and a drag across the spiral was a dozen requests for one decision.
const SAVE_DELAY = 500;

function onlyOwned(source) {
  const out = {};
  for (const key of OWNED) if (source && key in source) out[key] = source[key];
  return out;
}

function load() {
  try {
    const stored = JSON.parse(localStorage.getItem(KEY) || '{}');
    return { ...DEFAULTS, ...stored };
  } catch {
    return { ...DEFAULTS };
  }
}

export function usePrefs() {
  const [prefs, setPrefs] = useState(load);

  // Read inside `update`, which is a callback the whole app holds: closing over
  // `prefs.profile` would send a change to whoever was reading when it was created.
  const profileRef = useRef(prefs.profile);
  useEffect(() => {
    profileRef.current = prefs.profile;
  }, [prefs.profile]);

  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(prefs));
    } catch {
      // Private mode or a full quota — the session still works, it just won't persist.
    }
  }, [prefs]);

  // Changes not yet sent, for one profile: {profile, patch, timer}.
  const pending = useRef(null);
  const flush = useCallback(() => {
    const due = pending.current;
    pending.current = null;
    if (!due) return;
    clearTimeout(due.timer);
    // Fire and forget. A preference that failed to save is worth less than an error
    // banner across the reading surface, and the next change will carry it anyway.
    setProfilePrefs(due.profile, due.patch).catch(() => {});
  }, []);
  // Whatever is waiting goes out before the page does.
  useEffect(() => {
    window.addEventListener('pagehide', flush);
    return () => {
      window.removeEventListener('pagehide', flush);
      flush();
    };
  }, [flush]);

  const update = useCallback((patch) => {
    setPrefs((p) => ({ ...p, ...patch }));

    const mine = onlyOwned(patch);
    const profile = profileRef.current;
    if (!profile || !Object.keys(mine).length) return;
    // A change for somebody else sends the previous reader's first, so a quick switch
    // of profile never hands one reader's settings to the next.
    if (pending.current && pending.current.profile !== profile) flush();
    const due = pending.current || { profile, patch: {} };
    clearTimeout(due.timer);
    due.patch = { ...due.patch, ...mine };
    due.timer = setTimeout(flush, SAVE_DELAY);
    pending.current = due;
  }, [flush]);

  /** Take a profile's stored settings as they are, without echoing them back. */
  const adopt = useCallback((incoming) => {
    setPrefs((p) => ({ ...p, ...onlyOwned(incoming) }));
  }, []);

  return [prefs, update, adopt];
}

// Below this the 834px tablet layout is on a phone: its padding and side-by-side rows
// were drawn for twice the width, and a book title ends up one word to a line.
const NARROW = '(max-width: 600px)';

/** True on a phone-width screen. Tracks rotation and window resizes. */
export function useNarrow() {
  const [narrow, setNarrow] = useState(
    () => typeof matchMedia === 'function' && matchMedia(NARROW).matches,
  );
  useEffect(() => {
    if (typeof matchMedia !== 'function') return undefined;
    const query = matchMedia(NARROW);
    const onChange = (event) => setNarrow(event.matches);
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, []);
  return narrow;
}

export function useReducedMotion() {
  const [reduced, setReduced] = useState(
    () => typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches,
  );
  useEffect(() => {
    if (typeof matchMedia !== 'function') return undefined;
    const query = matchMedia('(prefers-reduced-motion: reduce)');
    const onChange = (event) => setReduced(event.matches);
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, []);
  return reduced;
}
