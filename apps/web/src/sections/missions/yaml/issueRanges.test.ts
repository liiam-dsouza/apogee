import { describe, expect, it } from 'vitest'
import { issueRange, parseIssuePath } from './issueRanges'

const YAML = `meta:
  name: Lanius
rocket:
  fins:
    - count: 4
      span_m: -1
motor:
  grains:
    count: 0
`

describe('parseIssuePath', () => {
  it('splits keys and indices', () => {
    expect(parseIssuePath('rocket.fins[1].span_m')).toEqual(['rocket', 'fins', 1, 'span_m'])
    expect(parseIssuePath('schema_version')).toEqual(['schema_version'])
  })
})

describe('issueRange', () => {
  it('covers a scalar with its key', () => {
    expect(issueRange(YAML, 'rocket.fins[0].span_m')).toEqual({
      startLineNumber: 6,
      startColumn: 7,
      endLineNumber: 6,
      endColumn: 17,
    })
  })

  it('skips segments the text does not have', () => {
    // Pydantic puts the union tag in the path; the YAML has no such key.
    expect(issueRange(YAML, 'motor.solid.grains.count').startLineNumber).toBe(9)
    // A missing required key lands on its parent.
    expect(issueRange(YAML, 'rocket.nose').startLineNumber).toBe(3)
  })

  it('falls back to the first line', () => {
    expect(issueRange(YAML, '').startLineNumber).toBe(1)
    expect(issueRange('[unclosed', 'meta.name').startLineNumber).toBe(1)
  })
})
