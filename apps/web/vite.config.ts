/// <reference types="vitest/config" />
import { fileURLToPath, URL } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

/** The repo's docs/, bundled into the Docs section. The Docker build copies it to /docs. */
const DOCS_DIR = process.env.APOGEE_DOCS_DIR ?? fileURLToPath(new URL('../../docs', import.meta.url))

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)), '@docs': DOCS_DIR },
  },
  build: {
    rolldownOptions: {
      output: {
        // The MapLibre worker ships as .mjs. Emit it as .js: every server types .js as
        // JavaScript (nginx's stock table has no .mjs, which stopped all map layers),
        // and the new name escapes any year-long cached copy of the mistyped .mjs.
        assetFileNames: (asset) =>
          asset.names.some((n) => n.endsWith('.mjs')) ? 'assets/[name]-[hash].js' : 'assets/[name]-[hash][extname]',
      },
    },
  },
  server: {
    // The browser talks only to the API; in dev, proxy to a local uvicorn.
    proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } },
    fs: { allow: ['.', DOCS_DIR] },
  },
  test: {
    environment: 'jsdom',
    // e2e/ is Playwright's.
    include: ['src/**/*.test.{ts,tsx}'],
    // The persistent transform cache keeps an import.meta.glob's file list, so a new
    // docs page stays invisible to tests (the docs link check then fails, or passes
    // without checking it). The suite is small; transform every run.
    fsModuleCache: false,
  },
})
