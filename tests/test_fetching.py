import pytest
import requests
import responses

from climate.fetching import USER_AGENT, fetch_text, make_session, series_url

from .conftest import serve

URL = series_url("Tmax", "UK")


def test_url_matches_the_met_office_download_form():
    assert (
        URL == "https://www.metoffice.gov.uk/pub/data/weather/uk/climate/datasets/Tmax/date/UK.txt"
    )


def test_identifies_itself(metoffice):
    serve(metoffice, "Tmax", "UK", body="ok")
    fetch_text(URL, make_session())
    assert metoffice.calls[0].request.headers["User-Agent"] == USER_AGENT


@pytest.mark.parametrize("transient", [500, 503, 429])
def test_transient_errors_are_retried(metoffice, transient):
    serve(metoffice, "Tmax", "UK", status=transient)
    serve(metoffice, "Tmax", "UK", body="year jan")
    assert fetch_text(URL, make_session()) == "year jan"
    assert len(metoffice.calls) == 2


def test_connection_errors_are_retried_then_raised(metoffice):
    metoffice.add(responses.GET, URL, body=requests.ConnectionError("reset"))
    with pytest.raises(requests.ConnectionError):
        fetch_text(URL, make_session())
    assert len(metoffice.calls) == 3


def test_not_found_is_not_retried(metoffice):
    serve(metoffice, "Tmax", "UK", status=404)
    with pytest.raises(requests.HTTPError, match="404"):
        fetch_text(URL, make_session())
    assert len(metoffice.calls) == 1
