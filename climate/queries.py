"""Read-side query functions shared by the REST API and the LLM chat tools.

Every function that takes arguments validates them itself, with the serializers below, against the
catalog whitelists (invariant 8). REST views and chat tools both call these functions, so neither
can reach the ORM with unchecked input. Bad input raises rest_framework ValidationError, which DRF
turns into HTTP 400 and the chat service turns into an error message for the model.
"""

import statistics
from collections.abc import Mapping
from typing import Any

from django.db.models import Max, Min
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .catalog import PARAMETER_CODES, PARAMETERS, REGION_CODES, REGIONS
from .invariants import MAX_COMPARE_REGIONS, MAX_YEAR, MIN_YEAR
from .models import Observation, Parameter, Region
from .periods import PERIOD_LABELS, PERIOD_ORDER


def code_field(codes: tuple[str, ...], what: str, **kwargs) -> serializers.ChoiceField:
    return serializers.ChoiceField(
        choices=codes,
        error_messages={
            "invalid_choice": f'Unknown {what} "{{input}}". Valid: {", ".join(codes)}.'
        },
        **kwargs,
    )


class YearRangeQuery(serializers.Serializer):
    year_from = serializers.IntegerField(required=False, min_value=MIN_YEAR, max_value=MAX_YEAR)
    year_to = serializers.IntegerField(required=False, min_value=MIN_YEAR, max_value=MAX_YEAR)

    def validate(self, attrs):
        year_from, year_to = attrs.get("year_from"), attrs.get("year_to")
        if year_from is not None and year_to is not None and year_from > year_to:
            raise serializers.ValidationError(
                {"year_from": f"year_from ({year_from}) must not be after year_to ({year_to})."}
            )
        return attrs


class SeriesQuery(YearRangeQuery):
    region = code_field(REGION_CODES, "region")
    parameter = code_field(PARAMETER_CODES, "parameter")
    period = code_field(PERIOD_ORDER, "period")


class ExtremeQuery(SeriesQuery):
    kind = serializers.ChoiceField(
        choices=["max", "min"],
        error_messages={"invalid_choice": 'Unknown kind "{input}". Valid: max, min.'},
    )
    limit = serializers.IntegerField(required=False, default=5, min_value=1, max_value=20)


@extend_schema_field(OpenApiTypes.STR)
class RegionListField(serializers.Field):
    """Up to MAX_COMPARE_REGIONS region codes, as "UK,Wales" (query string) or a JSON list."""

    def to_internal_value(self, data):
        items = data.split(",") if isinstance(data, str) else data
        if not isinstance(items, list) or not all(isinstance(i, str) for i in items):
            raise serializers.ValidationError("Give region codes as a comma-separated string.")
        codes = list(dict.fromkeys(i.strip() for i in items if i.strip()))  # dedupe, keep order
        unknown = [c for c in codes if c not in REGIONS]
        if unknown:
            raise serializers.ValidationError(
                f"Unknown region(s) {', '.join(unknown)}. Valid: {', '.join(REGION_CODES)}."
            )
        if not codes:
            raise serializers.ValidationError("Give at least one region.")
        if len(codes) > MAX_COMPARE_REGIONS:
            raise serializers.ValidationError(
                f"Compare at most {MAX_COMPARE_REGIONS} regions (got {len(codes)})."
            )
        return codes

    def to_representation(self, value):
        return value


class CompareQuery(YearRangeQuery):
    regions = RegionListField(help_text="1-4 comma-separated region codes, e.g. England,Wales")
    parameter = code_field(PARAMETER_CODES, "parameter")
    period = code_field(PERIOD_ORDER, "period")


def validated(query_class: type[serializers.Serializer], params: Mapping[str, Any]) -> dict:
    query = query_class(data=params)
    query.is_valid(raise_exception=True)
    return query.validated_data


def _rows(region, parameter, period, year_from=None, year_to=None):
    """(year, value) rows of one series in year order, via the observation_series index."""
    rows = Observation.objects.filter(region__code=region, parameter__code=parameter, period=period)
    if year_from is not None:
        rows = rows.filter(year__gte=year_from)
    if year_to is not None:
        rows = rows.filter(year__lte=year_to)
    return rows.order_by("year").values_list("year", "value")


def _describe(region: str, parameter: str, period: str) -> dict:
    """Labels and the unit (invariant 4) for a response, from the catalog: no query needed."""
    return {
        "region": region,
        "region_name": REGIONS[region],
        "parameter": parameter,
        "parameter_name": PARAMETERS[parameter].name,
        "period": period,
        "period_name": PERIOD_LABELS[period],
        "unit": PARAMETERS[parameter].unit,
    }


def list_regions() -> list[dict]:
    return list(Region.objects.values("code", "name", "slug"))


def list_parameters() -> list[dict]:
    """Parameters with their unit and the years actually present in the database.

    ponytail: MIN/MAX scan all observations (~85 ms at 280k rows). If it gets hot, add an index on
    (parameter, year) and use per-parameter ORDER BY year LIMIT 1 subqueries.
    """
    return list(
        Parameter.objects.annotate(
            first_year=Min("observations__year"), last_year=Max("observations__year")
        )
        .order_by("id")  # Meta.ordering is ignored in GROUP BY queries
        .values("code", "name", "unit", "description", "first_year", "last_year")
    )


def get_series(params: Mapping[str, Any]) -> dict:
    q = validated(SeriesQuery, params)
    rows = _rows(**q)
    return {
        **_describe(q["region"], q["parameter"], q["period"]),
        "points": [[year, float(value)] for year, value in rows],
    }


def get_summary(params: Mapping[str, Any]) -> dict:
    """Count, mean, extremes (with every tied year), latest value and linear trend per decade."""
    q = validated(SeriesQuery, params)
    points = [(year, float(value)) for year, value in _rows(**q)]
    summary = {
        **_describe(q["region"], q["parameter"], q["period"]),
        "count": len(points),
        "first_year": None,
        "last_year": None,
        "mean": None,
        "min": None,
        "max": None,
        "latest": None,
        "trend_per_decade": None,
    }
    if not points:
        return summary

    years = [year for year, _ in points]
    values = [value for _, value in points]
    low, high = min(values), max(values)
    summary.update(
        first_year=years[0],
        last_year=years[-1],
        mean=round(statistics.fmean(values), 2),
        min={"value": low, "years": [y for y, v in points if v == low]},
        max={"value": high, "years": [y for y, v in points if v == high]},
        latest={"year": years[-1], "value": values[-1]},
    )
    if len(points) >= 2:
        slope, _ = statistics.linear_regression(years, values)  # ordinary least squares
        summary["trend_per_decade"] = round(slope * 10, 3)
    return summary


def get_extreme(params: Mapping[str, Any]) -> dict:
    """The `limit` highest (kind=max) or lowest (kind=min) years, ties broken by earlier year."""
    q = validated(ExtremeQuery, params)
    kind, limit = q.pop("kind"), q.pop("limit")
    rows = _rows(**q).order_by("-value" if kind == "max" else "value", "year")[:limit]
    return {
        **_describe(q["region"], q["parameter"], q["period"]),
        "kind": kind,
        "rows": [{"year": year, "value": float(value)} for year, value in rows],
    }


def compare_regions(params: Mapping[str, Any]) -> dict:
    """Several regions' series on one shared year axis; null where a region has no value."""
    q = validated(CompareQuery, params)
    rows = Observation.objects.filter(
        region__code__in=q["regions"], parameter__code=q["parameter"], period=q["period"]
    )
    if "year_from" in q:
        rows = rows.filter(year__gte=q["year_from"])
    if "year_to" in q:
        rows = rows.filter(year__lte=q["year_to"])

    by_region: dict[str, dict[int, float]] = {code: {} for code in q["regions"]}
    for code, year, value in rows.values_list("region__code", "year", "value"):
        by_region[code][year] = float(value)
    years = sorted(set().union(*by_region.values()))
    described = _describe(q["regions"][0], q["parameter"], q["period"])
    return {
        **{k: v for k, v in described.items() if not k.startswith("region")},
        "regions": [{"code": code, "name": REGIONS[code]} for code in q["regions"]],
        "years": years,
        "values": {code: [series.get(y) for y in years] for code, series in by_region.items()},
    }
