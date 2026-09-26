"""The only things the model can do: six read-only functions over the shared query layer.

Every call is validated by the same serializers the REST API uses (queries.py), against the catalog
whitelists, before it touches the ORM. The model never sees SQL or the database (invariant 9).
Short code lists are enums in the schemas; the 17 region codes are listed once in the system prompt
rather than repeated in five schemas, which keeps each LLM round within Groq's free-tier budget.
"""

import json
from collections.abc import Callable
from typing import Any

from rest_framework.exceptions import ValidationError

from climate import queries
from climate.catalog import PARAMETER_CODES
from climate.invariants import MAX_COMPARE_REGIONS, MAX_YEAR, MIN_YEAR
from climate.periods import PERIOD_ORDER

_REGION = {"type": "string", "description": "region code from the list in the instructions"}
_PARAMETER = {"type": "string", "enum": list(PARAMETER_CODES)}
_PERIOD = {"type": "string", "enum": list(PERIOD_ORDER)}  # explained once, in the system prompt
_YEAR = {"type": "integer", "minimum": MIN_YEAR, "maximum": MAX_YEAR}
_SERIES_ARGS = {
    "region": _REGION,
    "parameter": _PARAMETER,
    "period": _PERIOD,
    "year_from": _YEAR,
    "year_to": _YEAR,
}


def _spec(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


TOOL_SPECS = [
    _spec("list_regions", "The 17 regions with their codes and names.", {}, []),
    _spec(
        "list_parameters",
        "The measures with units and the first and last year held in the database.",
        {},
        [],
    ),
    _spec(
        "get_series",
        "Every yearly value of one region, measure and period, oldest first.",
        _SERIES_ARGS,
        ["region", "parameter", "period"],
    ),
    _spec(
        "get_extreme",
        "Highest (kind=max) or lowest (kind=min) years of a series, ranked; limit defaults to 5.",
        {
            **_SERIES_ARGS,
            "kind": {"type": "string", "enum": ["max", "min"]},
            "limit": {"type": "integer", "minimum": 1, "maximum": 20},
        },
        ["region", "parameter", "period", "kind"],
    ),
    _spec(
        "get_summary",
        "Count, mean, min/max with years, latest value and linear trend per decade of a series.",
        _SERIES_ARGS,
        ["region", "parameter", "period"],
    ),
    _spec(
        "compare_regions",
        f"Up to {MAX_COMPARE_REGIONS} regions' values for one measure and period, aligned by year.",
        {
            "regions": {
                "type": "array",
                "items": _REGION,
                "minItems": 1,
                "maxItems": MAX_COMPARE_REGIONS,
            },
            "parameter": _PARAMETER,
            "period": _PERIOD,
            "year_from": _YEAR,
            "year_to": _YEAR,
        },
        ["regions", "parameter", "period"],
    ),
]

FUNCTIONS: dict[str, Callable[[dict], Any]] = {
    "list_regions": lambda args: queries.list_regions(),
    "list_parameters": lambda args: queries.list_parameters(),
    "get_series": queries.get_series,
    "get_extreme": queries.get_extreme,
    "get_summary": queries.get_summary,
    "compare_regions": queries.compare_regions,
}


def run_tool(name: str, arguments: str) -> tuple[dict, Any, bool]:
    """Run one model-requested call. Returns (parsed args, result or error, ok).

    Errors are returned, not raised, so the model can read them and correct its next call.
    """
    function = FUNCTIONS.get(name)
    if function is None:
        return {}, {"error": f"Unknown tool {name!r}. Available: {', '.join(FUNCTIONS)}."}, False
    try:
        args = json.loads(arguments or "{}")
    except (ValueError, RecursionError):  # malformed, or nested deeply enough to blow the stack
        return {}, {"error": "Arguments must be a JSON object."}, False
    if not isinstance(args, dict):
        return {}, {"error": "Arguments must be a JSON object."}, False
    try:
        return args, function(args), True
    except ValidationError as exc:
        return args, {"error": "Invalid arguments.", "details": exc.detail}, False
