from pathlib import Path

import pytest
import responses
from tenacity import wait_none

from climate.fetching import fetch_text, series_url

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text()


@pytest.fixture(autouse=True)
def _no_waiting(settings, monkeypatch):
    """No politeness delay or retry backoff in tests."""
    settings.METOFFICE_REQUEST_DELAY = 0
    monkeypatch.setattr(fetch_text.retry, "wait", wait_none())


@pytest.fixture
def metoffice():
    """Mock Met Office. Unregistered URLs raise ConnectionError, so no test can hit the network."""
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        yield mock


def serve(mock, parameter, region, body="", status=200):
    mock.add(responses.GET, series_url(parameter, region), body=body, status=status)
