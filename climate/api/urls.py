from django.urls import path

from . import views

app_name = "api"

urlpatterns = [
    path("regions/", views.RegionListView.as_view(), name="regions"),
    path("parameters/", views.ParameterListView.as_view(), name="parameters"),
    path("observations/", views.ObservationListView.as_view(), name="observations"),
    path("series/", views.SeriesView.as_view(), name="series"),
    path("series.csv", views.SeriesCsvView.as_view(), name="series-csv"),
    path("summary/", views.SummaryView.as_view(), name="summary"),
    path("extremes/", views.ExtremesView.as_view(), name="extremes"),
    path("compare/", views.CompareView.as_view(), name="compare"),
    path(
        "ingestion-runs/latest/",
        views.LatestIngestionRunView.as_view(),
        name="latest-ingestion-run",
    ),
]
