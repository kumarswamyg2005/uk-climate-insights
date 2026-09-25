import django_filters
from django import forms

from climate.catalog import PARAMETER_CODES, REGION_CODES
from climate.invariants import MAX_YEAR, MIN_YEAR
from climate.models import Observation
from climate.periods import PERIOD_ORDER


def code_filter(field_name: str, codes: tuple[str, ...], what: str):
    return django_filters.ChoiceFilter(
        field_name=field_name,
        choices=[(code, code) for code in codes],
        error_messages={
            "invalid_choice": f'Unknown {what} "%(value)s". Valid: {", ".join(codes)}.'
        },
    )


class YearFilter(django_filters.NumberFilter):
    field_class = forms.IntegerField  # NumberFilter defaults to Decimal, which accepts 1990.5


class ObservationFilterForm(forms.Form):
    def clean(self):
        data = super().clean()
        year_from, year_to = data.get("year_from"), data.get("year_to")
        if year_from is not None and year_to is not None and year_from > year_to:
            self.add_error(
                "year_from", f"year_from ({year_from}) must not be after year_to ({year_to})."
            )
        return data


class ObservationFilter(django_filters.FilterSet):
    region = code_filter("region__code", REGION_CODES, "region")
    parameter = code_filter("parameter__code", PARAMETER_CODES, "parameter")
    period = code_filter("period", PERIOD_ORDER, "period")
    year_from = YearFilter(
        field_name="year", lookup_expr="gte", min_value=MIN_YEAR, max_value=MAX_YEAR
    )
    year_to = YearFilter(
        field_name="year", lookup_expr="lte", min_value=MIN_YEAR, max_value=MAX_YEAR
    )
    ordering = django_filters.OrderingFilter(
        fields=[("year", "year"), ("value", "value")],
        help_text="year, -year, value or -value",
    )

    class Meta:
        model = Observation
        fields = []
        form = ObservationFilterForm

    def filter_queryset(self, queryset):
        # Tie-break on id so pages never overlap or skip rows when sorting by year or value.
        queryset = super().filter_queryset(queryset)
        return queryset.order_by(*queryset.query.order_by, "id")
