from decimal import Decimal

import factory

from climate.models import IngestionRun, Observation, Parameter, Region


class RegionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Region
        django_get_or_create = ("code",)

    code = "UK"
    name = factory.LazyAttribute(lambda o: o.code.replace("_", " "))
    slug = factory.LazyAttribute(lambda o: o.code.lower().replace("_", "-"))


class ParameterFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Parameter
        django_get_or_create = ("code",)

    code = "Tmax"
    name = "Max temperature"
    unit = "°C"


class IngestionRunFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = IngestionRun

    status = IngestionRun.Status.SUCCESS


class ObservationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Observation

    region = factory.SubFactory(RegionFactory)
    parameter = factory.SubFactory(ParameterFactory)
    year = 2000
    period = "ann"
    value = Decimal("10.00")
    source_url = factory.LazyAttribute(
        lambda o: (
            "https://www.metoffice.gov.uk/pub/data/weather/uk/climate/datasets/"
            f"{o.parameter.code}/date/{o.region.code}.txt"
        )
    )
    ingestion_run = factory.SubFactory(IngestionRunFactory)
