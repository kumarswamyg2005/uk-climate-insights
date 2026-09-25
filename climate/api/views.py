from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from climate import queries
from climate.models import IngestionRun, Observation

from .filters import ObservationFilter
from .serializers import (
    IngestionRunSerializer,
    ObservationSerializer,
    ParameterSerializer,
    RegionSerializer,
    SeriesSerializer,
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
