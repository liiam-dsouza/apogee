// A local entry for monaco-yaml's worker, so the dev server serves the copy it
// pre-bundled (optimizeDeps in vite.config.ts): several of the worker's
// dependencies are CommonJS, which a worker can't load unbundled.
import 'monaco-yaml/yaml.worker.js'
