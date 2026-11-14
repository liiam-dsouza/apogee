import { isMap, isScalar, isSeq, LineCounter, parseDocument, type Node } from 'yaml'

export interface TextRange {
  startLineNumber: number
  startColumn: number
  endLineNumber: number
  endColumn: number
}

/** 'rocket.fins[1].span_m' -> ['rocket', 'fins', 1, 'span_m'] (the API's Issue.path format). */
export function parseIssuePath(path: string): (string | number)[] {
  const out: (string | number)[] = []
  for (const [, key, index] of path.matchAll(/([^.[\]]+)|\[(\d+)\]/g)) {
    out.push(index !== undefined ? Number(index) : key)
  }
  return out
}

/**
 * Where an issue's path points in the YAML text, as 1-based Monaco positions.
 * Walks as deep as the document goes: a path segment the text doesn't have
 * (a union tag like `motor.solid`, or a missing required key) is skipped, so
 * the range lands on the nearest thing that exists. Falls back to line 1.
 */
export function issueRange(text: string, path: string): TextRange {
  const lineCounter = new LineCounter()
  const doc = parseDocument(text, { lineCounter })
  let node: unknown = doc.contents
  let span: [number, number] | null = null

  for (const segment of parseIssuePath(path)) {
    if (isMap(node)) {
      const pair = node.items.find((p) => isScalar(p.key) && String(p.key.value) === String(segment))
      if (!pair) continue
      const key = pair.key as Node
      const value = pair.value as Node | null
      // A scalar value is highlighted with its key; a block only by its key.
      const end = value && isScalar(value) && value.range ? value.range[1] : key.range![1]
      span = [key.range![0], end]
      node = value
    } else if (isSeq(node) && typeof segment === 'number') {
      const item = node.items[segment] as Node | undefined
      if (!item?.range) continue
      span = [item.range[0], isScalar(item) ? item.range[1] : item.range[0] + 1]
      node = item
    }
  }

  if (!span) return { startLineNumber: 1, startColumn: 1, endLineNumber: 1, endColumn: 1 }
  const start = lineCounter.linePos(span[0])
  const end = lineCounter.linePos(Math.max(span[1], span[0] + 1))
  return { startLineNumber: start.line, startColumn: start.col, endLineNumber: end.line, endColumn: end.col }
}
