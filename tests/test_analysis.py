"""Summary, extremes, compare and CSV, checked against the real fixtures.

Expected numbers were computed independently from the fixture files with awk (not with app code):
Tmax UK annual 1884-2025: n=142, mean=12.1474, max 14.01 (2025), min 10.81 (1888 and 1892),
least-squares slope 0.00966 degC/year.
"""

import csv
import io
from decimal import Decimal

import pytest

from climate import queries
from climate.ingest import run_ingest, sync_catalog

from .conftest import fixture_text, serve
from .factories import IngestionRunFactory, ObservationFactory

pytestmark = pytest.mark.django_db

API = "/api/v1"


@pytest.fixture
def real_data(metoffice):
    for parameter, region in [
        ("Tmax", "UK"),
        ("Rainfall", "Scotland"),
        ("AirFrost", "Wales"),
    ]:
        serve(metoffice, parameter, region, body=fixture_text(f"{parameter}_{region}.txt"))
    run_ingest(["UK", "Scotland", "Wales"], ["Tmax", "Rainfall", "AirFrost"])


# --- summary ----------------------------------------------------------------------------------


def test_summary_matches_hand_computed_values(client, real_data):
    body = client.get(
        f"{API}/summary/", {"region": "UK", "parameter": "Tmax", "period": "ann"}
    ).json()
    assert body["unit"] == "°C"
    assert (body["count"], body["first_year"], body["last_year"]) == (142, 1884, 2025)
    assert body["mean"] == 12.15
    assert body["max"] == {"value": 14.01, "years": [2025]}
    assert body["min"] == {"value": 10.81, "years": [1888, 1892]}  # a real tie in the data
    assert body["latest"] == {"year": 2025, "value": 14.01}
    assert body["trend_per_decade"] == 0.097


def test_summary_honours_the_year_range(client, real_data):
    body = client.get(
        f"{API}/summary/",
        {"region": "UK", "parameter": "Tmax", "period": "ann", "year_from": 1990, "year_to": 1999},
    ).json()
    assert (body["count"], body["first_year"], body["last_year"]) == (10, 1990, 1999)


def test_summary_reports_every_tied_year(client, real_data):
    """No July in Wales has ever had an air frost: all 96 years tie at 0."""
    body = client.get(
        f"{API}/summary/", {"region": "Wales", "parameter": "AirFrost", "period": "jul"}
    ).json()
    assert body["min"]["value"] == body["max"]["value"] == 0.0
    assert body["min"]["years"] == list(range(1931, 2027))
    assert body["trend_per_decade"] == 0.0


def test_summary_of_nothing_is_empty_not_an_error(client, real_data):
    body = client.get(
        f"{API}/summary/", {"region": "Wales", "parameter": "Sunshine", "period": "ann"}
    ).json()
    assert body["count"] == 0
    assert body["mean"] is body["min"] is body["trend_per_decade"] is None


def test_summary_of_one_year_has_no_trend(client, real_data):
    body = client.get(
        f"{API}/summary/",
        {"region": "UK", "parameter": "Tmax", "period": "ann", "year_from": 2000, "year_to": 2000},
    ).json()
    assert body["count"] == 1
    assert body["trend_per_decade"] is None


# --- extremes ---------------------------------------------------------------------------------


def test_wettest_years_in_scotland_since_1990(client, real_data):
    body = client.get(
        f"{API}/extremes/",
        {
            "region": "Scotland",
            "parameter": "Rainfall",
            "period": "ann",
            "kind": "max",
            "limit": 3,
            "year_from": 1990,
        },
    ).json()
    assert body["unit"] == "mm"
    assert body["rows"] == [
        {"year": 1990, "value": 1891.8},
        {"year": 2011, "value": 1862.9},
        {"year": 2015, "value": 1837.4},
    ]


def test_coldest_years_tie_break_on_the_earlier_year(client, real_data):
    body = client.get(
        f"{API}/extremes/",
        {"region": "UK", "parameter": "Tmax", "period": "ann", "kind": "min", "limit": 2},
    ).json()
    assert body["rows"] == [{"year": 1888, "value": 10.81}, {"year": 1892, "value": 10.81}]


@pytest.mark.parametrize(
    ("extra", "field"),
    [({"kind": "median"}, "kind"), ({"kind": "max", "limit": 0}, "limit"), ({}, "kind")],
)
def test_extremes_validate_kind_and_limit(client, extra, field):
    params = {"region": "UK", "parameter": "Tmax", "period": "ann", **extra}
    response = client.get(f"{API}/extremes/", params)
    assert response.status_code == 400
    assert field in response.json()


# --- compare ----------------------------------------------------------------------------------


@pytest.fixture
def two_regions():
    regions, parameters = sync_catalog()
    run = IngestionRunFactory()
    for code, year, value in [("UK", 2000, "1.00"), ("UK", 2001, "2.00"), ("Wales", 2001, "3.00")]:
        ObservationFactory(
            region=regions[code],
            parameter=parameters["Tmax"],
            year=year,
            value=Decimal(value),
            ingestion_run=run,
        )
    ObservationFactory(region=regions["Wales"], parameter=parameters["Tmax"], year=2002, value=4)


def test_compare_aligns_years_and_fills_gaps_with_null(client, two_regions):
    body = client.get(
        f"{API}/compare/", {"regions": "Wales,UK", "parameter": "Tmax", "period": "ann"}
    ).json()
    assert body["unit"] == "°C"
    assert body["regions"] == [{"code": "Wales", "name": "Wales"}, {"code": "UK", "name": "UK"}]
    assert body["years"] == [2000, 2001, 2002]
    assert body["values"] == {"Wales": [None, 3.0, 4.0], "UK": [1.0, 2.0, None]}


def test_compare_year_range_and_duplicate_codes(client, two_regions):
    body = client.get(
        f"{API}/compare/",
        {
            "regions": "UK, UK ,Wales",
            "parameter": "Tmax",
            "period": "ann",
            "year_from": 2001,
            "year_to": 2001,
        },
    ).json()
    assert [r["code"] for r in body["regions"]] == ["UK", "Wales"]
    assert body["values"] == {"UK": [2.0], "Wales": [3.0]}


@pytest.mark.parametrize(
    ("regions", "message"),
    [
        ("UK,England,Wales,Scotland,Midlands", "at most 4 regions (got 5)"),
        ("UK,Atlantis", "Unknown region(s) Atlantis. Valid: UK,"),
        (" , ", "at least one region"),
    ],
)
def test_compare_rejects_bad_region_lists(client, regions, message):
    response = client.get(
        f"{API}/compare/", {"regions": regions, "parameter": "Tmax", "period": "ann"}
    )
    assert response.status_code == 400
    assert message in response.json()["regions"][0]


def test_compare_accepts_a_json_list_from_the_chat_tools(two_regions):
    result = queries.compare_regions({"regions": ["UK"], "parameter": "Tmax", "period": "ann"})
    assert result["values"] == {"UK": [1.0, 2.0]}
    with pytest.raises(queries.serializers.ValidationError):
        queries.compare_regions({"regions": [1, 2], "parameter": "Tmax", "period": "ann"})


# --- CSV --------------------------------------------------------------------------------------


def test_csv_download(client, real_data):
    response = client.get(
        f"{API}/series.csv",
        {"region": "Wales", "parameter": "AirFrost", "period": "win", "year_from": 2024},
    )
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv; charset=utf-8"
    assert response["Content-Disposition"] == 'attachment; filename="Wales_AirFrost_win.csv"'
    rows = list(csv.reader(io.StringIO(response.content.decode())))
    assert rows == [
        ["region", "parameter", "period", "year", "value", "unit"],
        ["Wales", "AirFrost", "win", "2024", "18.8", "days"],
        ["Wales", "AirFrost", "win", "2025", "19.3", "days"],
        ["Wales", "AirFrost", "win", "2026", "17.0", "days"],
    ]


def test_csv_with_bad_params_is_a_json_400(client):
    response = client.get(f"{API}/series.csv", {"region": "Atlantis"})
    assert response.status_code == 400
    assert "Unknown region" in response.json()["region"][0]
