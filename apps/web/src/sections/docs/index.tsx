import { Search } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { cn } from '@/lib/utils'
import { GROUPS, HOME, PAGE_BY_SLUG, PAGES, renderDoc, searchDocs } from './pages'
import { useSectionLayout } from '@/app/sectionLayout'

function useSlug(): string {
  const rest = useParams()['*']
  return rest ? rest.replace(/\/$/, '') : HOME
}

export function Centre() {
  const slug = useSlug()
  const page = PAGE_BY_SLUG.get(slug)
  const html = useMemo(() => (page ? renderDoc(page) : ''), [page])
  const navigate = useNavigate()
  const scroller = useRef<HTMLDivElement>(null)

  // A new page starts at its top, or at the heading its link named.
  useEffect(() => {
    const hash = decodeURIComponent(window.location.hash.slice(1))
    const target = hash ? document.getElementById(hash) : null
    if (target) target.scrollIntoView()
    else scroller.current?.scrollTo({ top: 0 })
  }, [slug])

  if (!page) {
    return (
      <div className="space-y-4 p-6 md:p-10">
        <p className="max-w-[46ch] font-display text-2xl leading-snug font-medium text-muted-foreground md:text-3xl">
          This page isn't written yet.
        </p>
        <p className="text-sm text-muted-foreground">
          <code>docs/{slug}.md</code> doesn't exist. Every section's method is documented once that section is built.
        </p>
        <Link to={`/docs/${HOME}`} className="text-primary underline-offset-4 hover:underline">
          Start here
        </Link>
      </div>
    )
  }

  return (
    <div ref={scroller} className="h-full overflow-y-auto">
      <article
        className="doc-prose mx-auto max-w-3xl px-6 py-8 md:px-10"
        // Docs are the repo's own Markdown, bundled at build time; nothing user-supplied.
        dangerouslySetInnerHTML={{ __html: html }}
        onClick={(e) => {
          const a = (e.target as HTMLElement).closest('a')
          const href = a?.getAttribute('href')
          if (!a || !href || a.target === '_blank' || e.metaKey || e.ctrlKey) return
          if (href.startsWith('#')) return
          if (href.startsWith('/') && !href.startsWith('/api/')) {
            e.preventDefault()
            navigate(href)
          }
        }}
      />
    </div>
  )
}

export function Pane() {
  const layout = useSectionLayout()
  const slug = useSlug()
  const [query, setQuery] = useState('')
  const results = useMemo(() => searchDocs(query), [query])

  return (
    // On a phone, picking a page shows it.
    <nav
      aria-label="Documentation"
      className="space-y-5 p-4"
      onClick={(e) => {
        if ((e.target as HTMLElement).closest('a[href^="/docs/"]')) layout.showCentre()
      }}
    >
      <label className="flex h-9 items-center gap-2 rounded-md border border-border bg-background px-3 focus-within:border-primary">
        <Search className="size-4 text-muted-foreground" aria-hidden />
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search the docs"
          aria-label="Search the docs"
          className="h-full min-w-0 flex-1 bg-transparent text-sm outline-none"
        />
      </label>

      {query.trim() ? (
        <ul className="space-y-3" aria-live="polite">
          {results.length === 0 && <li className="text-sm text-muted-foreground">Nothing matches.</li>}
          {results.map(({ page, snippet }) => (
            <li key={page.slug}>
              <Link to={`/docs/${page.slug}`} className="text-sm text-primary underline-offset-4 hover:underline">
                {page.title}
              </Link>
              <p className="line-clamp-2 text-xs text-muted-foreground">{snippet}</p>
            </li>
          ))}
        </ul>
      ) : (
        <>
          {GROUPS.map((g) => {
            const pages = PAGES.filter((p) => p.group === g.id)
            if (pages.length === 0) return null
            return (
              <section key={g.id} className="space-y-1">
                <h2 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">{g.label}</h2>
                <ul>
                  {pages.map((p) => (
                    <li key={p.slug}>
                      <Link
                        to={`/docs/${p.slug}`}
                        aria-current={p.slug === slug ? 'page' : undefined}
                        className={cn(
                          'block rounded px-2 py-1 text-sm',
                          p.slug === slug ? 'bg-surface text-foreground' : 'text-muted-foreground hover:text-foreground',
                        )}
                      >
                        {p.title}
                      </Link>
                    </li>
                  ))}
                </ul>
              </section>
            )
          })}
          <section className="space-y-1">
            <h2 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">API</h2>
            <a href="/api/docs" target="_blank" rel="noreferrer" className="block px-2 py-1 text-sm text-muted-foreground hover:text-foreground">
              API reference (OpenAPI)
            </a>
          </section>
        </>
      )}
    </nav>
  )
}
