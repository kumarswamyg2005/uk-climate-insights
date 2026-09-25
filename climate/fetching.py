"""Download Met Office series files politely: User-Agent, timeouts, retries with backoff."""

import requests
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

BASE_URL = "https://www.metoffice.gov.uk/pub/data/weather/uk/climate/datasets"
USER_AGENT = "uk-climate-insights/1.0 (+https://github.com/kumarswamyg2005/uk-climate-insights)"
TIMEOUT = (5, 30)  # seconds: connect, read


def series_url(parameter: str, region: str) -> str:
    """Year-ordered ("date") file; the site's download form builds the same URL."""
    return f"{BASE_URL}/{parameter}/date/{region}.txt"


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    return session


def _is_transient(exc: BaseException) -> bool:
    """Worth another try: network trouble, server errors, rate limiting. Not 404s."""
    if isinstance(exc, requests.ConnectionError | requests.Timeout):
        return True
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return exc.response.status_code >= 500 or exc.response.status_code == 429
    return False


@retry(
    retry=retry_if_exception(_is_transient),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def fetch_text(url: str, session: requests.Session) -> str:
    response = session.get(url, timeout=TIMEOUT)
    response.raise_for_status()
    # Served as text/plain with no charset; the files are ASCII, so decode explicitly.
    return response.content.decode("utf-8", errors="replace")
