# ADR-003: LLM tool calling over typed query functions instead of text-to-SQL

**Status:** Accepted
**Date:** 2026-09-25
**Deciders:** Kumaraswamy

## Context

The assignment asks for an LLM chat that answers weather questions "from DB regions". Answers must
come from the stored Met Office data, not the model's memory. The endpoint is public and
unauthenticated, so every message is untrusted input, including prompt-injection attempts. Groq is
the provider (free tier, fast, OpenAI-compatible tool calling).

## Decision

The model gets **tools, not SQL**. `climate/chat/tools.py` exposes six read-only functions
(`list_regions`, `list_parameters`, `get_series`, `get_extreme`, `get_summary`, `compare_regions`)
with JSON schemas whose `enum`s come from the catalog whitelist. The service validates every call's
arguments with the same validator the REST API uses, then runs the shared ORM query in
`climate/queries.py`. It returns rows to the model, and returns the tool calls plus those rows to the
user.

## Options considered

### Option A: Tool calling over validated ORM functions (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Medium: a loop of at most 5 rounds, tool schemas, a dispatcher |
| Cost | 2-3 LLM calls per typical question |
| Scalability | New question types need a new tool |
| Security | Strong: the model can only do what the API already allows |

**Pros:** no SQL injection surface. Every argument is whitelisted. The query plans are known and
indexed. Answers are grounded, and the "data used" payload is the literal tool output, which is
testable with a fake LLM.
**Cons:** less flexible. A question the tools can't express ("which month had the biggest
year-on-year jump?") gets "I can't answer that from the data" instead of a clever query.

### Option B: Text-to-SQL (model writes SQL, we execute it on a read-only role)

| Dimension | Assessment |
|---|---|
| Complexity | Medium: schema prompt, SQL sanitising, read-only DB role, statement timeouts |
| Cost | Fewer round trips for complex questions |
| Scalability | Handles arbitrary analytical questions |
| Security | Weak: prompt injection becomes query injection; needs defence in depth |

**Pros:** answers open-ended analytical questions.
**Cons:** a hostile prompt can craft expensive or data-exfiltrating queries (`pg_sleep`, cross joins,
reading `auth_user` unless the role is locked down perfectly). SQL is hard to validate and the
results hard to test. It also breaks invariant 9.

### Option C: RAG over pre-written text summaries

**Pros:** simple.
**Cons:** numbers come back through retrieval of prose, so the precision and freshness the
assignment asks for are lost.

## Trade-off analysis

For a public, anonymous endpoint, the safety and testability of Option A outweigh the flexibility of
Option B. The questions users actually ask (wettest, coldest, trend, compare, since year X) map
onto six tools. The tools reuse the API's query functions, so the chat can't drift from what the
API returns.

## Consequences

- Easier: security review ("what can the model do?" is answered by six function signatures) and
  deterministic tests with a fake client.
- Harder: supporting new kinds of questions means adding a tool, with its schema and tests.
- Revisit: if users routinely ask questions the tools can't express, add narrowly-scoped tools
  (e.g. `rank_years`) before considering SQL.

## Action items

1. [ ] `LLMClient` interface + Groq implementation; a fake client in tests.
2. [ ] System prompt: valid codes, natural-language mappings, the "no numbers without a tool call" rule.
3. [ ] Code-level guard: an answer containing numbers with zero tool calls is replaced by a
   "couldn't ground that" message.
