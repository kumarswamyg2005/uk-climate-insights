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

## Every invariant has a test

| # | Invariant (`climate/invariants.py`) | Tests |
|---|---|---|
| 1 | Missing is never stored as 0 | `test_parsing::test_dashes_mean_no_row_not_zero`, `::test_partial_current_year_blank_cells_are_absent_and_nothing_shifts`, `test_ingest::test_missing_values_are_not_stored` |
| 2 | Idempotent ingest | `test_ingest::test_running_twice_is_idempotent`, `::test_changed_value_is_updated_in_place`, `::test_value_withdrawn_from_the_source_is_pruned` |
| 3 | Unique key in the DB | `test_models::test_unique_key_is_enforced_by_the_database` |
| 4 | Units are data | `test_api::test_observations_filter_and_carry_unit_and_provenance`, `::test_series_returns_chart_points_in_year_order_with_unit`, `test_analysis::test_csv_download`, `test_ingest::test_seeds_the_full_catalog_with_units` |
| 5 | Provenance | `test_ingest::test_stores_every_observation_with_provenance` |
| 6 | A failing file never aborts the run | `test_ingest::test_one_missing_file_gives_a_partial_run_and_the_rest_is_stored`, `::test_a_broken_file_leaves_existing_rows_untouched`, `::test_database_error_in_one_file_rolls_back_only_that_file`, `::test_run_is_closed_even_if_interrupted` |
| 7 | Read-only API except chat | `test_api::test_api_is_read_only`, `test_chat::test_chat_is_post_only` |
| 8 | Whitelisted params, 400 not 500 | `test_api::test_bad_observation_params_are_400_with_a_clear_message`, `::test_bad_page_size_is_a_400_not_silently_ignored`, `test_analysis::test_compare_rejects_bad_region_lists` |
| 9 | LLM never writes SQL | `test_chat::test_tool_schemas_whitelist_the_catalog`, `::test_bad_tool_calls_are_rejected_with_a_readable_error` |
| 10 | Answers grounded in the DB | `test_chat::test_answers_from_tool_results_and_reports_the_grounding`, `::test_numbers_without_any_data_behind_them_are_withheld` |
| 11 | Chat degrades to 503 | `test_chat::test_chat_without_an_api_key_is_503_and_the_rest_still_works`, `::test_groq_failures_become_llm_unavailable` |
| 12 | Chat throttled and length-capped | `test_chat::test_chat_is_rate_limited_per_client`, `::test_chat_input_is_capped_and_history_roles_are_whitelisted` |
| 13 | No secrets; prod config from env | `test_settings::test_production_refuses_to_start_without_a_secret_key`, `::test_production_forces_debug_off_and_reads_the_key_from_env`, `::test_no_credentials_in_tracked_files` |
| 14 | Polite scraping | `test_fetching::test_identifies_itself`, `::test_transient_errors_are_retried`, `test_ingest::test_waits_between_requests` |

No-N+1 checks: `test_api::test_observations_run_a_constant_number_of_queries`,
`test_api::test_compare_query_count_does_not_grow_with_regions`,
`test_admin::test_changelist_queries_do_not_grow_with_rows`.
