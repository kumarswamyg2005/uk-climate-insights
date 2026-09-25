from decimal import Decimal

import pytest
from django.utils import timezone

from climate.catalog import REGION_CODES
from climate.ingest import sync_catalog
from climate.models import IngestionRun

from .factories import IngestionRunFactory, ObservationFactory

pytestmark = pytest.mark.django_db

API = "/api/v1"


@pytest.fixture
def catalog():
    return sync_catalog()


@pytest.fixture
def uk_tmax(catalog):
    """UK Tmax: annual 2000-2004 plus one January, and a Wales annual value to filter out."""
    regions, parameters = catalog
    run = IngestionRunFactory()
    values = {2000: "10.10", 2001: "12.30", 2002: "11.00", 2003: "12.30", 2004: "9.90"}
    for year, value in values.items():
        ObservationFactory(
            region=regions["UK"],
            parameter=parameters["Tmax"],
            year=year,
            value=Decimal(value),
            ingestion_run=run,
        )
    ObservationFactory(
        region=regions["UK"],
        parameter=parameters["Tmax"],
        year=2000,
        period="jan",
        ingestion_run=run,
    )
    ObservationFactory(region=regions["Wales"], parameter=parameters["Tmax"], ingestion_run=run)
    return run


# --- lookups ----------------------------------------------------------------------------------


def test_regions_are_listed_in_met_office_order(client, catalog):
    body = client.get(f"{API}/regions/").json()
    assert [r["code"] for r in body] == list(REGION_CODES)
    assert body[4] == {
        "code": "Northern_Ireland",
        "name": "Northern Ireland",
        "slug": "northern-ireland",
    }


def test_parameters_carry_units_and_available_years(client, uk_tmax):
    body = client.get(f"{API}/parameters/").json()
    assert [p["code"] for p in body][:3] == ["Tmax", "Tmin", "Tmean"]
    tmax = body[0]
    assert (tmax["unit"], tmax["first_year"], tmax["last_year"]) == ("°C", 2000, 2004)
    assert body[1]["first_year"] is None  # no Tmin data loaded


# --- observations -----------------------------------------------------------------------------


def test_observations_filter_and_carry_unit_and_provenance(client, uk_tmax):
    response = client.get(
        f"{API}/observations/",
        {"region": "UK", "parameter": "Tmax", "period": "ann", "year_from": 2001, "year_to": 2003},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 3
    row = body["results"][0]
    assert row == {
        "region": "UK",
        "parameter": "Tmax",
        "year": 2001,
        "period": "ann",
        "value": 12.3,
        "unit": "°C",
        "source_url": "https://www.metoffice.gov.uk/pub/data/weather/uk/climate/datasets/Tmax/date/UK.txt",
        "ingestion_run": uk_tmax.pk,
        "updated_at": row["updated_at"],
    }


def test_observations_paginate(client, uk_tmax):
    body = client.get(f"{API}/observations/", {"region": "UK", "page_size": 2}).json()
    assert body["count"] == 6
    assert len(body["results"]) == 2
    assert "page=2" in body["next"]


def test_ordering_by_value_is_stable_across_pages(client, uk_tmax):
    """2001 and 2003 tie on 12.30; paging one row at a time must still return both."""
    params = {"region": "UK", "period": "ann", "ordering": "-value", "page_size": 1}
    years = [
        client.get(f"{API}/observations/", {**params, "page": page}).json()["results"][0]["year"]
        for page in range(1, 6)
    ]
    assert years == [2001, 2003, 2002, 2000, 2004]


def test_observations_run_a_constant_number_of_queries(client, uk_tmax, django_assert_num_queries):
    with django_assert_num_queries(2):  # COUNT for pagination + one SELECT with joins, no N+1
        client.get(f"{API}/observations/")


def test_no_match_is_an_empty_200(client, uk_tmax):
    response = client.get(f"{API}/observations/", {"region": "Scotland"})
    assert response.status_code == 200
    assert response.json()["results"] == []


@pytest.mark.parametrize(
    ("params", "field", "message"),
    [
        ({"region": "Atlantis"}, "region", 'Unknown region "Atlantis". Valid: UK, England,'),
        ({"parameter": "Snow"}, "parameter", "Valid: Tmax, Tmin, Tmean, Sunshine,"),
        ({"period": "xmas"}, "period", "Valid: jan, feb,"),
        ({"year_from": 2000, "year_to": 1990}, "year_from", "must not be after year_to"),
        ({"year_from": "1990.5"}, "year_from", "whole number"),
        ({"year_to": 1066}, "year_to", "greater than or equal to 1800"),
        ({"ordering": "region"}, "ordering", "Select a valid choice"),
        ({"page": 999}, "page", "Invalid page"),
    ],
)
def test_bad_observation_params_are_400_with_a_clear_message(
    client, uk_tmax, params, field, message
):
    response = client.get(f"{API}/observations/", params)
    assert response.status_code == 400
    assert message in response.json()[field][0]


# --- series -----------------------------------------------------------------------------------


def test_series_returns_chart_points_in_year_order_with_unit(client, uk_tmax):
    response = client.get(
        f"{API}/series/",
        {"region": "UK", "parameter": "Tmax", "period": "ann", "year_from": 2002, "year_to": 2004},
    )
    assert response.status_code == 200
    assert response.json() == {
        "region": "UK",
        "region_name": "UK",
        "parameter": "Tmax",
        "parameter_name": "Max temperature",
        "period": "ann",
        "period_name": "Annual",
        "unit": "°C",
        "points": [[2002, 11.0], [2003, 12.3], [2004, 9.9]],
    }


def test_series_with_no_data_is_an_empty_200(client, catalog):
    response = client.get(
        f"{API}/series/", {"region": "UK", "parameter": "Sunshine", "period": "ann"}
    )
    assert response.status_code == 200
    assert response.json()["points"] == []


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"parameter": "Tmax", "period": "ann"}, "region"),
        ({"region": "UK", "parameter": "Tmax"}, "period"),
        ({"region": "uk", "parameter": "Tmax", "period": "ann"}, "region"),  # codes are exact
        ({"region": "UK", "parameter": "Tmax", "period": "ann", "year_from": "abc"}, "year_from"),
        (
            {
                "region": "UK",
                "parameter": "Tmax",
                "period": "ann",
                "year_from": 2001,
                "year_to": 2000,
            },
            "year_from",
        ),
    ],
)
def test_series_rejects_bad_params(client, params, field):
    response = client.get(f"{API}/series/", params)
    assert response.status_code == 400
    assert field in response.json()


# --- ingestion runs ---------------------------------------------------------------------------


def test_latest_run_is_404_before_any_ingest(client):
    assert client.get(f"{API}/ingestion-runs/latest/").status_code == 404


def test_latest_run_skips_failed_and_running_and_hides_error_text(client):
    good = IngestionRunFactory(
        status=IngestionRun.Status.PARTIAL,
        errors=[{"url": "https://example.test", "error": "secret internals"}],
        source_updated_at=timezone.now(),
    )
    IngestionRunFactory(status=IngestionRun.Status.FAILED)
    IngestionRunFactory(status=IngestionRun.Status.RUNNING)

    body = client.get(f"{API}/ingestion-runs/latest/").json()

    assert body["id"] == good.pk
    assert body["error_count"] == 1
    assert "secret internals" not in str(body)


# --- read-only, docs --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "regions/",
        "parameters/",
        "observations/",
        "series/",
        "series.csv",
        "summary/",
        "extremes/",
        "compare/",
        "ingestion-runs/latest/",
    ],
)
@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_api_is_read_only(client, path, method):
    """Invariant 7."""
    assert getattr(client, method)(f"{API}/{path}").status_code == 405


def test_openapi_schema_and_swagger_ui(client):
    schema = client.get("/api/schema/")
    assert schema.status_code == 200
    assert b"/api/v1/series/" in schema.content
    assert client.get("/api/docs/").status_code == 200
