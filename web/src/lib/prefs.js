import { useCallback, useEffect, useState } from 'react';

// theme, palette, focusMode and maxHighlights persist; the design lists them as the
// settings a reader owns rather than the app.
const KEY = 'bookv3.prefs';

const DEFAULTS = {
  theme: 'night',
  palette: 'sunset',
  focusMode: true,
  maxHighlights: 8,
};

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

  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(prefs));
    } catch {
      // Private mode or a full quota — the session still works, it just won't persist.
    }
  }, [prefs]);

  const update = useCallback((patch) => setPrefs((p) => ({ ...p, ...patch })), []);
  return [prefs, update];
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
