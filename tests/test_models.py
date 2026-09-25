import pytest
from django.db import IntegrityError, transaction

from climate import catalog
from climate.periods import PERIOD_ORDER

from .factories import ObservationFactory

pytestmark = pytest.mark.django_db


def test_unique_key_is_enforced_by_the_database():
    """Invariant 3: bypasses model validation entirely; only the DB constraint can stop this."""
    obs = ObservationFactory()
    with pytest.raises(IntegrityError), transaction.atomic():
        ObservationFactory(
            region=obs.region,
            parameter=obs.parameter,
            year=obs.year,
            period=obs.period,
            ingestion_run=obs.ingestion_run,
        )


def test_same_year_different_period_is_allowed():
    obs = ObservationFactory(period="jan")
    ObservationFactory(region=obs.region, parameter=obs.parameter, period="feb")


def test_unknown_period_is_rejected_by_the_database():
    with pytest.raises(IntegrityError), transaction.atomic():
        ObservationFactory(period="xyz")


def test_str_is_readable():
    obs = ObservationFactory(year=1990, period="win")
    assert str(obs) == "UK Tmax 1990 win = 10.00"
    assert str(obs.parameter) == "Max temperature (°C)"
    assert str(obs.ingestion_run) == f"Run #{obs.ingestion_run.pk} (success)"


def test_catalog_matches_met_office_page():
    """The 17 x 7 grid found on the Met Office page during the data investigation."""
    assert len(catalog.REGION_CODES) == 17
    assert catalog.PARAMETER_CODES == (
        "Tmax", "Tmin", "Tmean", "Sunshine", "Rainfall", "Raindays1mm", "AirFrost",
    )  # fmt: skip
    assert len(PERIOD_ORDER) == 17
