import csv
from dataclasses import asdict

from django.http import HttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from climate import queries
from climate.chat import llm, service
from climate.models import IngestionRun, Observation

from .filters import ObservationFilter
from .serializers import (
    ChatRequestSerializer,
    ChatResponseSerializer,
    CompareSerializer,
    ExtremeSerializer,
    IngestionRunSerializer,
    ObservationSerializer,
    ParameterSerializer,
    RegionSerializer,
    SeriesSerializer,
    SummarySerializer,
)


class ObservationPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 1000

    def paginate_queryset(self, queryset, request, view=None):
        try:
            return super().paginate_queryset(queryset, request, view)
        except NotFound as exc:  # a bad ?page= is bad input: 400, not 404 (invariant 8)
            raise ValidationError({"page": [str(exc.detail)]}) from exc


class RegionListView(APIView):
    @extend_schema(responses=RegionSerializer(many=True))
    def get(self, request):
        return Response(queries.list_regions())


class ParameterListView(APIView):
    @extend_schema(responses=ParameterSerializer(many=True))
    def get(self, request):
        return Response(queries.list_parameters())


class ObservationListView(generics.ListAPIView):
    """Filtered, paginated observations. Each row carries its unit and provenance."""

    queryset = Observation.objects.select_related("region", "parameter").order_by("id")
    serializer_class = ObservationSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = ObservationFilter
    pagination_class = ObservationPagination


class SeriesView(APIView):
    """One region x parameter x period as compact chart points."""

    @extend_schema(parameters=[queries.SeriesQuery], responses=SeriesSerializer)
    def get(self, request):
        return Response(queries.get_series(request.query_params))


class SeriesCsvView(APIView):
    """The same series as /series/, as a CSV download (one row per year, unit on every row)."""

    @extend_schema(
        parameters=[queries.SeriesQuery],
        responses={(200, "text/csv"): OpenApiResponse(OpenApiTypes.STR, description="CSV file")},
    )
    def get(self, request):
        series = queries.get_series(request.query_params)
        filename = "_".join([series["region"], series["parameter"], series["period"]])
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'
        writer = csv.writer(response)
        writer.writerow(["region", "parameter", "period", "year", "value", "unit"])
        for year, value in series["points"]:
            writer.writerow(
                [
                    series["region"],
                    series["parameter"],
                    series["period"],
                    year,
                    value,
                    series["unit"],
                ]
            )
        return response


class SummaryView(APIView):
    """Count, mean, min/max with their years, latest value and linear trend per decade."""

    @extend_schema(parameters=[queries.SeriesQuery], responses=SummarySerializer)
    def get(self, request):
        return Response(queries.get_summary(request.query_params))


class ExtremesView(APIView):
    """The highest or lowest years of a series (what the chat uses for "wettest", "coldest")."""

    @extend_schema(parameters=[queries.ExtremeQuery], responses=ExtremeSerializer)
    def get(self, request):
        return Response(queries.get_extreme(request.query_params))


class CompareView(APIView):
    """Up to 4 regions' series aligned on one year axis."""

    @extend_schema(parameters=[queries.CompareQuery], responses=CompareSerializer)
    def get(self, request):
        return Response(queries.compare_regions(request.query_params))


class LatestIngestionRunView(APIView):
    """The most recent run that stored data (success or partial): when the data was refreshed."""

    @extend_schema(responses=IngestionRunSerializer)
    def get(self, request):
        run = (
            IngestionRun.objects.filter(
                status__in=[IngestionRun.Status.SUCCESS, IngestionRun.Status.PARTIAL]
            )
            .order_by("-started_at")
            .first()
        )
        if run is None:
            raise NotFound("No ingestion has completed yet.")
        return Response(IngestionRunSerializer(run).data)


class ChatView(APIView):
    """Ask a question in plain English. The answer comes only from tool calls over this database;
    the response lists those calls and the data they returned. The only write-method endpoint."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "chat"

    @extend_schema(
        request=ChatRequestSerializer,
        responses={
            200: ChatResponseSerializer,
            400: OpenApiResponse(description="empty or too long message, bad history"),
            429: OpenApiResponse(description="more than the per-IP rate limit"),
            503: OpenApiResponse(description="LLM provider not configured, busy or down"),
        },
    )
    def post(self, request):
        chat = ChatRequestSerializer(data=request.data)
        chat.is_valid(raise_exception=True)
        try:
            result = service.answer(
                chat.validated_data["message"],
                chat.validated_data.get("history", []),
                llm.default_client(),
            )
        except llm.LLMUnavailable as exc:
            return Response({"detail": str(exc)}, status=503)
        return Response(asdict(result))
