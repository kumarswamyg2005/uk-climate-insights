# Walkthrough

A guided tour of the codebase, for someone about to explain or change it. It starts with the
problem, then follows a request through every layer, then covers the decisions, the edge cases,
operations and the questions a reviewer is likely to ask.

## 1. The problem and the data

The Met Office publishes long-running climate records for the UK and 16 sub-regions: monthly
average temperatures, rainfall totals, sunshine hours, rain days and frost days. The records go
back as far as 1836. Each region and measure is one text file, and there are 17 x 7 = 119 of them.
A row is a year; the 17 columns are the 12 months, the 4 seasons and the annual value.

```
year    jan    feb  ...    dec     win     spr     sum     aut     ann
1884    7.3    6.8  ...    5.8     ---   11.02   18.73   12.10   12.14
...
2026    6.0    7.9  ...                  7.43   13.87   21.31
```

The values are averages over a whole region, computed by the Met Office from a 1 km grid. They
aren't readings from one weather station.

The assignment: parse these files, store them, serve them over a REST API, show them in a web UI,
put it in Docker and on a public cloud, and add an LLM chat that answers questions from the stored
data.

## 2. The big picture

```
Met Office .txt files
   │  fetching.py (requests + tenacity, polite)
   ▼
parsing.py (fixed-width, column by right edge)  ──►  ParseError(line) on anything odd
   │
   ▼
ingest.py (one transaction per file: upsert + prune)  ──►  IngestionRun (status, errors)
   │
   ▼
PostgreSQL: Region, Parameter, Observation, IngestionRun
   │
   ▼
queries.py (validate args against catalog whitelists, then ORM)
   ├──► api/views.py (DRF)  ──►  JSON / CSV  ──►  browser JS (Chart.js)  and anyone with curl
   └──► chat/tools.py  ◄──  chat/service.py (tool loop)  ◄──►  Groq LLM
```

Two ideas hold it together:

1. **`catalog.py` is the single list of valid codes.** The ingest copies it into the database, and
   every validator is built from it.
2. **`queries.py` is the single read path.** The REST views and the LLM tools both call the same
   functions, and those functions validate their own inputs. Nothing reaches the ORM without
   passing the same checks.

## 3. Request lifecycles

### Explorer page

1. The browser requests `/?region=Scotland&parameter=Rainfall&period=ann`.
2. `climate/views.py::explorer` renders `explorer.html`. The region, measure and period dropdowns
   come from `catalog.py` and `periods.py`. Values from the query string pre-select them, but only
   if they're on the whitelist. Anything else falls back to defaults.
3. `explorer.js` reads the form, writes the selection back into the URL (`history.replaceState`,
   so the URL is always shareable) and fetches `GET /api/v1/series/?...` and `GET /api/v1/summary/?...`
   in parallel. A request counter drops out-of-order responses if the user changes the selection
   quickly.
4. `api/views.py::SeriesView` calls `queries.get_series(request.query_params)`.
5. `get_series` validates the params with the `SeriesQuery` serializer: region, parameter and
   period must be catalog codes, years must be whole numbers within bounds, and `year_from` can't
   be after `year_to`. A failure raises DRF's `ValidationError`, which DRF turns into a 400 listing
   the valid values.
6. `_rows()` runs one query: `WHERE region.code = ? AND parameter.code = ? AND period = ? ORDER BY
   year`. Postgres answers it from the `observation_series` index (`region, parameter, period,
   year`) in under a millisecond.
7. The JSON comes back as `{unit, points: [[year, value], ...]}`. The JS draws the stripes (one
   colour per year from the value's deviation from the mean) and the Chart.js line, then fills the
   stat rows and the table.

### Chat

1. `chat.js` POSTs `{message, history}` to `/api/v1/chat/`.
2. `ChatView` applies DRF's throttle (10 a minute per client IP), then validates the body. The
   message is capped at 500 characters. History is at most 6 turns of at most 1,000 characters,
   and roles can only be `user` or `assistant`, so nobody can inject a `system` message.
3. `service.answer()` builds the messages: a system prompt (rules, codes, and the real year ranges
   from the database), the history, and the question.
4. `GroqClient.complete()` sends them with six tool schemas. The model replies with either text or
   tool calls, for example `get_extreme(region=Wales, parameter=Tmean, period=win, kind=min)`.
5. For each tool call, `tools.run_tool()` parses the JSON arguments and calls the matching
   `queries` function, which validates them exactly as it would for the REST API. Invalid
   arguments come back to the model as an error message, so it can correct itself.
6. The rows go back to the model as a `role: tool` message, and the loop repeats (at most 5
   rounds, with a 30-second deadline).
7. When the model answers in text, `_grounded()` checks one rule in code: if the answer contains
   numbers but no tool call succeeded, it's replaced with a refusal.
8. The response is `{answer, model, tool_calls, data}`. The UI shows the answer and, collapsed,
   the exact rows under "Data used".

## 4. The files

| Path | What it does | Why it exists |
|---|---|---|
| `config/settings/base.py` | shared settings: apps, middleware, DRF, throttle rates, LLM settings | one place for everything that doesn't vary |
| `config/settings/dev.py` | safe defaults so a fresh clone runs; plain static storage | local development and tests |
| `config/settings/prod.py` | `SECRET_KEY` and `DATABASE_URL` required from env, `DEBUG` forced off, HTTPS cookies, HSTS, proxy header | production must fail loudly if misconfigured |
| `config/urls.py` | pages, admin, `/healthz`, `/api/v1/`, schema and docs | |
| `climate/catalog.py` | the 17 regions and 7 parameters, with names, units and descriptions | the one whitelist |
| `climate/periods.py` | the 17 period codes in file order, with labels | shared by parser, models and UI |
| `climate/invariants.py` | the 14 rules as a comment block, plus the limits they refer to | makes the rules reviewable; each is tested |
| `climate/models.py` | `Region`, `Parameter`, `IngestionRun`, `Observation` with constraints and index | |
| `climate/parsing.py` | text to `ParsedSeries(records, preamble, last_updated)` | the graded parsing item |
| `climate/fetching.py` | URL builder, session with User-Agent, retries | polite and resilient downloads |
| `climate/ingest.py` | `run_ingest()`, catalog sync, upsert + prune, background runner | orchestration and failure isolation |
| `climate/management/commands/ingest_metoffice.py` | CLI with `--regions`, `--parameters`, `--if-needed`, summary table | cron, Docker entrypoint, humans |
| `climate/admin.py` | read-only admin plus the **Run ingest now** button | browse data and trigger a refresh |
| `climate/queries.py` | validators and read functions: series, summary, extremes, compare | the shared read path |
| `climate/api/` | DRF views, output and doc serializers, django-filter set, URLs | the REST API and its OpenAPI schema |
| `climate/chat/llm.py` | `LLMClient` protocol, `GroqClient`, `LLMUnavailable` | swappable provider; tests use a fake |
| `climate/chat/tools.py` | tool JSON schemas and `run_tool()` dispatch | the only things the model can do |
| `climate/chat/service.py` | system prompt, tool loop, grounding guard | the chat logic |
| `climate/views.py` | explorer, compare, about pages; `/healthz` | server-rendered shells |
| `climate/templates/`, `climate/static/` | HTML, CSS (DESIGN.md tokens), JS, vendored Chart.js, fonts | the frontend |
| `Dockerfile`, `docker/entrypoint.sh`, `docker-compose.yml` | image, boot sequence, local stack | |
| `render.yaml` | the Render Blueprint | deployment as code |
| `tests/` | 208 tests, real Met Office fixtures | |

## 5. Decisions and what was rejected

**Django templates + vanilla JS, not React.** There are three pages. The state is a few dropdowns,
and a query string holds that. A React build would add Node, a bundler and a second deploy
artifact for no visible gain. The JS still calls the public API, so every chart also tests the API.
([ADR-001](adr/001-django-templates-vs-spa.md))

**Tool calling, not text-to-SQL.** The chat is public and anonymous, so every message is untrusted.
With text-to-SQL, a clever prompt becomes a clever query. With tools, the model can only call six
read-only functions whose arguments are checked against whitelists. The worst case is a wrong
answer, and the grounding guard and "Data used" make that visible.
([ADR-003](adr/003-llm-tool-calling-vs-text-to-sql.md))

**Upsert + prune, not delete-and-reload.** Delete-and-reload leaves a window where a series is
empty. If file 60 of 119 fails, those series are gone. Upsert on the unique key updates the
provisional current-year values in place. Pruning deletes rows the new file no longer has. Both
happen in one transaction per file, so readers see either the old series or the new one.
([ADR-002](adr/002-postgres-upsert-strategy.md))

**A hand-written parser, not pandas.** The format needs one thing: match each value to the header
column whose right edge it shares. That's about 40 lines of standard library. pandas is a 30 MB
dependency, and `read_fwf` infers column widths, which is exactly where the partial year goes
wrong. Every line of the parser can be explained and has a test.

**Render + Neon, not EC2 or Render Postgres.** Render gives HTTPS, Docker deploys from GitHub and a
free tier with no servers to manage. Render's free Postgres is deleted 30 + 14 days after creation,
which could fall inside the interview window, so the database is on Neon's free tier, in the same
region. EC2 would mean managing TLS, a proxy, patching and costs after 12 months.
([ADR-004](adr/004-render-web-neon-postgres.md))

**Smaller calls:**
- `Decimal(8, 2)` rather than float, so stored values equal the file's text.
- A second index `(region, parameter, period, year)`, because the unique index has `year` before
  `period` and can't serve "one period, ordered by year".
- One gunicorn process with four threads. The throttle counters live in process memory, so one
  process keeps them exact, and threads keep slow LLM calls from blocking page loads.
- Static files collected at image build time.
- Production ignores `.env` files completely.

## 6. Edge cases and how each is handled

| Edge case | Handling | Test |
|---|---|---|
| The partial current year has blank cells | values matched to columns by right edge; blank means no row | `test_partial_current_year_blank_cells_are_absent_and_nothing_shifts` |
| `---` in the first year's winter | treated as missing, never 0 | `test_dashes_mean_no_row_not_zero` |
| A real zero (July frost days) | kept as `0.0` | `test_real_zero_is_kept` |
| `-0.0` in the file | normalised to `0.0` | `test_negative_values_and_negative_zero` |
| Preamble length changes | header found by its column names | `test_header_is_found_by_its_names_not_its_line_number` |
| `NaN`, `n/a`, 3 decimals, bad or duplicate year | `ParseError` with line number; the file fails, others continue | `test_malformed_lines_raise_parse_error_with_line_number` |
| A file 404s or times out | 5xx/429/network retried 3x with backoff; 404 not retried; run ends `partial` | `test_one_missing_file_gives_a_partial_run...` |
| The Met Office revises a value | upsert updates it in place with new provenance | `test_changed_value_is_updated_in_place` |
| The Met Office withdraws a value | pruned in the same transaction | `test_value_withdrawn_from_the_source_is_pruned` |
| A DB error halfway through a file | that file's transaction rolls back | `test_database_error_in_one_file_rolls_back_only_that_file` |
| Winter spans two calendar years | stored under the January year, as the source does; explained in UI, prompt and about page | `test_values_are_read_from_the_right_columns` |
| Tied extremes (96 Julys with 0 frost days) | summary returns every tied year | `test_summary_reports_every_tied_year` |
| Empty selection | 200 with empty data; the UI shows DESIGN.md's empty copy | `test_series_with_no_data_is_an_empty_200` |
| Chat without a key, rate-limited, provider down | 503 with a clear message; the rest works | `test_chat_without_an_api_key_is_503_and_the_rest_still_works` |
| The model answers from memory | numbers with no data behind them are replaced | `test_numbers_without_any_data_behind_them_are_withheld` |

## 7. Operations

**Run locally:** `docker compose up --build`, then open http://localhost:8000. The first boot
downloads the data (about 2 minutes).

**Test:** `docker compose up -d db`, then `pytest --cov`, then `ruff check .`.

**Monthly refresh:** `.github/workflows/ingest.yml` runs `ingest_metoffice --strict` against the
production database on the 2nd of each month. A partial or failed run fails the job, and GitHub
emails the repository owner. It needs the `DATABASE_URL` repository secret.

**Re-ingest:** GitHub → Actions → Monthly Met Office ingest → Run workflow; or in
`/admin/climate/ingestionrun/` press **Run ingest now**; or run
`python manage.py ingest_metoffice`. It's safe to re-run at any time. To refresh one series, use
`--regions Wales --parameters Rainfall`.

**Deploy:** merge to `main`. Render rebuilds the image from `render.yaml` and swaps it in after the
`/healthz` check passes. Rolling back means redeploying the previous commit from the Render
dashboard.

**Rotate the Groq key:** create a new key at console.groq.com, paste it into Render → service →
Environment → `GROQ_API_KEY` (this triggers a redeploy), check the chat, then delete the old key in
Groq. For a local `.env`, write `GROQ_API_KEY=gsk_...` with no space after `=`.

**Rotate the database password:** reset the role password in the Neon console, then update
`DATABASE_URL` in Render.

## 8. Known limitations, and what to do with more time

- **Durable background jobs.** The admin button starts a thread. A job runner (RQ or Celery) would
  survive restarts and show progress properly.
- **Caching.** Responses only change after an ingest. An ETag based on the latest run id, or a
  per-view cache cleared by the ingest, would make repeat views free.
- **Conditional downloads.** The Met Office sends `ETag` and `Last-Modified`. Sending
  `If-None-Match` would skip unchanged files.
- **Auth and quotas** for the chat if it were public at scale: API keys or login, and daily quotas
  per user.
- **More sources.** Station data or HadUK-Grid would need a `source` dimension on observations.
- **Value history.** Revisions overwrite today. A history table would allow "what did we show
  last month".

## 9. Likely interview questions

**1. Why not split each line on whitespace?**
In the current year's row, months that haven't happened are blank, not `---`. Splitting on
whitespace would shift the winter value (7.43) into September, and nothing would error. The parser
maps each value to the header column whose right edge it shares, and a value that doesn't line up
raises `ParseError`.

**2. Why not pandas?**
The job is 40 lines of standard library, and `read_fwf` infers widths, which is fragile exactly on
the partial year. Keeping pandas out keeps the image small and the parser easy to explain line by
line.

**3. How is ingestion idempotent?**
A unique constraint on `(region, parameter, year, period)` in Postgres, plus `bulk_create(...,
update_conflicts=True)`, which compiles to `INSERT ... ON CONFLICT ... DO UPDATE`. Running twice
gives the same 279,208 rows; the second run just re-stamps provenance.

**4. What does the prune step do, and is it safe?**
After upserting a file, the ingest deletes rows of that region and parameter that this run didn't
write. They're values the Met Office no longer publishes. It happens in the same transaction as
the upsert, and a file that fails to fetch or parse never reaches it, so a bad download can't wipe
a series. A file with zero rows is treated as a parse error for the same reason.

**5. Why enforce uniqueness in the database rather than in Python?**
Application checks race and can be bypassed by a new code path. A constraint can't. Postgres also
needs a unique constraint as the conflict target for `ON CONFLICT`.

**6. Why two indexes?**
The unique index is `(region, parameter, year, period)`. Every read filters region, parameter and
period and orders by year. With `year` before `period`, the unique index can't serve that as one
range scan, so `(region, parameter, period, year)` exists for reads. `EXPLAIN ANALYZE` shows
0.5 ms for a 190-row series.

**7. What happens if a Met Office file is down or changes format?**
Network errors, 5xx and 429 are retried three times with exponential backoff. A 404 isn't retried.
A format change raises `ParseError` with a line number. Either way the error is stored on the
`IngestionRun`, the other files continue, and the run ends `partial`. Existing rows for the failed
file are untouched.

**8. What is winter, and why is the first year's winter missing?**
December of the previous year plus January and February, labelled with the January year. The first
year has no previous December, so the file shows `---`. That's checked arithmetically: every year's
winter equals the sum (or, for temperature, the day-weighted mean) of those three months.

**9. How do you stop the LLM from making numbers up?**
Four layers. It has no data except through tools. The prompt forbids answering from memory. In
code, an answer with digits but no successful tool call is replaced. The response shows the calls
and rows so a human can check. There's also a test for each.

**10. Why not text-to-SQL? What about prompt injection?**
With text-to-SQL, a prompt injection becomes a query injection, and SQL is hard to validate. Here
the model can only call six read-only functions, and their arguments pass the same whitelists as
the API. An injection can at most produce a wrong answer for the person who wrote it. History
can't carry `system` or `tool` roles.

**11. What if Groq is down, rate-limited, or there's no key?**
Every provider error becomes `LLMUnavailable`, and the endpoint returns 503 with a plain message.
On a 429 the client moves straight to the next model in a three-model chain, each with its own
free-tier quota. It doesn't sleep on `Retry-After`, because that held requests for 20 to 40
seconds in testing. Repeated standalone questions come from a cache keyed on the question, model
and latest ingest run, so they cost nothing and keep working if Groq is down. The rest of the site
never depends on the LLM.

**12. How are query parameters validated?**
DRF serializers built from the catalog: `ChoiceField` for codes (the error lists valid values),
bounded integers for years, a cross-field check for `year_from <= year_to`, and at most 4 compare
regions. `/observations/` uses a django-filter FilterSet with the same whitelists, plus 400 for a
bad `page` or `page_size`. Bad input can't reach the ORM, so it can't become a 500.

**13. How did you rule out N+1 queries?**
`select_related("region", "parameter")` on list endpoints and admin lists, and a single joined
query for compare. Tests assert the count: `/observations/` is 2 queries regardless of page size,
compare is 1 query for 4 regions, and admin lists cost the same for 3 rows as for 30.

**14. Why templates and vanilla JS rather than React?**
See section 5. For three pages the SPA toolchain is pure cost, and the UI calling the public API
keeps the separation that matters.

**15. How is the frontend's state managed?**
The URL is the state. Every change writes the selection to the query string, so any view can be
shared, and the server pre-selects whitelisted values so there's no flash. Each load gets an id,
and stale responses are ignored. While loading, the previous chart stays visible at reduced
opacity.

**16. How are secrets handled?**
Nothing secret is in the repo: `.env` is git-ignored, and a test scans every tracked file for key
patterns. Production reads settings only from real environment variables, refuses to start without
`SECRET_KEY`, and forces `DEBUG` off. On Render, secrets are set in the dashboard, and
`SECRET_KEY` is generated by Render.

**17. How does rate limiting work behind Render's proxy?**
DRF's `ScopedRateThrottle` keys on client IP. Behind a proxy, the socket address is the proxy's,
so `NUM_PROXIES=1` makes DRF use the last `X-Forwarded-For` entry, the one Render's proxy adds.
Checked on the live site: requests that each forged a different `X-Forwarded-For` were still
throttled at the limit, so a client can't bypass it. Counters are in process memory, which is exact
with one gunicorn process; several processes would need Redis.

**18. How do you keep the data up to date, and how would you scale this?**
A GitHub Actions schedule runs the ingest on the 2nd of each month (the Met Office updates on the
1st). `--strict` fails the job on anything short of 119/119 files, so GitHub emails the owner.
Next would be conditional GETs to skip unchanged files. For read load: HTTP caching keyed on the last run, then more web instances with
Redis for the throttle. The database is tiny (92 MB), so it isn't the bottleneck.

**19. What does "trend per decade" mean, and is it fair?**
It's an ordinary least-squares straight line fitted to the selected years, with its slope times
10. It summarises direction over the chosen window. It says nothing about acceleration and isn't a
forecast, and the about page says so. Changing the year range changes the trend, which is why the
selected range is always shown.

**20. How do you know the numbers are right?**
The parser is tested on five real files with counts worked out by hand (for example 143 x 17 - 1 -
6 = 2424). All 119 live files parse to 279,208 observations, matching an independent count made
with a different tool. Summary values in the tests were computed separately with awk. A live chat
answer (Wales's coldest winter, 1963, -0.45 °C) was checked against the raw Met Office file.

## 10. Three-minute demo

1. **Explorer (45 s).** Open https://uk-climate-insights.onrender.com (a ping keeps it awake; if
   it's slow to load, it's the free tier waking up, which takes about a minute). "One stripe per year, UK mean temperature since 1884.
   The red end is the last decade." Switch to Scotland, Rainfall, Annual, and tick the rolling
   mean. Point at the Wettest row and the trend. Mention that the URL just changed, so you can
   share this exact view.
2. **Data honesty (30 s).** Choose Winter. "Winter spans two years; the note explains it." Scroll
   to the table; Download CSV.
3. **Compare (30 s).** Click Compare regions and pick the four nations, summer max temperature,
   since 1960. "Each region keeps its colour when you untick one."
4. **Chat (45 s).** Ask "Which was the coldest winter in Wales?" Open "Data used": the one row it
   came from. Then ask "What's the weather tomorrow?" and it declines. "The model can only call six
   read-only functions; numbers without data get blocked in code."
5. **Engineering (30 s).** Open `/api/docs/`, then the GitHub repo: PR per step, CI with Postgres
   and a Docker build, 208 tests, the invariants table in `docs/TESTING.md`.
