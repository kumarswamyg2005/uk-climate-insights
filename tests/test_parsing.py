"""Parser tests against real Met Office files (tests/fixtures, downloaded 2026-09-25).

Expected counts are worked out by hand from the files, not by re-running parser logic:
rows x 17 periods - 1 "---" (first-year winter) - 6 blank cells (2026 has no sep-dec, aut, ann).
"""

from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from climate.parsing import ParseError, parse_metoffice_series

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return (FIXTURES / name).read_text()


def values(series):
    return {(r.year, r.period): r.value for r in series.records}


@pytest.mark.parametrize(
    ("fixture", "first_year", "rows", "expected"),
    [
        ("Tmax_UK.txt", 1884, 143, 143 * 17 - 1 - 6),
        ("Tmin_Scotland.txt", 1884, 143, 143 * 17 - 1 - 6),
        ("Rainfall_Scotland.txt", 1836, 191, 191 * 17 - 1 - 6),
        ("Sunshine_England.txt", 1910, 117, 117 * 17 - 1 - 6),
        ("AirFrost_Wales.txt", 1931, 96, 96 * 17 - 1 - 6),
    ],
)
def test_real_files_parse_to_the_hand_counted_number_of_observations(
    fixture, first_year, rows, expected
):
    series = parse_metoffice_series(load(fixture))
    assert len(series.records) == expected
    years = sorted({r.year for r in series.records})
    assert years == list(range(first_year, first_year + rows))


def test_values_are_read_from_the_right_columns():
    got = values(parse_metoffice_series(load("Tmax_UK.txt")))
    assert got[(1884, "jan")] == Decimal("7.3")
    assert got[(1885, "win")] == Decimal("5.75")
    assert got[(2025, "ann")] == Decimal("14.01")


def test_dashes_mean_no_row_not_zero():
    """Invariant 1: 1884 winter needs Dec 1883, which doesn't exist, so the file has '---'."""
    got = values(parse_metoffice_series(load("Tmax_UK.txt")))
    assert (1884, "win") not in got
    assert (1884, "spr") in got


def test_partial_current_year_blank_cells_are_absent_and_nothing_shifts():
    got = values(parse_metoffice_series(load("Tmax_UK.txt")))
    assert got[(2026, "aug")] == Decimal("21.4")
    # The next value on the line is winter; a whitespace split would have put it in September.
    assert got[(2026, "win")] == Decimal("7.43")
    assert got[(2026, "sum")] == Decimal("21.31")
    for missing in ("sep", "oct", "nov", "dec", "aut", "ann"):
        assert (2026, missing) not in got


def test_real_zero_is_kept():
    got = values(parse_metoffice_series(load("AirFrost_Wales.txt")))
    assert got[(2026, "jun")] == Decimal("0.0")
    assert got[(2026, "win")] == Decimal("17.0")


def test_negative_values_and_negative_zero():
    got = values(parse_metoffice_series(load("Tmin_Scotland.txt")))
    assert got[(1963, "jan")] == Decimal("-3.9")
    assert got[(1963, "win")] == Decimal("-2.89")
    # The file prints Nov 2010 as "-0.0"; it must come out as a plain zero, not "-0.0".
    assert str(got[(2010, "nov")]) == "0.0"


def test_header_is_found_by_its_names_not_its_line_number():
    original = load("Tmax_UK.txt")
    longer = "An extra notice line\nAnother one\n\n" + original
    shorter = original.split("\n", 3)[3]  # drop the first 3 preamble lines
    expected = len(parse_metoffice_series(original).records)
    assert len(parse_metoffice_series(longer).records) == expected
    assert len(parse_metoffice_series(shorter).records) == expected


def test_windows_line_endings_are_accepted():
    text = load("AirFrost_Wales.txt")
    assert parse_metoffice_series(text.replace("\n", "\r\n")) == parse_metoffice_series(text)


def test_missing_header_raises_parse_error():
    with pytest.raises(ParseError, match="header"):
        parse_metoffice_series("<html>Service unavailable</html>\n")


def corrupt(line_no, old, new):
    """Tmax_UK.txt with one substitution on a 1-based line (line 6 is the header, 7 is 1884)."""
    lines = load("Tmax_UK.txt").split("\n")
    assert old in lines[line_no - 1]
    lines[line_no - 1] = lines[line_no - 1].replace(old, new, 1)
    return "\n".join(lines)


@pytest.mark.parametrize(
    ("line_no", "old", "new", "message"),
    [
        (7, "   6.8", "  6.8 ", "does not line up"),  # value shifted one column left
        (8, "7.3", "n/a", "not a number"),
        (9, "3.4", "NaN", "not a number"),  # Decimal() would accept this; we must not
        (9, "  3.7", "3.745", "not a number"),  # Decimal(8, 2) would silently round it
        (10, "1887", "18x7", "year"),
        (10, "1887", "1886", "duplicate year"),
    ],
)
def test_malformed_lines_raise_parse_error_with_line_number(line_no, old, new, message):
    with pytest.raises(ParseError, match=message) as exc:
        parse_metoffice_series(corrupt(line_no, old, new))
    assert exc.value.line_no == line_no
    assert str(exc.value).startswith(f"line {line_no}:")


def test_header_without_data_rows_is_an_error():
    header_only = "\n".join(load("Tmax_UK.txt").split("\n")[:6])
    with pytest.raises(ParseError, match="no data rows"):
        parse_metoffice_series(header_only)


def test_trailing_blank_lines_are_ignored():
    text = load("Sunshine_England.txt")
    assert parse_metoffice_series(text + "\n\n  \n") == parse_metoffice_series(text)


def test_header_metadata_is_kept():
    series = parse_metoffice_series(load("Rainfall_Scotland.txt"))
    assert series.last_updated == datetime(2026, 9, 1, 11, 57)
    assert len(series.preamble) == 5
    assert series.preamble[3] == "Areal series, starting in 1836"


def test_last_updated_is_optional():
    text = load("Tmax_UK.txt").replace("Last updated", "Updated")
    assert parse_metoffice_series(text).last_updated is None
