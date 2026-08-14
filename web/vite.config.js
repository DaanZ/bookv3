import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The built bundle is served by the FastAPI app (api/main.py mounts web/dist), so the
// frontend always talks to a relative /api — in dev that is proxied to uvicorn.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});
