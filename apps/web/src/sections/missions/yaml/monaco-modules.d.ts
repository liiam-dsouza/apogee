// Monaco's core-editor entrypoint ships without types; its API is editor.api's.
declare module 'monaco-editor/esm/vs/editor/edcore.main.js'

// The pre-0.55 createWebWorker({ label, moduleId, createData }), kept as its own export.
declare module 'monaco-editor/esm/vs/common/workers.js' {
  import type { editor } from 'monaco-editor/esm/vs/editor/editor.api.js'
  export function createWebWorker<T extends object>(opts: {
    label?: string
    moduleId?: string
    createData?: unknown
    host?: Record<string, Function>
    keepIdleModels?: boolean
  }): editor.MonacoWebWorker<T>
}
