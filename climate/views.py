from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.shortcuts import render

from . import queries
from .catalog import PARAMETERS, REGIONS, SOURCE_PAGE_URL
from .invariants import MAX_COMPARE_REGIONS
from .periods import MONTH_PERIODS, PERIOD_LABELS, SEASON_PERIODS

DEFAULTS = {"region": "UK", "parameter": "Tmean", "period": "ann"}
DEFAULT_COMPARE_REGIONS = ["England", "Wales", "Scotland", "Northern_Ireland"]


def _choices() -> dict:
    return {
        "regions": list(REGIONS.items()),
        "parameters": [(code, info.name, info.unit) for code, info in PARAMETERS.items()],
        "period_groups": [
            ("Year", [("ann", PERIOD_LABELS["ann"])]),
            ("Seasons", [(p, PERIOD_LABELS[p]) for p in SEASON_PERIODS]),
            ("Months", [(p, PERIOD_LABELS[p]) for p in MONTH_PERIODS]),
        ],
        "source_url": SOURCE_PAGE_URL,
    }


def _selected(request) -> dict:
    """Pre-select the form from the query string; unknown values fall back to defaults."""
    valid = {"region": REGIONS, "parameter": PARAMETERS, "period": PERIOD_LABELS}
    return {
        key: request.GET[key] if request.GET.get(key) in valid[key] else DEFAULTS[key]
        for key in DEFAULTS
    }


def explorer(request):
    return render(
        request,
        "climate/explorer.html",
        {**_choices(), "selected": _selected(request), "nav": "explore"},
    )


def compare(request):
    codes = [c for c in request.GET.get("regions", "").split(",") if c in REGIONS]
    selected = {
        **_selected(request),
        "regions": list(dict.fromkeys(codes))[:MAX_COMPARE_REGIONS] or DEFAULT_COMPARE_REGIONS,
    }
    return render(
        request,
        "climate/compare.html",
        {
            **_choices(),
            "selected": selected,
            "max_regions": MAX_COMPARE_REGIONS,
            "nav": "compare",
        },
    )


def about(request):
    return render(
        request,
        "climate/about.html",
        {**_choices(), "coverage": queries.list_parameters(), "nav": "about"},
    )


def healthz(request):
    """Liveness plus a real round-trip to the database, so a broken DB fails the healthcheck."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        return JsonResponse({"status": "error", "db": "unreachable"}, status=503)
    return JsonResponse({"status": "ok", "db": "ok"})
