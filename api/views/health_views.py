from django.core.cache import cache
from django.db import connections
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        checks = {"database": False, "cache": False}
        try:
            with connections["default"].cursor() as cursor:
                cursor.execute("SELECT 1")
                checks["database"] = cursor.fetchone()[0] == 1
        except Exception:
            pass

        try:
            cache.set("prescript-health", "ok", timeout=10)
            checks["cache"] = cache.get("prescript-health") == "ok"
        except Exception:
            pass

        healthy = all(checks.values())
        return Response(
            {"status": "ok" if healthy else "unhealthy", "checks": checks},
            status=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        )
