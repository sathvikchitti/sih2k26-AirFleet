import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// SSR-only build for the view render check. Swaps the data hooks module for a
// stub so views render synchronously with real API data (useEffect never runs
// during SSR, so the real hooks would leave every view stuck on "Loading").
const STUB = path.resolve('scripts/render-check/hooks-stub.jsx').replace(/\\/g, '/');

const hooksStub = {
  name: 'hooks-stub-alias',
  enforce: 'pre',
  resolveId(source, importer) {
    if (!importer) return null;
    // Only redirect the real hooks module, never the stub's own imports.
    const resolved = path.resolve(path.dirname(importer), source).replace(/\\/g, '/');
    if (resolved.endsWith('/src/services/hooks.js')) return STUB;
    return null;
  },
};

export default defineConfig({
  plugins: [hooksStub, react()],
// Render checks are deterministic and do not require a running backend. The
// fallback is allowed only in this same-origin/offline harness and is clearly
// marked as illustrative by the application; live API contracts are covered
// by the focused API contract test and browser rehearsal.
  define: {
    'import.meta.env.VITE_API_BASE': JSON.stringify(''),
  },
  build: {
    ssr: 'scripts/render-check/entry.jsx',
    outDir: 'dist-render-check',
    emptyOutDir: true,
    minify: false,
    // Top-level await (used to preload real API data) needs a modern target.
    target: 'esnext',
  },
});
