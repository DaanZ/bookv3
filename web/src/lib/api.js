// In dev, Vite proxies /api to the FastAPI server (see vite.config.js). In production
// the same server hosts this bundle, so a relative path is right in both cases.
const BASE = '/api';

import { cacheGet, cachePut, drain, enqueue, pin, pinnedKeys, queuedCount, unpin } from './offline';

// Whose reading these requests are. Held here rather than passed to every call: it
// qualifies all of them and is about none of them, which is the same reason it travels
// as a header rather than in the path. App sets it before the first shelf load; until
// then the server answers as the owner, exactly as it did before profiles existed.
let profileId = null;

export function setProfile(id) {
  profileId = id || null;
}

/**
 * Who to send, falling back to what the browser has stored.
 *
 * The module variable above is set once, by App's mount effect. That made it the only
 * copy of the answer, and anything that re-evaluated this module without re-running that
 * effect silently reset it to null — which the server reads as the guest, so the shelf
 * loses its bookmarks and every owner action comes back "Only the owner adds, removes or
 * re-files books". In development a hot reload does exactly that on every edit to this
 * file. The stored preference is the durable answer and this is the cache, so when the
 * cache is empty the stored one stands in rather than the app forgetting who it is.
 */
function currentProfile() {
  if (profileId) return profileId;
  try {
    const stored = JSON.parse(localStorage.getItem('bookv3.prefs') || '{}');
    return stored.profile || null;
  } catch {
    return null;
  }
}

/**
 * A request that failed because there was no server, as opposed to one the server
 * refused. The difference decides everything downstream: no server means fall back to
 * what is on the device and queue the write; a refusal means show the reader the reason.
 */
function offlineError(path) {
  const error = new Error('No connection to the library.');
  error.offline = true;
  error.path = path;
  return error;
}

const isWrite = (options) => Boolean(options?.method) && options.method !== 'GET';

// A gateway between the app and the library reports an absent server as an HTTP status
// rather than a failed connection: with uvicorn stopped, Vite's dev proxy answers 502 and
// `fetch` resolves perfectly happily. Treating that as a refusal meant the reader saw
// "502 Bad Gateway" instead of the book it had on the device.
//
// 500 is deliberately not here. That is a server which answered — it exists, it broke,
// and its reason belongs on screen rather than being papered over with a cached page.
const GATEWAY_DOWN = new Set([502, 503, 504]);

async function request(path, options) {
  // Network first, always. Being online must behave exactly as it did before this
  // existed — the cache is a fallback, never a shortcut, so nothing goes stale while
  // there is a server to ask.
  try {
    const data = await send(path, options);
    if (!isWrite(options)) cachePut(path, data);
    return data;
  } catch (error) {
    if (!error.offline) throw error;

    if (isWrite(options)) {
      // Nowhere to send it now; keep it and let the caller carry on as though it landed.
      await enqueue({ path, method: options.method, body: options.body ?? null });
      return { queued: true };
    }

    const cached = await cacheGet(path);
    if (cached !== null && cached !== undefined) return cached;
    throw error;
  }
}

async function send(path, options) {
  let response;
  try {
    response = await fetch(`${BASE}${path}`, {
    // Never read these from the HTTP cache. The server sends no-store, but that only
    // governs responses stored from now on: a stale server once answered /api/profiles
    // with the SPA's index.html under a 200, the browser cached it with no directives
    // at all, and every reload afterwards was served that HTML while the same URL
    // returned correct JSON to curl. Asking here means a browser already holding a bad
    // answer recovers on its own rather than needing its cache cleared.
    cache: 'no-store',
    headers: {
      'content-type': 'application/json',
      ...(currentProfile() ? { 'x-profile': currentProfile() } : null),
    },
      ...options,
    });
  } catch {
    // `fetch` rejects only when the request never reached a server — DNS, refused
    // connection, no network. A server that answered with a 500 resolves, so this
    // catch means "no library to talk to" and nothing else.
    throw offlineError(path);
  }

  if (GATEWAY_DOWN.has(response.status)) throw offlineError(path);

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // Non-JSON error body; the status line is all we have.
    }
    throw new Error(detail);
  }
  return response.json();
}

export const getShelf = () => request('/shelf');

/** Everyone reading here, and how far each of them has got. */
export const getProfiles = () => request('/profiles');

export const addProfile = (name) =>
  request('/profiles', { method: 'POST', body: JSON.stringify({ name }) });

export const renameProfile = (id, name) =>
  request(`/profiles/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify({ name }),
  });

export const deleteProfile = (id) =>
  request(`/profiles/${encodeURIComponent(id)}`, { method: 'DELETE' });

/**
 * Check a profile's PIN before switching into it. Resolves when it is right; rejects
 * with what the server said when it is not, including how long a run of wrong guesses
 * has bought. The digits go up and nothing comes back down — the browser is never told
 * anything about a PIN except whether one exists.
 */
export const unlockProfile = (id, pin, remember = false) =>
  request(`/profiles/${encodeURIComponent(id)}/unlock`, {
    method: 'POST',
    body: JSON.stringify({ pin, remember }),
  });

/**
 * Ask whether this device is still trusted, without a PIN.
 *
 * The token is the whole of the claim, so it is sent and never shown: the app knows only
 * that it holds one, and the server decides whether it is still good. Expiry is checked
 * there rather than here — a date the browser keeps is a reminder, not a check.
 */
export const unlockWithDevice = (id, device) =>
  request(`/profiles/${encodeURIComponent(id)}/unlock`, {
    method: 'POST',
    body: JSON.stringify({ device }),
  });

/** Stop trusting every remembered device for this profile. */
export const forgetDevices = (id) =>
  request(`/profiles/${encodeURIComponent(id)}/forget-devices`, { method: 'POST' });

/** Set, change or remove a PIN. `pin: null` removes it; `current` is needed to do either. */
export const setProfilePin = (id, pin, current) =>
  request(`/profiles/${encodeURIComponent(id)}/pin`, {
    method: 'PUT',
    body: JSON.stringify({ pin, current }),
  });

/**
 * Link this reader's own Hardcover account, or unlink it with `token: null`.
 *
 * Finishing a book marks it read on the account of whoever read it, so this is what
 * makes the completion list personal. The token goes up and never comes back down — the
 * profile only ever reports `hasHardcover`.
 */
export const setProfileHardcover = (id, token) =>
  request(`/profiles/${encodeURIComponent(id)}/hardcover`, {
    method: 'PUT',
    body: JSON.stringify({ token }),
  });

/** The reader's own settings — register, palette, highlight cap. */
export const setProfilePrefs = (id, patch) =>
  request(`/profiles/${encodeURIComponent(id)}/prefs`, {
    method: 'PUT',
    body: JSON.stringify(patch),
  });

/** The bed this reader chose for this book, kept beside their bookmark in it. */
export const putAmbience = (key, settings) =>
  request(`/books/${encodeURIComponent(key)}/ambience`, {
    method: 'PUT',
    body: JSON.stringify(settings),
  });

export const getBook = (key) => request(`/books/${encodeURIComponent(key)}`);

export const putPosition = (key, part, page) =>
  request(`/books/${encodeURIComponent(key)}/position`, {
    method: 'PUT',
    body: JSON.stringify({ part, page }),
  });

export const finishBook = (key) =>
  request(`/books/${encodeURIComponent(key)}/finish`, { method: 'POST' });

/** Ask Hardcover again about an already-finished book, without re-finishing it. */
export const resyncHardcover = (key) =>
  request(`/books/${encodeURIComponent(key)}/hardcover`, { method: 'POST' });

/** Fetch cover, rating and genres from Hardcover. Reads only; writes nothing there. */
export const enrichBook = (key) =>
  request(`/books/${encodeURIComponent(key)}/enrich`, { method: 'POST' });

/** What would be submitted if this book were added to Hardcover. Sends nothing. */
export const previewContribution = (key) =>
  request(`/books/${encodeURIComponent(key)}/contribution`);

/** Publish this book to Hardcover's shared catalogue. Only from an explicit confirm. */
export const submitContribution = (key) =>
  request(`/books/${encodeURIComponent(key)}/contribution`, { method: 'POST' });

export const moveBook = (key, finished) =>
  request(`/books/${encodeURIComponent(key)}`, {
    method: 'PATCH',
    body: JSON.stringify({ finished }),
  });

export const deleteBook = (key) =>
  request(`/books/${encodeURIComponent(key)}`, { method: 'DELETE' });

export const getJobs = () => request('/ingest/jobs');

/** How far the background cover lookup has got. Nothing starts it — the shelf does. */
export const getEnrichment = () => request('/enrichment');

export const clearJobs = () => request('/ingest/jobs', { method: 'DELETE' });

/** Run a failed job again, continuing from the parts it already paid for. */
export const resumeJob = (id) =>
  request(`/ingest/jobs/${encodeURIComponent(id)}/resume`, { method: 'POST' });

/** Remove one settled job, and the abandoned upload it left in next/. */
export const removeJob = (id) =>
  request(`/ingest/jobs/${encodeURIComponent(id)}`, { method: 'DELETE' });

/** Uploads bypass `request`: the body is multipart, so the JSON header must not be set. */
async function postFile(path, file) {
  const body = new FormData();
  body.append('file', file);
  const response = await fetch(path, {
    method: 'POST',
    body,
    cache: 'no-store',
    // The profile header, which `request` adds and this had no way of knowing about:
    // uploads bypass `request` because the body is multipart and the JSON content-type
    // must not be set. That exemption quietly took the reader's identity off with it,
    // so every upload arrived as a guest and the server refused it — "Only the owner
    // adds, removes or re-files books" — on a tablet where the owner was the one
    // holding it. Only the content-type is special here; who is asking is not.
    headers: currentProfile() ? { 'x-profile': currentProfile() } : undefined,
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      if (payload?.detail) detail = payload.detail;
    } catch {
      // Non-JSON error body; the status line is all we have.
    }
    throw new Error(detail);
  }
  return response.json();
}

/** What this book would cost. Reads the PDF, calls no model, queues nothing. */
export const estimatePdf = (file, chunks) =>
  postFile(`/api/ingest/estimate${chunks ? `?chunks=${chunks}` : ''}`, file);

export function uploadPdf(file, { chunks, model, cost } = {}) {
  const params = new URLSearchParams();
  if (chunks) params.set('chunks', chunks);
  if (model) params.set('model', model);
  if (cost != null) params.set('cost', cost);
  const query = params.toString();
  return postFile(`/api/ingest/upload${query ? `?${query}` : ''}`, file);
}

// ── offline ────────────────────────────────────────────────────────────────────

/**
 * Keep a book on this device.
 *
 * Fetching it is what caches it — `request` stores every successful GET — so this is a
 * fetch plus a note that the book was chosen deliberately, which is what tells a later
 * sync to refresh it.
 */
export async function keepOffline(key) {
  await getBook(key);
  await pin(key);
}

export async function dropOffline(key) {
  await unpin(key);
}

export const offlineBooks = () => pinnedKeys();

/**
 * Bring the device up to date, and send anything written while it was away.
 *
 * Called when the app opens and whenever the browser says it is back online. Refreshing
 * the kept books is the point of running it *before* a flight: the shelf and each pinned
 * book are fetched, which is what puts them on the device.
 */
export async function sync() {
  const sent = await drain((entry) =>
    send(entry.path, { method: entry.method, body: entry.body ?? undefined }),
  );

  let books = 0;
  try {
    await getProfiles();
    await getShelf();
    for (const key of await pinnedKeys()) {
      await getBook(key);
      books += 1;
    }
  } catch (error) {
    if (!error.offline) throw error;
  }

  return { ...sent, books, pending: await queuedCount() };
}

/** How much is waiting to be sent. The shelf shows this rather than hiding it. */
export const pendingWrites = () => queuedCount();

// ── remembered devices ─────────────────────────────────────────────────────────
//
// The token is kept in localStorage rather than IndexedDB: it is one short string per
// profile, it is read before anything else on launch, and localStorage is synchronous —
// an async read here would mean a frame of the PIN screen before the app knew it did not
// need one.

const DEVICE_KEY = 'bookv3.devices';

function deviceTokens() {
  try {
    const stored = JSON.parse(localStorage.getItem(DEVICE_KEY) || '{}');
    return stored && typeof stored === 'object' ? stored : {};
  } catch {
    return {};
  }
}

export const deviceTokenFor = (id) => deviceTokens()[id] || null;

export function rememberDevice(id, token) {
  if (!token) return;
  try {
    localStorage.setItem(DEVICE_KEY, JSON.stringify({ ...deviceTokens(), [id]: token }));
  } catch {
    // Private mode or a full quota: the reader is simply asked for the PIN next time.
  }
}

export function forgetDevice(id) {
  try {
    const tokens = deviceTokens();
    delete tokens[id];
    localStorage.setItem(DEVICE_KEY, JSON.stringify(tokens));
  } catch {
    // Nothing to do — the server copy is what actually grants entry.
  }
}
