"""Parser for Met Office "UK and regional series" year-ordered text files.

Format (checked on all 119 files):

    <5 lines of free-text preamble>
    year    jan    feb  ...    dec     win     spr     sum     aut     ann
    1884    7.3    6.8  ...    5.8     ---   11.02   18.73   12.10   12.14
    ...
    2026    6.0    7.9  ...                  7.43   13.87   21.31

Values are right-aligned under their header names. The current, partial year leaves blank space
where months haven't happened yet, so splitting on whitespace would slide later values into the
wrong columns. Instead, each value is assigned to the header column whose right edge it shares.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from .periods import PERIOD_ORDER

HEADER = ("year", *PERIOD_ORDER)
_TOKEN = re.compile(r"\S+")
_YEAR = re.compile(r"\d{4}")
# Fits Observation.value = Decimal(8, 2) exactly. Stricter than Decimal(), which accepts "NaN".
_NUMBER = re.compile(r"-?\d{1,6}(\.\d{1,2})?")
_MISSING = re.compile(r"-+")  # the files use "---"; any run of dashes means "no value"
_LAST_UPDATED = re.compile(r"Last updated (\d{2}-[A-Za-z]{3}-\d{4} \d{2}:\d{2})")


class ParseError(ValueError):
    """The text is not a series file we understand. `line_no` is 1-based, None if file-wide."""

    def __init__(self, message: str, line_no: int | None = None):
        self.line_no = line_no
        super().__init__(f"line {line_no}: {message}" if line_no else message)


@dataclass(frozen=True)
class Record:
    year: int
    period: str
    value: Decimal


@dataclass(frozen=True)
class ParsedSeries:
    records: list[Record]
    preamble: tuple[str, ...]  # the free-text lines above the header
    last_updated: datetime | None  # "Last updated 01-Sep-2026 11:56", UK local time


def parse_metoffice_series(text: str) -> ParsedSeries:
    lines = text.splitlines()
    header_index = next((i for i, line in enumerate(lines) if tuple(line.split()) == HEADER), None)
    if header_index is None:
        raise ParseError(f"header row not found (expected columns: {' '.join(HEADER)})")
    header_matches = _TOKEN.finditer(lines[header_index])
    column_at_edge = {m.end(): name for m, name in zip(header_matches, HEADER, strict=True)}

    records: list[Record] = []
    seen_years: set[int] = set()
    for line_no, line in enumerate(lines[header_index + 1 :], start=header_index + 2):
        if not line.strip():
            continue
        cells = {}
        for match in _TOKEN.finditer(line):
            column = column_at_edge.get(match.end())
            if column is None:
                raise ParseError(
                    f"value {match.group()!r} at column {match.start() + 1} does not line up "
                    "with any header column",
                    line_no,
                )
            cells[column] = match.group()

        raw_year = cells.pop("year", "")
        if not _YEAR.fullmatch(raw_year):
            raise ParseError(f"expected a 4-digit year, got {raw_year!r}", line_no)
        year = int(raw_year)
        if year in seen_years:
            raise ParseError(f"duplicate year {year}", line_no)
        seen_years.add(year)

        for period, raw in cells.items():
            if _MISSING.fullmatch(raw):
                continue  # invariant 1: missing is "no row", never 0
            if not _NUMBER.fullmatch(raw):
                raise ParseError(
                    f"{period} value {raw!r} is not a number with at most 2 decimals", line_no
                )
            value = Decimal(raw)
            if value.is_zero():
                value = abs(value)  # the files print tiny negatives as "-0.0"
            records.append(Record(year, period, value))

    if not records:
        raise ParseError("no data rows after the header")

    preamble = tuple(line.strip() for line in lines[:header_index] if line.strip())
    stamp = next(filter(None, map(_LAST_UPDATED.search, preamble)), None)
    last_updated = datetime.strptime(stamp.group(1), "%d-%b-%Y %H:%M") if stamp else None
    return ParsedSeries(records, preamble, last_updated)
