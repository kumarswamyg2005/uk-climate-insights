"""Read-side query functions shared by the REST API and the LLM chat tools.

Every function that takes arguments validates them itself, with the serializers below, against the
catalog whitelists (invariant 8). REST views and chat tools both call these functions, so neither
can reach the ORM with unchecked input. Bad input raises rest_framework ValidationError, which DRF
turns into HTTP 400 and the chat service turns into an error message for the model.
"""

from collections.abc import Mapping
from typing import Any

from django.db.models import Max, Min
from rest_framework import serializers

from .catalog import PARAMETER_CODES, PARAMETERS, REGION_CODES, REGIONS
from .invariants import MAX_YEAR, MIN_YEAR
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
