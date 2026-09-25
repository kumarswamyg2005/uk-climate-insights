"""Rules this codebase must never break. Each one is covered by a test (see README).

 1. Missing values are never stored as 0. A "---" or blank cell means "no row", never a zero.
 2. Ingestion is idempotent. Re-running yields the same row count; changed values (the partial
    current year) are updated in place via upsert on the unique key, never duplicated.
 3. Unique key (region, parameter, year, period) is enforced by a DB constraint, not app logic.
 4. Units are data: stored on Parameter and returned by every API response that returns values.
 5. Provenance: every observation points at the IngestionRun and source URL that last wrote it.
 6. A failing file never aborts the whole ingest. The error is recorded on the run, other files
    continue, and the run ends as success, partial or failed.
 7. The public API is read-only except POST /api/v1/chat/.
 8. All query params are validated against whitelists (region, parameter, period codes, year
    bounds). Bad input returns HTTP 400 with a clear message, never a 500.
 9. The LLM never writes SQL and never sees the DB directly. It can only call typed tool functions
    whose arguments are validated against the same whitelists; tools use the Django ORM.
10. Chat answers come from the DB, not the model's memory. The response includes the tool calls
    made and the data returned, and the bot says so when the data can't answer.
11. Chat degrades gracefully: no API key, provider error or timeout gives HTTP 503 with a clear
    message, and the rest of the app keeps working.
12. Chat is rate-limited per IP and its input is length-capped.
13. No secrets in the repo or git history. SECRET_KEY, DEBUG, ALLOWED_HOSTS and
    CSRF_TRUSTED_ORIGINS come from env in production.
14. Polite scraping: an identifying User-Agent, a delay between requests, retries with backoff.

The limits below are the numbers these rules refer to.
"""

MIN_YEAR = 1800
MAX_YEAR = 2100
MAX_COMPARE_REGIONS = 4

CHAT_MAX_MESSAGE_CHARS = 500
# Kept small because the free Groq tier allows ~8k tokens a minute per model.
CHAT_MAX_HISTORY_MESSAGES = 6
CHAT_MAX_HISTORY_CHARS = 1000
CHAT_MAX_TOOL_ROUNDS = 5
CHAT_DEADLINE_SECONDS = 30  # stop starting new LLM rounds after this; gunicorn times out at 60
