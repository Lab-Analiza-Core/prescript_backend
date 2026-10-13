from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import SimpleTestCase, TestCase
from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APIClient

from api.models import (
    DoctorCredential,
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



class DoctorActivationTests(TestCase):
    def setUp(self):
        self.client = APIClient(HTTP_HOST="localhost")
        self.doctor_payload = {
            "id": 25,
            "full_name": "Dra. Prueba Prescript",
            "sex": "F",
            "email": "doctor.mvp@test.local",
            "phone": "99990000",
            "colegiation_code": "MED-25",
            "qualification_code": "Top",
            "final_score": "91.50",
            "status": "active",
            "is_top_doctor": True,
            "roles": ["DOCTOR"],
            "has_doctor_role": True,
            "specialties": [{"id": 1, "name": "Cardiologia", "code": "CAR-001"}],
            "clinics": [{"id": 8, "name": "Hospital del Valle"}],
        }

    @patch("api.serializers.auth_serializers.InteractiveCoreDoctorService.lookup_doctor")
    def test_top_doctor_can_activate_credentials(self, lookup_doctor):
        lookup_doctor.return_value = self.doctor_payload

        response = self.client.post(
            "/api/v1/auth/doctor/activate",
            {
                "identifier": "MED-25",
                "password": "Doctor1234!",
                "password_confirm": "Doctor1234!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("access", response.data)
        self.assertEqual(response.data["roles"], ["DOCTOR"])
        self.assertTrue(DoctorPortalProfile.objects.filter(interactive_core_doctor_id=25).exists())
        profile = DoctorPortalProfile.objects.get(interactive_core_doctor_id=25)
        self.assertEqual(profile.sex, "F")
        self.assertEqual(profile.clinics, [{"id": 8, "name": "Hospital del Valle"}])
        self.assertTrue(DoctorCredential.objects.filter(email="doctor.mvp@test.local").exists())
        self.assertTrue(Group.objects.filter(name="DOCTOR", user__email="doctor.mvp@test.local").exists())

    def test_auth_me_uses_gendered_doctor_display_name(self):
        user = get_user_model().objects.create_user(
            username="ada@test.local",
            email="ada@test.local",
            password="Doctor1234!",
        )
        Group.objects.get_or_create(name="DOCTOR")[0].user_set.add(user)
        DoctorPortalProfile.objects.create(
            user=user,
            interactive_core_doctor_id=301,
            full_name="Ada Cordoba",
            sex="F",
            clinics=[{"id": 8, "name": "Hospital del Valle"}],
            status="active",
        )
        self.client.force_authenticate(user)

        response = self.client.get("/api/v1/auth/me")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["display_name"], "Dra. Ada Cordoba")
        self.assertEqual(response.data["doctor_profile"]["display_name"], "Dra. Ada Cordoba")
        self.assertEqual(
            response.data["doctor_profile"]["clinics"],
            [{"id": 8, "name": "Hospital del Valle"}],
        )

    def test_auth_me_uses_masculine_doctor_display_name(self):
        user = get_user_model().objects.create_user(
            username="david@test.local",
            email="david@test.local",
            password="Doctor1234!",
        )
        Group.objects.get_or_create(name="DOCTOR")[0].user_set.add(user)
        DoctorPortalProfile.objects.create(
            user=user,
            interactive_core_doctor_id=302,
            full_name="David Suazo",
            sex="M",
            status="active",
        )
        self.client.force_authenticate(user)

        response = self.client.get("/api/v1/auth/me")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["display_name"], "Dr. David Suazo")

    @patch("api.serializers.auth_serializers.InteractiveCoreDoctorService.lookup_doctor")
    def test_active_doctor_can_activate_without_score_requirement(self, lookup_doctor):
        lookup_doctor.return_value = {
            **self.doctor_payload,
            "id": 26,
            "email": "doctor.no.top@test.local",
            "is_top_doctor": False,
        }

        response = self.client.post(
            "/api/v1/auth/doctor/activate",
            {
                "identifier": "MED-26",
                "password": "Doctor1234!",
                "password_confirm": "Doctor1234!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(DoctorPortalProfile.objects.filter(interactive_core_doctor_id=26).exists())

    @patch("api.serializers.auth_serializers.InteractiveCoreDoctorService.lookup_doctor")
    def test_doctor_without_interactive_core_doctor_role_cannot_activate(self, lookup_doctor):
        lookup_doctor.return_value = {
            **self.doctor_payload,
            "id": 27,
            "email": "doctor.no.role@test.local",
            "roles": ["visita medica"],
            "has_doctor_role": False,
        }

        response = self.client.post(
            "/api/v1/auth/doctor/activate",
            {
                "identifier": "MED-27",
                "password": "Doctor1234!",
                "password_confirm": "Doctor1234!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(DoctorPortalProfile.objects.filter(interactive_core_doctor_id=27).exists())



class PortalAccessActivationTests(TestCase):
    def setUp(self):
        self.client = APIClient(HTTP_HOST="localhost")

    @patch("api.serializers.auth_serializers.InteractiveCoreAccessService.lookup")
    def test_validates_secretary_identifier_before_activation(self, lookup):
        lookup.return_value = {
            "id": 55,
            "full_name": "Secretaria Prescript",
            "email": "secretaria@test.local",
            "phone": "99990000",
            "country": "HN",
        }

        response = self.client.post(
            "/api/v1/auth/access/validate",
            {
                "role": "SECRETARY",
                "identifier": "55",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"valid": True})
        self.assertFalse(SecretaryPortalProfile.objects.filter(secretaria_interactivecore_id=55).exists())

    @patch("api.serializers.auth_serializers.InteractiveCoreAccessService.lookup")
    def test_validates_nurse_identifier_before_activation(self, lookup):
        lookup.return_value = {
            "interactive_core_user_id": 70,
            "interactive_core_employee_id": 170,
            "full_name": "Enfermera Prescript",
            "email": "nurse@test.local",
            "phone": "99991111",
            "country": "HN",
        }

        response = self.client.post(
            "/api/v1/auth/access/validate",
            {
                "role": "NURSE",
                "identifier": "nurse@test.local",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"valid": True})
        self.assertFalse(NursePortalProfile.objects.filter(interactive_core_user_id=70).exists())

    @patch("api.serializers.auth_serializers.InteractiveCoreAccessService.lookup")
    def test_rejects_invalid_nurse_identifier_before_next_step(self, lookup):
        lookup.return_value = None

        response = self.client.post(
            "/api/v1/auth/access/validate",
            {
                "role": "NURSE",
                "identifier": "sin-registro@test.local",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("identifier", response.data)

    @patch("api.serializers.auth_serializers.InteractiveCoreAccessService.lookup")
    def test_rejects_invalid_secretary_identifier_before_next_step(self, lookup):
        lookup.return_value = None

        response = self.client.post(
            "/api/v1/auth/access/validate",
            {
                "role": "SECRETARY",
                "identifier": "secretaria-invalida@test.local",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("identifier", response.data)

    @patch("api.serializers.auth_serializers.InteractiveCoreAccessService.lookup")
    def test_can_activate_secretary_access(self, lookup):
        lookup.return_value = {
            "id": 55,
            "full_name": "Secretaria Prescript",
            "email": "secretaria@test.local",
            "phone": "99990000",
            "country": "HN",
        }

        response = self.client.post(
            "/api/v1/auth/access/activate",
            {
                "role": "SECRETARY",
                "identifier": "55",
                "password": "Doctor1234!",
                "password_confirm": "Doctor1234!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("access", response.data)
        self.assertTrue(SecretaryPortalProfile.objects.filter(secretaria_interactivecore_id=55).exists())
        self.assertTrue(Group.objects.filter(name="SECRETARY", user__email="secretaria@test.local").exists())

    @patch("api.serializers.auth_serializers.InteractiveCoreAccessService.lookup")
    def test_can_activate_nurse_access(self, lookup):
        lookup.return_value = {
            "interactive_core_user_id": 70,
            "interactive_core_employee_id": 170,
            "full_name": "Enfermera Prescript",
            "email": "nurse@test.local",
            "phone": "99991111",
            "country": "HN",
        }

        response = self.client.post(
            "/api/v1/auth/access/activate",
            {
                "role": "NURSE",
                "identifier": "nurse@test.local",
                "password": "Doctor1234!",
                "password_confirm": "Doctor1234!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("access", response.data)
        self.assertTrue(NursePortalProfile.objects.filter(interactive_core_user_id=70).exists())
        self.assertTrue(Group.objects.filter(name="NURSE", user__email="nurse@test.local").exists())

    @patch("api.serializers.auth_serializers.InteractiveCoreAccessService.lookup")
    def test_rejects_access_when_role_record_is_missing(self, lookup):
        lookup.return_value = None

        response = self.client.post(
            "/api/v1/auth/access/activate",
            {
                "role": "NURSE",
                "identifier": "sin-registro@test.local",
                "password": "Doctor1234!",
                "password_confirm": "Doctor1234!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)



