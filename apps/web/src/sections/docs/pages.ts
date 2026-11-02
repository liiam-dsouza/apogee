/**
 * The repo's docs/ folder, bundled at build time (the `@docs` alias, see
 * vite.config.ts), so the documentation works offline wherever the app does.
 */
import { marked, type Tokens } from 'marked'

export interface DocPage {
  /** Path under docs/ without `.md`, e.g. `methods/weather`. */
  slug: string
  group: DocGroup
  title: string
  body: string
}

export type DocGroup = 'start' | 'guides' | 'methods' | 'reference' | 'architecture' | 'adr' | 'validation'

/** Contents order. Unknown folders fall into Reference. */
export const GROUPS: { id: DocGroup; label: string }[] = [
  { id: 'start', label: 'Start here' },
  { id: 'guides', label: 'Guides' },
  { id: 'methods', label: 'Methods' },
  { id: 'reference', label: 'Reference' },
  { id: 'architecture', label: 'Architecture' },
  { id: 'adr', label: 'Decisions (ADRs)' },
  { id: 'validation', label: 'Validation' },
]

export const HOME = 'start-here'

const raw = import.meta.glob<string>('@docs/**/*.md', { query: '?raw', import: 'default', eager: true })

function groupOf(slug: string): DocGroup {
  const folder = slug.includes('/') ? slug.split('/')[0] : 'start'
  return (GROUPS.some((g) => g.id === folder) ? folder : 'reference') as DocGroup
}

export const PAGES: DocPage[] = Object.entries(raw)
  .map(([path, body]) => {
    const slug = path.replace(/^.*?\/docs\//, '').replace(/\.md$/, '')
    const title = /^#\s+(.+)$/m.exec(body)?.[1].trim() ?? slug
    return { slug, group: groupOf(slug), title, body }
  })
  // Start here first, then by file name (ADRs are numbered, so they stay in order).
  .sort((a, b) => (a.slug === HOME ? -1 : b.slug === HOME ? 1 : a.slug.localeCompare(b.slug)))

export const PAGE_BY_SLUG = new Map(PAGES.map((p) => [p.slug, p]))

/**
 * Where a link written in a docs page points in the app. Relative links to other
 * pages become `/docs/...`; links to repo files that are not docs have no page
 * and return null; absolute URLs and in-app paths are left alone.
 */
export function resolveDocLink(fromSlug: string, href: string): string | null {
  if (/^[a-z]+:/i.test(href) || href.startsWith('/') || href.startsWith('#')) return href
  const [path, hash] = href.split('#')
  const parts = fromSlug.split('/').slice(0, -1)
  for (const seg of path.split('/')) {
    if (seg === '..') {
      if (parts.length === 0) return null // leaves docs/: a repo file, not a page
      parts.pop()
    } else if (seg && seg !== '.') parts.push(seg)
  }
  const slug = parts.join('/').replace(/\.md$/, '')
  if (!PAGE_BY_SLUG.has(slug)) return null
  return `/docs/${slug}${hash ? `#${hash}` : ''}`
}

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/<[^>]+>/g, '')
    .replace(/[^\w\s-]/g, '')
    .trim()
    .replace(/\s+/g, '-')
}

/** The page as HTML, with links rewritten for the app and ids on headings. */
export function renderDoc(page: DocPage): string {
  const renderer = new marked.Renderer()
  const link = renderer.link.bind(renderer)
  renderer.link = (token: Tokens.Link) => {
    const to = resolveDocLink(page.slug, token.href)
    if (to === null) return `<span class="doc-repo-path" title="${token.href}">${renderer.parser.parseInline(token.tokens)}</span>`
    const html = link({ ...token, href: to })
    return /^https?:/.test(to) ? html.replace('<a ', '<a target="_blank" rel="noreferrer" ') : html
  }
  renderer.heading = ({ tokens, depth }: Tokens.Heading) => {
    const text = renderer.parser.parseInline(tokens)
    return `<h${depth} id="${slugify(text)}">${text}</h${depth}>\n`
  }
  return marked.parse(page.body, { renderer, async: false })
}

/** Pages matching every word of the query, title matches first, with a snippet of the body. */
export function searchDocs(query: string): { page: DocPage; snippet: string }[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean)
  if (words.length === 0) return []
  return PAGES.filter((p) => words.every((w) => `${p.title}\n${p.body}`.toLowerCase().includes(w)))
    .map((page) => {
      const lower = page.body.toLowerCase()
      const at = Math.max(0, lower.indexOf(words[0]))
      const snippet = page.body
        .slice(Math.max(0, at - 40), at + 100)
        .replace(/[#*`|[\]]/g, '')
        .replace(/\s+/g, ' ')
        .trim()
      const inTitle = words.every((w) => page.title.toLowerCase().includes(w))
      return { page, snippet, inTitle }
    })
    .sort((a, b) => Number(b.inTitle) - Number(a.inTitle))
}
