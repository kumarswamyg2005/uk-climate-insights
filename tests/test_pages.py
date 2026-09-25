import json

import pytest

from climate.ingest import sync_catalog

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("path", ["/", "/compare/", "/about/", "/healthz", "/api/docs/"])
def test_pages_load(client, path):
    assert client.get(path).status_code == 200


def test_explorer_defaults_and_links_its_assets(client):
    html = client.get("/").content.decode()
    assert '<option value="Tmean" data-unit="°C" selected>' in html
    assert '<option value="UK" selected>' in html
    assert "climate/vendor/chart.umd.min.js" in html  # vendored, no CDN
    assert "cdn." not in html
    assert "Open Government Licence v3.0" in html


def test_explorer_preselects_from_a_shared_url(client):
    html = client.get("/?region=Scotland&parameter=Rainfall&period=win").content.decode()
    assert '<option value="Scotland" selected>' in html
    assert '<option value="Rainfall" data-unit="mm" selected>' in html
    assert '<option value="win" selected>' in html


def test_explorer_ignores_junk_in_the_url(client):
    response = client.get("/?region=<script>&parameter=Snow&period=xmas")
    assert response.status_code == 200
    html = response.content.decode()
    assert '<option value="UK" selected>' in html
    assert "<script>&" not in html


def regions_on(response):
    return json.loads(
        response.content.decode()
        .split('id="initial-regions" type="application/json">')[1]
        .split("</script>")[0]
    )


def test_compare_keeps_up_to_four_known_regions_in_order(client):
    response = client.get("/compare/?regions=Wales,Atlantis,UK,Wales,Scotland,Midlands,East_Anglia")
    assert regions_on(response) == ["Wales", "UK", "Scotland", "Midlands"]


def test_compare_has_sensible_defaults(client):
    assert regions_on(client.get("/compare/")) == [
        "England",
        "Wales",
        "Scotland",
        "Northern_Ireland",
    ]


def test_about_lists_coverage_from_the_database(client):
    sync_catalog()
    html = client.get("/about/").content.decode()
    assert "Days of air frost" in html
    assert "Not loaded yet" in html  # no observations in this test database
