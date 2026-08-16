// Reading with no server.
//
// The reader is a browser talking to a FastAPI process on a laptop. On a plane there is
// no laptop, so everything the reading path needs has to already be on the device, and
// everything it writes has to wait somewhere until there is a server again.
//
// Three stores, one job each:
//
//   responses — the last good answer for a GET, keyed by path. Read only when the
//               network fails, so being online behaves exactly as it did before.
//   queue     — writes made with no server, replayed in order when one returns.
//   pinned    — which books were deliberately kept, so a sync knows what to refresh.
//
// IndexedDB rather than localStorage: the corpus was 264 books and 4.3MB, and
// localStorage caps around 5MB and stores strings only. Written against the raw API
// rather than a wrapper library — it is three object stores and no schema to speak of.

const DB_NAME = 'bookv3';
const DB_VERSION = 1;
const STORES = ['responses', 'queue', 'pinned'];

let dbPromise = null;

function openDb() {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    if (typeof indexedDB === 'undefined') {
      reject(new Error('This browser has no IndexedDB.'));
      return;
    }
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      for (const name of STORES) {
        if (!db.objectStoreNames.contains(name)) {
          // The queue is the only one that needs its own keys — a write has no natural
          // id, and replay order is the whole point.
          db.createObjectStore(name, name === 'queue' ? { autoIncrement: true } : undefined);
        }
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  return dbPromise;
}

async function tx(store, mode, run) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(store, mode);
    const request = run(transaction.objectStore(store));
    transaction.onerror = () => reject(transaction.error);
    if (request) {
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    } else {
      transaction.oncomplete = () => resolve();
    }
  });
}

/** Never let storage break reading: a cache that throws is worse than no cache. */
async function quietly(work, fallback = null) {
  try {
    return await work();
  } catch {
    return fallback;
  }
}

// ── responses ──────────────────────────────────────────────────────────────────

export const cacheGet = (path) => quietly(() => tx('responses', 'readonly', (s) => s.get(path)));

export const cachePut = (path, data) =>
  quietly(() => tx('responses', 'readwrite', (s) => s.put(data, path)));

export const cachedPaths = () =>
  quietly(() => tx('responses', 'readonly', (s) => s.getAllKeys()), []);

// ── the write queue ────────────────────────────────────────────────────────────

/**
 * Remember a write that had nowhere to go.
 *
 * Order is kept because it matters: a position for part 3 followed by one for part 7
 * must not land the other way round, and a finish must follow the reading that earned it.
 */
export const enqueue = (entry) =>
  quietly(() => tx('queue', 'readwrite', (s) => s.put({ ...entry, at: Date.now() })));

export const queued = () => quietly(() => tx('queue', 'readonly', (s) => s.getAll()), []);

export const queuedCount = async () => (await queued()).length;

const clearQueue = () => quietly(() => tx('queue', 'readwrite', (s) => s.clear()));

/**
 * Send everything that was written offline, oldest first.
 *
 * Stops at the first failure and keeps the rest: a server that has gone away again
 * should not cost the writes still waiting. Individual rejections — a book deleted
 * meanwhile, a finish the server already recorded — are dropped rather than retried
 * forever, because they will never succeed and would block everything behind them.
 */
export async function drain(send) {
  const entries = await queued();
  if (!entries.length) return { sent: 0, kept: 0 };

  const ordered = [...entries].sort((a, b) => a.at - b.at);
  const kept = [];
  let sent = 0;

  for (let i = 0; i < ordered.length; i += 1) {
    const entry = ordered[i];
    try {
      await send(entry);
      sent += 1;
    } catch (error) {
      // Offline again: keep this one and everything after it, in order.
      if (error?.offline) {
        kept.push(...ordered.slice(i));
        break;
      }
      // The server answered and refused. Replaying will not change its mind.
    }
  }

  await clearQueue();
  for (const entry of kept) await enqueue(entry);
  return { sent, kept: kept.length };
}

// ── pinned books ───────────────────────────────────────────────────────────────

export const pin = (key) => quietly(() => tx('pinned', 'readwrite', (s) => s.put(true, key)));

export const unpin = (key) => quietly(() => tx('pinned', 'readwrite', (s) => s.delete(key)));

export const pinnedKeys = () => quietly(() => tx('pinned', 'readonly', (s) => s.getAllKeys()), []);

export const isPinned = async (key) => (await pinnedKeys()).includes(key);
