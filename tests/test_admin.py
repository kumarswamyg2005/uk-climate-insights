import pytest

from .factories import ObservationFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("model", ["region", "parameter", "observation", "ingestionrun"])
def test_changelists_render(admin_client, model):
    ObservationFactory()
    response = admin_client.get(f"/admin/climate/{model}/")
    assert response.status_code == 200


def test_admin_is_read_only(admin_client):
    obs = ObservationFactory()
    assert admin_client.get("/admin/climate/observation/add/").status_code == 403
    page = admin_client.get(f"/admin/climate/observation/{obs.pk}/change/")
    assert page.status_code == 200  # view-only page
    assert b'name="_save"' not in page.content


@pytest.mark.parametrize("model", ["observation", "ingestionrun", "region"])
def test_changelist_queries_do_not_grow_with_rows(
    admin_client, model, django_assert_max_num_queries
):
    """No N+1: rendering 3 rows and 30 rows costs the same number of queries."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from climate.ingest import sync_catalog

    from .factories import IngestionRunFactory

    regions, parameters = sync_catalog()

    def count():
        with CaptureQueriesContext(connection) as ctx:
            assert admin_client.get(f"/admin/climate/{model}/").status_code == 200
        return len(ctx.captured_queries)

    run = IngestionRunFactory()
    for year in range(3):
        ObservationFactory(
            region=regions["UK"], parameter=parameters["Tmax"], year=2000 + year, ingestion_run=run
        )
    few = count()
    for i, code in enumerate(list(regions)[:10]):
        for year in range(3):
            ObservationFactory(
                region=regions[code],
                parameter=parameters["Rainfall"],
                year=1900 + i * 3 + year,
                ingestion_run=IngestionRunFactory(),
            )
    assert count() == few
