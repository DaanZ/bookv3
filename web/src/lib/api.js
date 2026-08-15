// In dev, Vite proxies /api to the FastAPI server (see vite.config.js). In production
// the same server hosts this bundle, so a relative path is right in both cases.
const BASE = '/api';

async function request(path, options) {
  const response = await fetch(`${BASE}${path}`, {
    headers: { 'content-type': 'application/json' },
    ...options,
  });
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

export const getBook = (key) => request(`/books/${encodeURIComponent(key)}`);

export const putPosition = (key, part, page) =>
  request(`/books/${encodeURIComponent(key)}/position`, {
    method: 'PUT',
    body: JSON.stringify({ part, page }),
  });

export const finishBook = (key) =>
  request(`/books/${encodeURIComponent(key)}/finish`, { method: 'POST' });

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

/** Uploads bypass `request`: the body is multipart, so the JSON header must not be set. */
export async function uploadPdf(file) {
  const body = new FormData();
  body.append('file', file);
  const response = await fetch('/api/ingest/upload', { method: 'POST', body });
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
