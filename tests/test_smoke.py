from unittest import mock

import pytest
from django.db import DatabaseError


@pytest.mark.django_db
def test_healthz_ok(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok"}


def test_healthz_reports_db_failure_as_503(client):
    with mock.patch("climate.views.connection.cursor", side_effect=DatabaseError("down")):
        response = client.get("/healthz")
    assert response.status_code == 503
    assert response.json()["db"] == "unreachable"
