from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from climate import ingest
from climate.fetching import series_url
from climate.ingest import run_ingest, start_background_ingest
from climate.models import IngestionRun, Observation, Parameter, Region

from .conftest import fixture_text, serve

pytestmark = pytest.mark.django_db

TMAX_UK = fixture_text("Tmax_UK.txt")
TMAX_UK_ROWS = 2424  # hand count, see test_parsing.py


def ingest_tmax_uk(metoffice, body=TMAX_UK):
    serve(metoffice, "Tmax", "UK", body=body)
    return run_ingest(["UK"], ["Tmax"])


def test_stores_every_observation_with_provenance(metoffice):
    run = ingest_tmax_uk(metoffice)

    assert run.status == IngestionRun.Status.SUCCESS
    assert (run.files_attempted, run.files_succeeded, run.rows_upserted) == (1, 1, TMAX_UK_ROWS)
    assert run.finished_at is not None
    assert Observation.objects.count() == TMAX_UK_ROWS
    # Invariant 5: every row points at the run and file that wrote it.
    url = series_url("Tmax", "UK")
    assert set(Observation.objects.values_list("ingestion_run", "source_url")) == {(run.pk, url)}
    obs = Observation.objects.get(
        region__code="UK", parameter__code="Tmax", year=2025, period="ann"
    )
    assert obs.value == Decimal("14.01")


def test_seeds_the_full_catalog_with_units(metoffice):
    ingest_tmax_uk(metoffice)
    assert Region.objects.count() == 17
    assert Region.objects.get(code="England_SW_and_S_Wales").slug == "england-sw-and-s-wales"
    assert dict(Parameter.objects.values_list("code", "unit")) == {
        "Tmax": "°C",
        "Tmin": "°C",
        "Tmean": "°C",
        "Sunshine": "hours",
        "Rainfall": "mm",
        "Raindays1mm": "days",
        "AirFrost": "days",
    }


def test_missing_values_are_not_stored(metoffice):
    """Invariant 1: '---' and the blank cells of the partial year are absent, not zero."""
    ingest_tmax_uk(metoffice)
    stored = Observation.objects.filter(region__code="UK", parameter__code="Tmax")
    assert not stored.filter(year=1884, period="win").exists()
    assert not stored.filter(year=2026, period__in=["sep", "oct", "nov", "dec", "aut", "ann"])


def test_running_twice_is_idempotent(metoffice):
    """Invariant 2: same count, no duplicates, rows now owned by the latest run."""
    ingest_tmax_uk(metoffice)
    second = ingest_tmax_uk(metoffice)
    assert Observation.objects.count() == TMAX_UK_ROWS
    assert set(Observation.objects.values_list("ingestion_run", flat=True)) == {second.pk}


def test_changed_value_is_updated_in_place(metoffice):
    ingest_tmax_uk(metoffice)
    obs = Observation.objects.get(year=2026, period="aug")
    revised = TMAX_UK.replace("22.6   21.4", "22.6   21.9")  # provisional Aug 2026 revised

    second = ingest_tmax_uk(metoffice, revised)

    obs.refresh_from_db()  # same row (same pk), new value and provenance
    assert obs.value == Decimal("21.9")
    assert obs.ingestion_run == second
    assert Observation.objects.count() == TMAX_UK_ROWS


def test_value_withdrawn_from_the_source_is_pruned(metoffice):
    ingest_tmax_uk(metoffice)
    withdrawn = TMAX_UK.replace("22.6   21.4", "22.6    ---")
    ingest_tmax_uk(metoffice, withdrawn)
    assert not Observation.objects.filter(year=2026, period="aug").exists()
    assert Observation.objects.count() == TMAX_UK_ROWS - 1


def test_one_missing_file_gives_a_partial_run_and_the_rest_is_stored(metoffice):
    """Invariant 6."""
    serve(metoffice, "Tmax", "UK", body=TMAX_UK)
    serve(metoffice, "Tmax", "Wales", status=404)

    run = run_ingest(["UK", "Wales"], ["Tmax"])

    assert run.status == IngestionRun.Status.PARTIAL
    assert (run.files_attempted, run.files_succeeded) == (2, 1)
    assert run.errors == [
        {"url": series_url("Tmax", "Wales"), "error": mock.ANY},
    ]
    assert "404" in run.errors[0]["error"]
    assert Observation.objects.count() == TMAX_UK_ROWS


def test_a_broken_file_leaves_existing_rows_untouched(metoffice):
    first = ingest_tmax_uk(metoffice)
    run = ingest_tmax_uk(metoffice, "<html>Maintenance</html>")

    assert run.status == IngestionRun.Status.FAILED
    assert run.errors[0]["error"].startswith("ParseError: header row not found")
    assert Observation.objects.count() == TMAX_UK_ROWS
    assert set(Observation.objects.values_list("ingestion_run", flat=True)) == {first.pk}


def test_database_error_in_one_file_rolls_back_only_that_file(metoffice):
    serve(metoffice, "Tmax", "UK", body=TMAX_UK)
    serve(metoffice, "Tmax", "Wales", body=TMAX_UK)
    real_upsert = ingest._upsert

    def flaky(run, region, *args):
        if region.code == "Wales":
            real_upsert(run, region, *args)  # rows written, then the transaction fails
            raise RuntimeError("disk full")
        return real_upsert(run, region, *args)

    with mock.patch.object(ingest, "_upsert", side_effect=flaky):
        run = run_ingest(["UK", "Wales"], ["Tmax"])

    assert run.status == IngestionRun.Status.PARTIAL
    assert "RuntimeError: disk full" in run.errors[0]["error"]
    assert Observation.objects.filter(region__code="Wales").count() == 0
    assert Observation.objects.filter(region__code="UK").count() == TMAX_UK_ROWS


def test_records_how_fresh_the_met_office_data_is(metoffice):
    run = ingest_tmax_uk(metoffice)
    local = timezone.localtime(run.source_updated_at)
    assert (local.date().isoformat(), local.strftime("%H:%M")) == ("2026-09-01", "11:56")


def test_waits_between_requests(metoffice, settings):
    """Invariant 14: a pause between files, none before the first."""
    settings.METOFFICE_REQUEST_DELAY = 0.25
    for region in ("UK", "Wales", "Scotland"):
        serve(metoffice, "Tmax", region, body=TMAX_UK)
    with mock.patch.object(ingest.time, "sleep") as sleep:
        run_ingest(["UK", "Wales", "Scotland"], ["Tmax"])
    assert sleep.call_args_list == [mock.call(0.25), mock.call(0.25)]


def test_run_is_closed_even_if_interrupted(metoffice):
    with (
        mock.patch.object(ingest, "fetch_text", side_effect=KeyboardInterrupt),
        pytest.raises(KeyboardInterrupt),
    ):
        run_ingest(["UK"], ["Tmax"])
    run = IngestionRun.objects.get()
    assert run.status == IngestionRun.Status.FAILED
    assert run.finished_at is not None


# --- management command -----------------------------------------------------------------------


def test_command_ingests_and_prints_a_summary(metoffice, capsys):
    serve(metoffice, "Tmax", "UK", body=TMAX_UK)
    call_command("ingest_metoffice", "--regions", "UK", "--parameters", "Tmax")
    out = capsys.readouterr().out
    assert "success" in out
    assert "Files 1/1 succeeded, 2,424 rows upserted" in out
    assert "Tmax" in out and "1884-2026" in out


def test_command_rejects_unknown_codes():
    with pytest.raises(CommandError, match=r"unknown code.*Atlantis"):
        call_command("ingest_metoffice", "--regions", "UK,Atlantis")


def test_command_fails_when_every_file_fails(metoffice, capsys):
    serve(metoffice, "Tmax", "UK", status=404)
    with pytest.raises(CommandError, match="every file failed"):
        call_command("ingest_metoffice", "--regions", "UK", "--parameters", "Tmax")
    assert "FAILED" in capsys.readouterr().err


# --- admin trigger ----------------------------------------------------------------------------


def test_background_ingest_starts_a_thread():
    with mock.patch.object(ingest.threading, "Thread") as thread:
        run = start_background_ingest()
    assert run.status == IngestionRun.Status.RUNNING
    thread.assert_called_once_with(target=ingest._ingest_in_thread, args=(run.pk,), daemon=True)
    thread.return_value.start.assert_called_once()


def test_background_ingest_refuses_while_another_is_running():
    IngestionRun.objects.create()
    assert start_background_ingest() is None


def test_stale_running_row_does_not_block_a_new_ingest():
    IngestionRun.objects.create(started_at=timezone.now() - timedelta(hours=2))
    with mock.patch.object(ingest.threading, "Thread"):
        assert start_background_ingest() is not None


def test_thread_body_runs_the_ingest_and_releases_its_connection():
    run = IngestionRun.objects.create()
    with (
        mock.patch.object(ingest, "run_ingest") as run_ingest_mock,
        mock.patch.object(ingest.connection, "close") as close,
    ):
        ingest._ingest_in_thread(run.pk)
    assert run_ingest_mock.call_args.kwargs["run"] == run
    close.assert_called_once()


def test_admin_button_starts_an_ingest(admin_client):
    with mock.patch("climate.admin.start_background_ingest") as start:
        start.return_value = IngestionRun(pk=7)
        response = admin_client.post("/admin/climate/ingestionrun/run-ingest/", follow=True)
    start.assert_called_once()
    assert b"Ingest run #7 started" in response.content
    assert b"Run ingest now" in response.content


def test_admin_button_reports_an_ingest_already_running(admin_client):
    with mock.patch("climate.admin.start_background_ingest", return_value=None):
        response = admin_client.post("/admin/climate/ingestionrun/run-ingest/", follow=True)
    assert b"already running" in response.content


def test_admin_button_is_post_only_and_superuser_only(admin_client, client, django_user_model):
    assert admin_client.get("/admin/climate/ingestionrun/run-ingest/").status_code == 405
    staff = django_user_model.objects.create_user("staff", password="x", is_staff=True)
    client.force_login(staff)
    with mock.patch("climate.admin.start_background_ingest") as start:
        assert client.post("/admin/climate/ingestionrun/run-ingest/").status_code == 403
    start.assert_not_called()


@pytest.mark.parametrize("status", [IngestionRun.Status.SUCCESS, IngestionRun.Status.PARTIAL])
def test_if_needed_skips_once_an_ingest_has_completed(capsys, status):
    IngestionRun.objects.create(status=status, finished_at=timezone.now())
    with mock.patch("climate.management.commands.ingest_metoffice.run_ingest") as run:
        call_command("ingest_metoffice", "--if-needed")
    run.assert_not_called()
    assert "already completed" in capsys.readouterr().out


@pytest.mark.parametrize(
    "earlier",
    [
        None,  # empty database: first boot
        {"status": IngestionRun.Status.RUNNING},  # container killed mid-ingest
        {"status": IngestionRun.Status.FAILED, "finished_at": "now"},  # Met Office was down
    ],
)
def test_if_needed_ingests_until_one_completes(metoffice, earlier):
    if earlier:
        if earlier.get("finished_at"):
            earlier = {**earlier, "finished_at": timezone.now()}
        IngestionRun.objects.create(**earlier)
    serve(metoffice, "Tmax", "UK", body=TMAX_UK)
    call_command("ingest_metoffice", "--if-needed", "--regions", "UK", "--parameters", "Tmax")
    assert Observation.objects.count() == TMAX_UK_ROWS
