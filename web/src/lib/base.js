// Where the app is mounted, and the one place that knows.
//
// The reader was written for `https://host/` and hardcoded that assumption in five
// places: the API base, two upload paths, four ambience beds and three favicons. Served
// from `https://singularitynexus.nl/books` every one of them reaches for the domain root
// instead — the bundle 404s before a book is ever listed.
//
// `import.meta.env.BASE_URL` is Vite's own answer to the same question, set from `base`
// in vite.config.js at build time, so dev (`/`) and the deployed subpath (`/books/`)
// both come out right without a runtime switch or a second config to keep in step.
// It always ends in a slash; everything here wants it without one.
export const BASE_PATH = (import.meta.env.BASE_URL || '/').replace(/\/$/, '');

/** A path under the app's own mount point. Pass a leading slash: asset('/ambience/x.mp3'). */
export const asset = (path) => `${BASE_PATH}${path}`;
