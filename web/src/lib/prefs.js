import { useCallback, useEffect, useRef, useState } from 'react';

import { setProfilePrefs } from './api';

// theme, palette and maxHighlights persist; the design lists them as the
// settings a reader owns rather than the app. They now live on the *profile*
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
};

// The keys that belong to the reader and travel to the server. `profile` is not one:
// it is this tablet's answer to "who is holding me".
const OWNED = ['theme', 'palette', 'maxHighlights'];

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

  const update = useCallback((patch) => {
    setPrefs((p) => ({ ...p, ...patch }));

    const mine = onlyOwned(patch);
    if (profileRef.current && Object.keys(mine).length) {
      // Fire and forget. A preference that failed to save is worth less than an error
      // banner across the reading surface, and the next change will carry it anyway.
      setProfilePrefs(profileRef.current, mine).catch(() => {});
    }
  }, []);

  /** Take a profile's stored settings as they are, without echoing them back. */
  const adopt = useCallback((incoming) => {
    setPrefs((p) => ({ ...p, ...onlyOwned(incoming) }));
  }, []);

  return [prefs, update, adopt];
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
