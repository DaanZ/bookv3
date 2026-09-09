import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The built bundle is served by the FastAPI app (api/main.py mounts web/dist), so the
// frontend always talks to a relative /api — in dev that is proxied to uvicorn.
export default defineConfig({
  // Where the app will be served from. Dev and the production root are both '/'; the
  // deploy under singularitynexus.nl/books sets PUBLIC_BASE=/books/ so every emitted
  // asset URL, and `import.meta.env.BASE_URL` with it, carries the prefix. Must end
  // in a slash — Vite joins it to filenames without inserting one.
  base: process.env.PUBLIC_BASE || '/',
  plugins: [react()],
  server: {
    // Whatever port the harness assigns, falling back to the usual one. Nothing here is
    // pinned to 5173: the app talks to a relative /api through the proxy below, so no
    // callback URL or CORS origin depends on the number.
    port: Number(process.env.PORT) || 5173,
    proxy: {
      // The API's port is pinned rather than assigned, because this target has to
      // agree with it and a proxy cannot discover a port chosen at launch. 8000 was
      // the obvious number and is taken on this machine by an unrelated service, so
      // the pair moved together to 8001. `API_PORT` overrides both if it ever clashes
      // again — the number matters to nothing but this line.
      '/api': {
        target: `http://127.0.0.1:${process.env.API_PORT || 8001}`,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});
