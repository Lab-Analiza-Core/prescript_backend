from unittest import mock

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient


class HealthEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient(HTTP_HOST="localhost")

    def test_health_is_public_and_checks_database_and_cache(self):
        response = self.client.get("/api/v1/health")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "ok")
        self.assertEqual(response.data["checks"], {"database": True, "cache": True})

    @mock.patch("api.views.health_views.cache.set", side_effect=OSError("cache caido"))
    def test_health_reports_service_unavailable_when_cache_fails(self, _cache_set):
        response = self.client.get("/api/v1/health")

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data["status"], "unhealthy")
        self.assertTrue(response.data["checks"]["database"])
        self.assertFalse(response.data["checks"]["cache"])
