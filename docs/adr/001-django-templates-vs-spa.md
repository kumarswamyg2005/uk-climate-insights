# ADR-001: Django templates + vanilla JS instead of a React SPA

**Status:** Accepted
**Date:** 2026-09-25
**Deciders:** Kumaraswamy

## Context

The assignment asks for a frontend for data access and visualisation. The screens are small: an
explorer (controls, stripes, one chart, stats, table, chat), a compare page and an about page. The
same data must also be served through a public REST API, and the whole thing ships as one Docker
image to a free-tier host. One developer, 3-4 days.

## Decision

Render page shells with Django templates, and load all data in the browser with vanilla JavaScript
calling our own `/api/v1/` endpoints. Chart.js is vendored into `static/` (no CDN). There is no
bundler or build step.

## Options considered

### Option A: Django templates + vanilla JS on the public API (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low: plain ES modules, no toolchain |
| Cost | One container; whitenoise serves static files |
| Scalability | Fine for 3 pages; would strain past ~10 interactive views |
| Team familiarity | High: plain Django and DOM APIs |

**Pros:** one deployable and one language toolchain. The UI dogfoods the public API, so every chart
proves an endpoint works. Pages render and are keyboard-usable before JS loads, and they're fast on
cold starts.
**Cons:** manual DOM updates, no component model, and state handling is hand-written (URL params
are the state store).

### Option B: React (Vite) SPA served separately or from Django static

| Dimension | Assessment |
|---|---|
| Complexity | Medium-high: Node toolchain, bundling, a second Docker stage, CORS or proxying |
| Cost | Extra build stage; possibly a second service |
| Scalability | Better for a large, stateful UI |
| Team familiarity | High, but more surface to explain and maintain |

**Pros:** component reuse and a richer interaction model.
**Cons:** doubles the build and deploy surface for three pages. It's also more code to defend in a
review, for no user-visible gain here.

### Option C: Server-rendered HTML with no API calls (Django views render the charts' data inline)

**Pros:** fewest requests.
**Cons:** the UI would no longer exercise the API. The chart data would be duplicated between views
and API, and sharing or CSV would need separate paths.

## Trade-off analysis

The deciding factor is surface area against need. The interactive state is a handful of `<select>`
values plus a year range, and a query string models that exactly: shareable URLs come for free.
A SPA pays a fixed tax (toolchain, second build, bundle size) that only amortises over many views.
Calling our own API from the templates keeps the one real benefit of an SPA split: a clean API
contract that other clients can use.

## Consequences

- Easier: one image, one deploy, no Node in CI, URLs are shareable by construction.
- Harder: complex client state (e.g. a draggable time brush) would need hand-written code.
- Revisit: if the UI grows past a few views or needs offline or real-time features, move to a
  component framework consuming the same `/api/v1/`, which doesn't change.

## Action items

1. [ ] Vendor Chart.js and self-host fonts under `climate/static/`.
2. [ ] Keep all data access in JS going through `/api/v1/` (no inline JSON data dumps in templates).
