from django.contrib import admin
from django.db import models
from django.db.models import Count

from .models import IngestionRun, Observation, Parameter, Region


class ReadOnlyAdmin(admin.ModelAdmin):
    """Data comes from the ingest, codes from catalog.py: the admin only reads."""

    formfield_overrides = {models.URLField: {"assume_scheme": "https"}}  # Django 6.0 default

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Region)
class RegionAdmin(ReadOnlyAdmin):
    list_display = ["code", "name", "slug", "observation_count"]
    search_fields = ["code", "name"]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_observations=Count("observations"))

    @admin.display(description="Observations", ordering="_observations")
    def observation_count(self, obj):
        return obj._observations


@admin.register(Parameter)
class ParameterAdmin(ReadOnlyAdmin):
    list_display = ["code", "name", "unit"]


@admin.register(Observation)
class ObservationAdmin(ReadOnlyAdmin):
    list_display = ["region", "parameter", "year", "period", "value", "ingestion_run", "updated_at"]
    list_filter = ["parameter", "period", "region"]
    list_select_related = ["region", "parameter", "ingestion_run"]
    ordering = ["region", "parameter", "-year", "period"]
    show_full_result_count = False  # skip a second COUNT(*) over ~280k rows on filtered pages


@admin.register(IngestionRun)
class IngestionRunAdmin(ReadOnlyAdmin):
    list_display = [
        "id",
        "status",
        "started_at",
        "finished_at",
        "files_succeeded",
        "files_attempted",
        "rows_upserted",
        "error_count",
    ]
    list_filter = ["status"]

    @admin.display(description="Errors")
    def error_count(self, obj):
        return len(obj.errors)
