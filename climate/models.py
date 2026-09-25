from django.db import models
from django.db.models import Q
from django.utils import timezone

from .periods import PERIOD_CHOICES, PERIOD_ORDER


class Region(models.Model):
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=60, unique=True)

    class Meta:
        ordering = ["id"]  # catalog order: the ingest seeds regions in the Met Office's order

    def __str__(self):
        return self.name


class Parameter(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=60)
    unit = models.CharField(max_length=10)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.name} ({self.unit})"


class IngestionRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running"
        SUCCESS = "success"
        PARTIAL = "partial"
        FAILED = "failed"

    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RUNNING)
    files_attempted = models.PositiveIntegerField(default=0)
    files_succeeded = models.PositiveIntegerField(default=0)
    rows_upserted = models.PositiveIntegerField(default=0)
    errors = models.JSONField(default=list, blank=True)  # [{"url": ..., "error": ...}]

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"Run #{self.pk} ({self.status})"


class Observation(models.Model):
    """One value from one cell of a Met Office file. A missing cell is a missing row, never 0."""

    region = models.ForeignKey(Region, on_delete=models.PROTECT, related_name="observations")
    parameter = models.ForeignKey(Parameter, on_delete=models.PROTECT, related_name="observations")
    year = models.PositiveSmallIntegerField()
    period = models.CharField(max_length=3, choices=PERIOD_CHOICES)
    value = models.DecimalField(max_digits=8, decimal_places=2)
    # Provenance: overwritten on every upsert, so they name the run and file that last confirmed it.
    source_url = models.URLField()
    ingestion_run = models.ForeignKey(
        IngestionRun, on_delete=models.PROTECT, related_name="observations"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["region", "parameter", "year", "period"],
                name="observation_unique_region_parameter_year_period",
            ),
            models.CheckConstraint(
                condition=Q(period__in=PERIOD_ORDER), name="observation_period_valid"
            ),
        ]
        indexes = [
            # Every read filters region + parameter + period and orders by year.
            models.Index(
                fields=["region", "parameter", "period", "year"], name="observation_series"
            ),
        ]

    def __str__(self):
        return f"{self.region.code} {self.parameter.code} {self.year} {self.period} = {self.value}"
