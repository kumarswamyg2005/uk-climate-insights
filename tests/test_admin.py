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
