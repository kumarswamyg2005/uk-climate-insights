# Test strategy

Everything runs with `pytest` against real Postgres 16 (docker compose locally, a service container
in CI). The DB-level unique constraint and `ON CONFLICT` upserts are therefore exercised for real,
not emulated. No test touches the network: Met Office HTTP is mocked with `responses`, and the LLM
with a fake `LLMClient`.

Coverage gate: **85% line + branch on `climate/`** (`fail_under` in `pyproject.toml`, enforced in CI).

## Pyramid

| Layer | Share | Speed | What it protects |
|---|---|---|---|
| Unit (no DB) | parser, URL building, retry policy, tool schemas, chat loop with a fake client | ms | data correctness, edge cases |
| Integration (DB + Django test client) | ingest, models, every API endpoint, chat endpoint, admin, pages | ~1 s total | invariants, HTTP contract, failure codes |
| Smoke (container) | `docker compose up --build`, `/healthz`, one API call | minutes, manual + release checklist | the deployable artifact |

## Plan by area

| Area | Type | Must cover | Invariant |
|---|---|---|---|
| `parsing.py` | unit, **real fixtures** | observation count per fixture equals a manual count (for example Tmax UK: 143 x 17 - 1 `---` - 6 blank = 2424); `---` gives no row; blank cells in the partial current year give no row and don't shift columns; negative values; header found when the preamble length changes; `ParseError` with line number for misaligned or non-numeric values, duplicate years, no header, no data | 1 |
| `fetching.py` | unit | URL pattern; User-Agent sent; retries 5xx/429/connection errors then succeeds; 404 not retried | 14 |
| `ingest.py` + command | integration | run twice gives the same count (idempotent); changed value updated, not duplicated; withdrawn value pruned; one 404 gives run `partial` with other files stored; all failing gives `failed`; parse error leaves existing rows untouched; provenance set; command filters and rejects unknown codes | 2, 5, 6 |
| models | integration | unique key and period check enforced by Postgres (bypassing the ORM's validation) | 3 |
| API | integration | happy path per endpoint; unknown region/parameter/period gives 400 listing valid values; `year_from > year_to` gives 400; >4 compare regions gives 400; empty gives 200 `[]`; pagination; CSV content type and header row; compare aligns years with nulls; summary extremes match the fixture; units in every value response; non-GET gives 405 | 4, 7, 8 |
| chat | unit + integration | tools reject bad args; service runs tool calls with a fake client and returns grounded `data`; an ungrounded numeric answer is replaced; max rounds; no key gives 503; provider rate limit or timeout gives 503; throttle gives 429; long input gives 400; history can't inject `system`/`tool` roles | 9-12 |
| pages | smoke | `/`, `/compare/`, `/about/`, `/healthz`, `/api/docs/` return 200 | - |

## Deliberately not tested

- Chart rendering and DOM behaviour in the browser. They're verified by hand against DESIGN.md.
  A Playwright suite is the next step if the UI grows.
- The live Met Office and Groq APIs. The real ingest and three live chat questions are part of the
  release checklist instead, so CI stays deterministic and offline.
