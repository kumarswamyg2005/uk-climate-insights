from django.db import DatabaseError, connection
from django.http import JsonResponse


def healthz(request):
    """Liveness plus a real round-trip to the database, so a broken DB fails the healthcheck."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        return JsonResponse({"status": "error", "db": "unreachable"}, status=503)
    return JsonResponse({"status": "ok", "db": "ok"})
