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
