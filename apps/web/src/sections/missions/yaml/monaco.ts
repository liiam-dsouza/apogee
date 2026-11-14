/**
 * Monaco, set up once for mission YAML: bundled workers (no CDN, so it works
 * offline), schema-aware completion, hover and validation from the generated
 * OpenAPI schema (monaco-yaml), our snippets, and a theme read from the app's
 * CSS tokens. Only the YAML editor imports this, so it stays in a lazy chunk.
 */
// The core editor and its features, without the bundled JSON, CSS, HTML and
// TypeScript language services (and their multi-megabyte workers).
import 'monaco-editor/esm/vs/editor/edcore.main.js'
import * as monaco from 'monaco-editor/esm/vs/editor/editor.api.js'
import 'monaco-editor/esm/vs/basic-languages/yaml/yaml.contribution.js'
import { createWebWorker as createLegacyWebWorker } from 'monaco-editor/esm/vs/common/workers.js'
import EditorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker'
import { configureMonacoYaml, type JSONSchema } from 'monaco-yaml'
import YamlWorker from './yaml.worker?worker'
import openapi from '../../../../openapi.json'
import { SNIPPETS } from './snippets'

export { monaco }

/** Models are named after the mission, so the schema can match them by glob. */
export const modelUri = (missionId: string) => monaco.Uri.parse(`file:///missions/${missionId}.mission.yaml`)

window.MonacoEnvironment = {
  getWorker: (_id, label) => (label === 'yaml' ? new YamlWorker() : new EditorWorker()),
}

// The OpenAPI document's refs are '#/components/schemas/…', so the Mission
// schema keeps the components alongside it to resolve them.
const missionSchema = {
  ...openapi.components.schemas.Mission,
  components: { schemas: openapi.components.schemas },
} as unknown as JSONSchema

// monaco-yaml's worker manager calls editor.createWebWorker({ label, moduleId,
// createData }), the pre-0.55 signature. Monaco 0.55 keeps that form as a
// separate export, so hand monaco-yaml an editor namespace that uses it.
const monacoForYaml = { ...monaco, editor: { ...monaco.editor, createWebWorker: createLegacyWebWorker } }

configureMonacoYaml(monacoForYaml as typeof monaco, {
  enableSchemaRequest: false,
  schemas: [{ uri: 'apogee://schemas/mission.json', fileMatch: ['**/*.mission.yaml'], schema: missionSchema }],
})

monaco.languages.registerCompletionItemProvider('yaml', {
  provideCompletionItems: (model, position) => {
    const word = model.getWordUntilPosition(position)
    // Snippet prefixes have hyphens, which aren't word characters in YAML.
    const line = model.getLineContent(position.lineNumber).slice(0, position.column - 1)
    const typed = /[\w-]*$/.exec(line)![0]
    const range = new monaco.Range(position.lineNumber, position.column - typed.length, position.lineNumber, word.endColumn)
    return {
      suggestions: SNIPPETS.map((s) => ({
        label: { label: s.prefix, description: s.label, detail: `  ${s.detail}` },
        kind: monaco.languages.CompletionItemKind.Snippet,
        insertText: s.body,
        insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
        documentation: { value: '```yaml\n' + s.body.replace(/\$\{\d+(?::([^}]*)|\|([^,|]*)[^}]*\|)\}/g, '$1$2') + '\n```' },
        range,
      })),
    }
  },
})

/** A 6-digit hex token with an alpha suffix, e.g. selection highlights. */
const alpha = (hex: string, a: number) => hex + Math.round(a * 255).toString(16).padStart(2, '0')

/** (Re)define the 'apogee' theme from the current CSS tokens: dark, light or pink. */
export function applyTheme() {
  const css = getComputedStyle(document.documentElement)
  const t = (name: string) => css.getPropertyValue(`--${name}`).trim()
  const dark = css.colorScheme !== 'light'
  const strip = (hex: string) => hex.replace('#', '')

  monaco.editor.defineTheme('apogee', {
    base: dark ? 'vs-dark' : 'vs',
    inherit: true,
    // Each rule names the .yaml token too: the built-in light theme has its own
    // string.yaml colour, which would beat a plain 'string' rule.
    rules: [
      { token: '', foreground: strip(t('foreground')) },
      ...[
        ['type', t('foreground')],
        ['string', t('hazard')],
        ['number', t('primary')],
        ['keyword', t('caution')],
        ['operators', t('muted-foreground')],
        ['delimiter', t('muted-foreground')],
      ].flatMap(([token, color]) => [
        { token, foreground: strip(color) },
        { token: `${token}.yaml`, foreground: strip(color) },
      ]),
      { token: 'comment', foreground: strip(t('muted-foreground')), fontStyle: 'italic' },
      { token: 'comment.yaml', foreground: strip(t('muted-foreground')), fontStyle: 'italic' },
    ],
    colors: {
      'editor.background': t('background'),
      'editor.foreground': t('foreground'),
      'editor.lineHighlightBackground': t('surface'),
      'editor.lineHighlightBorder': t('surface'),
      'editor.selectionBackground': alpha(t('primary'), 0.3),
      'editor.inactiveSelectionBackground': alpha(t('primary'), 0.15),
      'editor.wordHighlightBackground': alpha(t('muted-foreground'), 0.2),
      'editorCursor.foreground': t('primary'),
      'editorLineNumber.foreground': alpha(t('muted-foreground'), 0.6),
      'editorLineNumber.activeForeground': t('foreground'),
      'editorIndentGuide.background1': t('surface-2'),
      'editorIndentGuide.activeBackground1': t('border'),
      'editorGutter.background': t('background'),
      'editorWidget.background': t('surface-2'),
      'editorWidget.border': t('border'),
      'editorHoverWidget.background': t('surface-2'),
      'editorHoverWidget.border': t('border'),
      'editorSuggestWidget.background': t('surface-2'),
      'editorSuggestWidget.border': t('border'),
      'editorSuggestWidget.selectedBackground': alpha(t('primary'), 0.2),
      'editorSuggestWidget.highlightForeground': t('primary'),
      'editorSuggestWidget.focusHighlightForeground': t('primary'),
      'list.hoverBackground': t('surface'),
      'focusBorder': alpha(t('primary'), 0.6),
      'input.background': t('surface'),
      'input.border': t('border'),
      'editorError.foreground': t('nogo'),
      'editorWarning.foreground': t('caution'),
      'editorBracketMatch.background': alpha(t('primary'), 0.15),
      'editorBracketMatch.border': alpha(t('primary'), 0.5),
      'scrollbarSlider.background': alpha(t('muted-foreground'), 0.2),
      'scrollbarSlider.hoverBackground': alpha(t('muted-foreground'), 0.35),
      'scrollbarSlider.activeBackground': alpha(t('muted-foreground'), 0.5),
      'editorOverviewRuler.border': t('background'),
      'editorStickyScroll.background': t('background'),
      'editorStickyScrollHover.background': t('surface'),
    },
  })
  monaco.editor.setTheme('apogee')
}
