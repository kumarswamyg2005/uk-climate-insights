# ADR-002: Postgres with per-file upsert + prune instead of delete-and-reload

**Status:** Accepted
**Date:** 2026-09-25
**Deciders:** Kumaraswamy

## Context

Every Met Office file is republished monthly. Most rows never change. The current year's months and
seasons are provisional and are revised or filled in over time, and a file can occasionally be
unavailable (404, 5xx) or change format. Re-running the ingest must be safe (the same row count,
never duplicates), and a failure in one file must not empty or corrupt the others.

## Decision

Use PostgreSQL with a database-level `UniqueConstraint(region, parameter, year, period)`. For each
file, in **one transaction**:

1. `bulk_create(..., update_conflicts=True, unique_fields=[region, parameter, year, period], update_fields=[value, source_url, ingestion_run, updated_at])`
   which compiles to `INSERT ... ON CONFLICT (...) DO UPDATE`.
2. Delete rows for that `(region, parameter)` whose `ingestion_run` is not the current run. Those
   rows exist in the DB but no longer in the source file (for example a value the Met Office
   withdrew).

A file that fails to fetch or parse never reaches step 1, so its existing rows stay as they were.
A file that parses to zero records is treated as a parse error, so the prune can't wipe a series.

## Options considered

### Option A: Upsert + prune per file (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low: one ORM call plus one delete, inside `transaction.atomic()` |
| Cost | 119 transactions of ~2.3k rows each; seconds in total |
| Scalability | Linear in file size; unaffected by total table size thanks to the unique index |
| Team familiarity | Standard Postgres `ON CONFLICT` |

**Pros:** idempotent. Readers never see a half-empty series (MVCC plus the per-file transaction).
Revised values update in place with provenance refreshed, and withdrawn values disappear, so the
table mirrors the source.
**Cons:** `ON CONFLICT DO UPDATE` rewrites unchanged rows too (write amplification is acceptable at
~279k rows a month). Requires Postgres (or SQLite 3.24+) semantics.

### Option B: Delete-and-reload (truncate, then insert everything)

**Pros:** simplest mental model, and the table always equals the latest download.
**Cons:** if file 60 of 119 fails, those series are either gone (if deleted up front) or the reload
needs one giant transaction that holds locks for the whole ingest. Observation ids churn every run,
and provenance ("which run last confirmed this value") is lost.

### Option C: Insert-only with "latest version" reads

**Pros:** full revision history.
**Cons:** every read needs a "latest per key" subquery. That's history nobody has asked for, and it
doubles the query complexity. YAGNI.

## Trade-off analysis

Option A gives the correctness of B (the DB equals the source) with the failure isolation that B
lacks. The DB-level constraint matters as much as the upsert. It makes idempotency a property of the
schema rather than of application code, and it's the conflict target Postgres needs for `ON CONFLICT`.

## Consequences

- Easier: re-running the ingest at any time, partial ingests (`--regions`, `--parameters`), and
  explaining where any value came from (`source_url`, `ingestion_run`).
- Harder: keeping revision history would need a separate table (Option C) later.
- Revisit: to cut write amplification, add `WHERE observation.value IS DISTINCT FROM EXCLUDED.value`
  via raw SQL, once volume makes it matter.

## Action items

1. [ ] `UniqueConstraint` + covering index in the `Observation` model and migration.
2. [ ] Tests: run twice gives the same count; a changed value is updated, not duplicated; a withdrawn
   value is pruned; a failing file leaves its existing rows untouched.
