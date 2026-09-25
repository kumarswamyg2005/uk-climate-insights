"""The 17 period columns of a Met Office series file, in file order.

Winter ("win") is Dec of the previous year + Jan + Feb, and is labelled with the Jan/Feb year:
2026 "win" = Dec 2025 to Feb 2026. Verified against the files: temperature seasons are the
day-weighted mean of the three months, the other parameters are the sum.
"""

MONTH_PERIODS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
SEASON_PERIODS = ("win", "spr", "sum", "aut")
ANNUAL_PERIOD = "ann"
PERIOD_ORDER = (*MONTH_PERIODS, *SEASON_PERIODS, ANNUAL_PERIOD)

PERIOD_LABELS = {
    "jan": "January",
    "feb": "February",
    "mar": "March",
    "apr": "April",
    "may": "May",
    "jun": "June",
    "jul": "July",
    "aug": "August",
    "sep": "September",
    "oct": "October",
    "nov": "November",
    "dec": "December",
    "win": "Winter (Dec-Feb)",
    "spr": "Spring (Mar-May)",
    "sum": "Summer (Jun-Aug)",
    "aut": "Autumn (Sep-Nov)",
    "ann": "Annual",
}

PERIOD_CHOICES = [(code, PERIOD_LABELS[code]) for code in PERIOD_ORDER]
