from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APIClient

from api.models import (
    DoctorPortalProfile,
    NursePortalProfile,
    SecretaryPortalProfile,
)



class AuthenticationSmokeTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()

    def test_protected_detail_endpoints_require_authentication(self):
        protected_urls = [
            "/api/v1/doctor/me",
            "/api/v1/doctor/medicine-preferences/1",
            "/api/v1/patients/1",
            "/api/v1/appointments/1",
            "/api/v1/prescriptions/1",
        ]

        for url in protected_urls:
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)



class EmailLoginTests(TestCase):
    def setUp(self):
        self.client = APIClient(HTTP_HOST="localhost")
        self.user = get_user_model().objects.create_user(
            username="doctor-test",
            email="doctor@test.local",
            password="Doctor1234!",
        )

    def test_login_accepts_email_and_password(self):
        response = self.client.post(
            "/api/v1/auth/login",
            {"email": "doctor@test.local", "password": "Doctor1234!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_login_accepts_username_and_password(self):
        response = self.client.post(
            "/api/v1/auth/login",
            {"username": "doctor-test", "password": "Doctor1234!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)


class LegacyActivationClosedTests(TestCase):
    """La activacion por identificador se cerro: bastaba un dato casi publico para reclamar una ficha."""

    def setUp(self):
        self.client = APIClient(HTTP_HOST="localhost")

    def post(self, url, body):
        return self.client.post(url, body, format="json")

    @patch("api.services.interactive_core.InteractiveCoreDoctorService.lookup_doctor")
    @patch("api.services.interactive_core.InteractiveCoreAccessService.get_secretary")
    def test_every_legacy_endpoint_answers_gone_and_never_consults_interactive_core(self, get_secretary, lookup_doctor):
        valid_bodies = {
            "/api/v1/auth/doctor/activate": {
                "identifier": "MED-25",
                "password": "Doctor1234!",
                "password_confirm": "Doctor1234!",
            },
            "/api/v1/auth/access/activate": {
                "role": "SECRETARY",
                "identifier": "55",
                "password": "Doctor1234!",
                "password_confirm": "Doctor1234!",
            },
            "/api/v1/auth/access/validate": {"role": "SECRETARY", "identifier": "55"},
        }
        for url, body in valid_bodies.items():
            with self.subTest(url=url):
                response = self.post(url, body)
                self.assertEqual(response.status_code, status.HTTP_410_GONE)
                self.assertEqual(response.data["register_path"], "/registro/afiliado")
        lookup_doctor.assert_not_called()
        get_secretary.assert_not_called()

    def test_nothing_is_created_by_the_closed_endpoints(self):
        self.post(
            "/api/v1/auth/doctor/activate",
            {"identifier": "MED-25", "email": "nuevo@test.local", "password": "Doctor1234!", "password_confirm": "Doctor1234!"},
        )
        self.assertFalse(get_user_model().objects.filter(email="nuevo@test.local").exists())
        self.assertFalse(DoctorPortalProfile.objects.exists())
        self.assertFalse(SecretaryPortalProfile.objects.exists())
        self.assertFalse(NursePortalProfile.objects.exists())

    def test_closed_endpoints_reject_anonymous_get(self):
        for url in ("/api/v1/auth/doctor/activate", "/api/v1/auth/access/activate"):
            self.assertEqual(self.client.get(url).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
