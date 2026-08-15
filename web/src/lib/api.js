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

/** Remove one settled job, and the abandoned upload it left in next/. */
export const removeJob = (id) =>
  request(`/ingest/jobs/${encodeURIComponent(id)}`, { method: 'DELETE' });

/** Uploads bypass `request`: the body is multipart, so the JSON header must not be set. */
async function postFile(path, file) {
  const body = new FormData();
  body.append('file', file);
  const response = await fetch(path, { method: 'POST', body });
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
