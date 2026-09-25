import argparse

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Max, Min

from climate.catalog import PARAMETER_CODES, REGION_CODES
from climate.ingest import run_ingest
from climate.models import IngestionRun, Observation


def code_list(valid: tuple[str, ...]):
    """argparse type: comma-separated codes, each checked against the catalog."""

    def parse(value: str) -> list[str]:
        codes = [c.strip() for c in value.split(",") if c.strip()]
        unknown = sorted(set(codes) - set(valid))
        if unknown or not codes:
            raise argparse.ArgumentTypeError(
                f"unknown code(s) {', '.join(unknown) or '(none given)'}; valid: {', '.join(valid)}"
            )
        return codes

    return parse


class Command(BaseCommand):
    help = "Download the Met Office UK and regional series and upsert them into the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--regions", type=code_list(REGION_CODES), help="comma-separated (default: all 17)"
        )
        parser.add_argument(
            "--parameters", type=code_list(PARAMETER_CODES), help="comma-separated (default: all 7)"
        )
        parser.add_argument(
            "--delay", type=float, help="seconds between requests (default: settings)"
        )
        parser.add_argument(
            "--if-needed",
            action="store_true",
            help="do nothing once an ingest has completed (container boot). A run that was "
            "interrupted or failed doesn't count, so the next boot tries again.",
        )

    def handle(self, *args, regions=None, parameters=None, delay=None, if_needed=False, **options):
        completed = IngestionRun.objects.filter(
            status__in=[IngestionRun.Status.SUCCESS, IngestionRun.Status.PARTIAL]
        )
        if if_needed and completed.exists():
            self.stdout.write("An ingest has already completed; skipping.")
            return
        run = run_ingest(regions, parameters, delay=delay)
        seconds = (run.finished_at - run.started_at).total_seconds()

        self.stdout.write(f"Ingestion run #{run.pk}: {run.status}")
        self.stdout.write(
            f"Files {run.files_succeeded}/{run.files_attempted} succeeded, "
            f"{run.rows_upserted:,} rows upserted in {seconds:.1f}s"
        )
        if run.source_updated_at:
            self.stdout.write(
                f"Met Office data last updated {run.source_updated_at:%Y-%m-%d %H:%M}"
            )
        for error in run.errors:
            self.stderr.write(f"  FAILED {error['url']}\n         {error['error']}")

        self.stdout.write(f"\n{'Parameter':<12} {'Rows in DB':>11}  Years")
        totals = (
            Observation.objects.values("parameter__code")
            .annotate(rows=Count("id"), first=Min("year"), last=Max("year"))
            .order_by("parameter_id")
        )
        for row in totals:
            self.stdout.write(
                f"{row['parameter__code']:<12} {row['rows']:>11,}  {row['first']}-{row['last']}"
            )
        self.stdout.write(f"{'Total':<12} {sum(r['rows'] for r in totals):>11,}")

        if run.status == IngestionRun.Status.FAILED:
            raise CommandError("every file failed; see errors above")
