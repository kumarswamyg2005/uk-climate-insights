"""One ingestion run: fetch, parse and upsert each region x parameter file in a transaction."""

import logging
import threading
import time
from collections.abc import Iterable
from datetime import timedelta

import requests
from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
from django.utils.text import slugify

from .catalog import PARAMETER_CODES, PARAMETERS, REGION_CODES, REGIONS
from .fetching import fetch_text, make_session, series_url
from .models import IngestionRun, Observation, Parameter, Region
from .parsing import ParseError, parse_metoffice_series

logger = logging.getLogger(__name__)

# A "running" row older than this is assumed dead (e.g. the worker was restarted mid-run).
STALE_RUN_AFTER = timedelta(minutes=30)


def sync_catalog() -> tuple[dict[str, Region], dict[str, Parameter]]:
    """Mirror catalog.py into the Region/Parameter tables (idempotent)."""
    regions = {
        code: Region.objects.update_or_create(
            code=code, defaults={"name": name, "slug": slugify(code.replace("_", "-"))}
        )[0]
        for code, name in REGIONS.items()
    }
    parameters = {
        code: Parameter.objects.update_or_create(
            code=code,
            defaults={"name": info.name, "unit": info.unit, "description": info.description},
        )[0]
        for code, info in PARAMETERS.items()
    }
    return regions, parameters


def run_ingest(
    region_codes: Iterable[str] | None = None,
    parameter_codes: Iterable[str] | None = None,
    *,
    delay: float | None = None,
    run: IngestionRun | None = None,
) -> IngestionRun:
    """Ingest the selected files (default: all 119). A failing file is recorded and skipped."""
    region_codes = list(region_codes or REGION_CODES)
    parameter_codes = list(parameter_codes or PARAMETER_CODES)
    delay = settings.METOFFICE_REQUEST_DELAY if delay is None else delay

    regions, parameters = sync_catalog()
    run = run or IngestionRun.objects.create()
    session = make_session()
    try:
        for parameter_code in parameter_codes:
            for region_code in region_codes:
                if run.files_attempted:
                    time.sleep(delay)  # invariant 14: be polite to the Met Office
                _ingest_file(run, regions[region_code], parameters[parameter_code], session)
    finally:
        # Also runs if something escapes the per-file handler (e.g. KeyboardInterrupt).
        if run.files_attempted and run.files_succeeded == run.files_attempted:
            run.status = IngestionRun.Status.SUCCESS
        elif run.files_succeeded:
            run.status = IngestionRun.Status.PARTIAL
        else:
            run.status = IngestionRun.Status.FAILED
        run.finished_at = timezone.now()
        run.save()
    return run


def _ingest_file(
    run: IngestionRun, region: Region, parameter: Parameter, session: requests.Session
) -> None:
    url = series_url(parameter.code, region.code)
    run.files_attempted += 1
    try:
        series = parse_metoffice_series(fetch_text(url, session))
        with transaction.atomic():
            written = _upsert(run, region, parameter, url, series.records)
            # Rows this run didn't write are no longer in the source file: drop them.
            Observation.objects.filter(region=region, parameter=parameter).exclude(
                ingestion_run=run
            ).delete()
    except Exception as exc:  # invariant 6: one bad file never aborts the run
        expected = isinstance(exc, requests.RequestException | ParseError)
        logger.warning("ingest failed for %s: %s", url, exc, exc_info=not expected)
        run.errors.append({"url": url, "error": f"{type(exc).__name__}: {exc}"})
    else:
        run.files_succeeded += 1
        run.rows_upserted += written
        if series.last_updated:
            stamp = timezone.make_aware(series.last_updated)  # UK local time in the file
            run.source_updated_at = max(filter(None, [run.source_updated_at, stamp]))
    # Save after every file so the admin shows progress while a run is going.
    run.save()


def _upsert(run, region, parameter, url, records) -> int:
    """INSERT ... ON CONFLICT (region, parameter, year, period) DO UPDATE, in batches."""
    Observation.objects.bulk_create(
        [
            Observation(
                region=region,
                parameter=parameter,
                year=r.year,
                period=r.period,
                value=r.value,
                source_url=url,
                ingestion_run=run,
            )
            for r in records
        ],
        batch_size=1000,
        update_conflicts=True,
        unique_fields=["region", "parameter", "year", "period"],
        update_fields=["value", "source_url", "ingestion_run", "updated_at"],
    )
    return len(records)


def start_background_ingest() -> IngestionRun | None:
    """Start a full ingest in a thread and return its run, or None if one is already going.

    ponytail: a daemon thread in the web worker. It dies if the worker restarts (the run then
    shows as stale "running"). Move to a job runner / Render cron if ingests must be durable.
    """
    if IngestionRun.objects.filter(
        status=IngestionRun.Status.RUNNING, started_at__gte=timezone.now() - STALE_RUN_AFTER
    ).exists():
        return None
    run = IngestionRun.objects.create()
    threading.Thread(target=_ingest_in_thread, args=(run.pk,), daemon=True).start()
    return run


def _ingest_in_thread(run_id: int) -> None:
    try:
        run_ingest(run=IngestionRun.objects.get(pk=run_id))
    except Exception:
        logger.exception("background ingest %s crashed", run_id)
    finally:
        connection.close()  # each thread gets its own DB connection; don't leak it
