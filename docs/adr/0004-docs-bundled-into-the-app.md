# 0004: The docs are bundled into the app

**Status:** accepted, 2026-11-02

## Context

The brief asks for a docs site (MkDocs Material or Docusaurus) served from the
stack, so it works offline in the field, and for every section's "what this
does" panel to link to its methods page.

## Decision

The Markdown in `docs/` is the single source. The web app bundles it at build
time (Vite's `import.meta.glob`, through the `@docs` alias) and renders it in
the **Docs** section with `marked`. Links between pages are rewritten to in-app
routes (`/docs/methods/weather`). The pages also read normally on any Git host.

## Consequences

- Works offline wherever the app works, with no extra service or build step.
- A methods link from a section opens in place, keeping the user's mission open.
- Docs ship with the build: a docs change needs a rebuild of the web image.
- No versioned docs, theming or plugins; search is a simple text match.

## Rejected

- **MkDocs in its own container.** Another service and build to keep alive, and
  links out of the app lose its state. Worth revisiting if the docs outgrow
  this: the Markdown would move across unchanged.
