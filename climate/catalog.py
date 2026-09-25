"""Every region and parameter the Met Office publishes for the UK and regional series.

Single source of truth: the ingest mirrors this into the Region/Parameter tables, and every
whitelist (API filters, query validation, LLM tool schemas) is built from it.
Codes and region labels are taken from the form on
https://www.metoffice.gov.uk/research/climate/maps-and-data/uk-and-regional-series
"""

from dataclasses import dataclass

SOURCE_PAGE_URL = (
    "https://www.metoffice.gov.uk/research/climate/maps-and-data/uk-and-regional-series"
)

# code -> display name, in the order the Met Office lists them.
REGIONS: dict[str, str] = {
    "UK": "UK",
    "England": "England",
    "Wales": "Wales",
    "Scotland": "Scotland",
    "Northern_Ireland": "Northern Ireland",
    "England_and_Wales": "England & Wales",
    "England_N": "England N",
    "England_S": "England S",
    "Scotland_N": "Scotland N",
    "Scotland_E": "Scotland E",
    "Scotland_W": "Scotland W",
    "England_E_and_NE": "England E & NE",
    "England_NW_and_N_Wales": "England NW/Wales N",
    "Midlands": "Midlands",
    "East_Anglia": "East Anglia",
    "England_SW_and_S_Wales": "England SW/Wales S",
    "England_SE_and_Central_S": "England SE/Central S",
}


@dataclass(frozen=True)
class ParameterInfo:
    name: str
    unit: str
    description: str


_MEAN = "Seasonal and annual values are day-weighted means of the monthly values."
_TOTAL = "Seasonal and annual values are totals of the monthly values."

PARAMETERS: dict[str, ParameterInfo] = {
    "Tmax": ParameterInfo(
        "Max temperature", "°C", f"Mean of daily maximum air temperature. {_MEAN}"
    ),
    "Tmin": ParameterInfo(
        "Min temperature", "°C", f"Mean of daily minimum air temperature. {_MEAN}"
    ),
    "Tmean": ParameterInfo("Mean temperature", "°C", f"Mean air temperature. {_MEAN}"),
    "Sunshine": ParameterInfo("Sunshine", "hours", f"Total duration of bright sunshine. {_TOTAL}"),
    "Rainfall": ParameterInfo("Rainfall", "mm", f"Total precipitation amount. {_TOTAL}"),
    "Raindays1mm": ParameterInfo(
        "Rain days ≥1.0mm", "days", f"Number of days with at least 1 mm of precipitation. {_TOTAL}"
    ),
    "AirFrost": ParameterInfo(
        "Days of air frost", "days", f"Number of days with minimum temperature below 0 °C. {_TOTAL}"
    ),
}

REGION_CODES = tuple(REGIONS)
PARAMETER_CODES = tuple(PARAMETERS)
