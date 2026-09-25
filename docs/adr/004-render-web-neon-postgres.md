# ADR-004: Render for the web service, Neon for Postgres

**Status:** Accepted
**Date:** 2026-09-26
**Deciders:** Kumaraswamy

## Context

The app must run on a public cloud with HTTPS, and it must still be live when the reviewers open it,
possibly several weeks after submission. It's one Docker image plus a Postgres database, with
negligible traffic. Budget is zero. The original plan was Render for both the web service and
Postgres.

Checked on Render's docs at deploy time: "Free Render Postgres databases expire 30 days after
creation", with a 14-day grace period before the database is deleted. Free web services spin down
after 15 idle minutes and take about a minute to wake. There is no shell and no one-off jobs.

## Decision

- **Web:** a Render free web service built from the repo's `Dockerfile` and described in
  `render.yaml`. Deploys happen on every push to `main`. Health checks use `/healthz`.
- **Database:** Neon free Postgres 16 in AWS eu-central-1, the same region as the Render service
  (Frankfurt), over the direct (non-pooled) endpoint with TLS. The URL is set as the
  `DATABASE_URL` secret on Render.
- The first boot ingests the Met Office data in the background while gunicorn starts. Without a
  shell on the free plan, this is the only way to seed the database.

## Options considered

### Option A: Render web + Neon Postgres (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low: one Blueprint and one secret URL |
| Cost | Free |
| Longevity | The database doesn't expire; Neon's free storage (0.5 GB) holds ~92 MB with room to spare |
| Operations | Two dashboards instead of one |

**Pros:** no expiry, same Postgres 16 as local and CI, and it keeps Render's Docker-native deploys.
**Cons:** a cross-provider network hop (same region, a few ms), and Neon suspends idle compute, so
the first query after a quiet spell is slower.

### Option B: Render web + Render Postgres (the original plan)

**Pros:** one provider, private networking.
**Cons:** the free database is deleted 44 days after creation, which could fall inside the
interview window. The paid plan fixes that for a monthly fee.

### Option C: AWS EC2 (+ RDS or Postgres on the instance)

**Pros:** full control, with no spin-down.
**Cons:** I'd have to handle TLS, a reverse proxy, OS patching and security groups myself. The free
tier lasts 12 months and then costs money. It's a lot of operations for a read-mostly demo.

### Option D: Fly.io / Railway

**Pros:** similar developer experience to Render.
**Cons:** no meaningful free database tier for this use at the time of writing, and no advantage
over A.

## Trade-off analysis

Longevity decided it. The deliverable has to be live when someone clicks it, and a database that
deletes itself after 30 to 44 days is the most likely way for that to fail. Splitting providers
costs one extra dashboard and a few milliseconds per query. Staying in one region keeps that small.

## Consequences

- Easier: the demo survives any interview date; moving to paid tiers later is just changing plans,
  with no migration.
- Harder: the `DATABASE_URL` secret lives in Render's environment and must be rotated through the
  Neon console.
- Cold starts: after 15 idle minutes the first page load takes about a minute (Render), and the
  first query after Neon suspends adds under a second.
- Revisit: a paid Render instance (no spin-down), or Render Postgres, if this became a real service.

## Action items

1. [x] `render.yaml`: Docker web service, `/healthz` health check, secrets marked `sync: false`.
2. [x] Production settings take the Render hostname from `RENDER_EXTERNAL_HOSTNAME`.
3. [ ] Rotate the Neon role password and the Groq key if either is ever exposed.
