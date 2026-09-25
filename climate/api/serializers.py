"""Output serializers. The plain Serializers document response shapes in the OpenAPI schema."""

from rest_framework import serializers

from climate.models import IngestionRun, Observation


class ObservationSerializer(serializers.ModelSerializer):
    region = serializers.CharField(source="region.code")
    parameter = serializers.CharField(source="parameter.code")
    unit = serializers.CharField(source="parameter.unit")
    ingestion_run = serializers.IntegerField(source="ingestion_run_id")

    class Meta:
        model = Observation
        fields = [
            "region",
            "parameter",
            "year",
            "period",
            "value",
            "unit",
            "source_url",
            "ingestion_run",
            "updated_at",
        ]


class IngestionRunSerializer(serializers.ModelSerializer):
    # Only the count: error text can contain internals that don't belong on a public endpoint.
    error_count = serializers.SerializerMethodField()

    class Meta:
        model = IngestionRun
        fields = [
            "id",
            "status",
            "started_at",
            "finished_at",
            "files_attempted",
            "files_succeeded",
            "rows_upserted",
            "error_count",
            "source_updated_at",
        ]

    def get_error_count(self, run) -> int:
        return len(run.errors)


class RegionSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    slug = serializers.CharField()


class ParameterSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    unit = serializers.CharField()
    description = serializers.CharField()
    first_year = serializers.IntegerField(allow_null=True)
    last_year = serializers.IntegerField(allow_null=True)


class SeriesMetaSerializer(serializers.Serializer):
    region = serializers.CharField()
    region_name = serializers.CharField()
    parameter = serializers.CharField()
    parameter_name = serializers.CharField()
    period = serializers.CharField()
    period_name = serializers.CharField()
    unit = serializers.CharField()


class SeriesSerializer(SeriesMetaSerializer):
    points = serializers.ListField(
        child=serializers.ListField(child=serializers.FloatField()),
        help_text="[[year, value], ...] in year order; years without a value are omitted.",
    )


class ExtremeValueSerializer(serializers.Serializer):
    value = serializers.FloatField()
    years = serializers.ListField(child=serializers.IntegerField(), help_text="all tied years")


class YearValueSerializer(serializers.Serializer):
    year = serializers.IntegerField()
    value = serializers.FloatField()


class SummarySerializer(SeriesMetaSerializer):
    count = serializers.IntegerField()
    first_year = serializers.IntegerField(allow_null=True)
    last_year = serializers.IntegerField(allow_null=True)
    mean = serializers.FloatField(allow_null=True)
    min = ExtremeValueSerializer(allow_null=True)
    max = ExtremeValueSerializer(allow_null=True)
    latest = YearValueSerializer(allow_null=True)
    trend_per_decade = serializers.FloatField(
        allow_null=True, help_text="least-squares slope over the selected years, in unit/decade"
    )


class ExtremeSerializer(SeriesMetaSerializer):
    kind = serializers.ChoiceField(choices=["max", "min"])
    rows = YearValueSerializer(many=True)


class RegionNameSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()


class CompareSerializer(serializers.Serializer):
    parameter = serializers.CharField()
    parameter_name = serializers.CharField()
    period = serializers.CharField()
    period_name = serializers.CharField()
    unit = serializers.CharField()
    regions = RegionNameSerializer(many=True)
    years = serializers.ListField(child=serializers.IntegerField())
    values = serializers.DictField(
        child=serializers.ListField(child=serializers.FloatField(allow_null=True)),
        help_text="region code -> values aligned with `years` (null where missing)",
    )
