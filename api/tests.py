from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APIClient

from api.models import Appointment, DoctorCredential, DoctorPortalProfile, Patient, PatientVitals
from api.roles import get_primary_prescript_role, normalize_prescript_roles


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


class PrescriptRoleTests(SimpleTestCase):
    def test_normalizes_spanish_and_legacy_roles_to_interactive_core_codes(self):
        roles = normalize_prescript_roles(["Gerente", "COUNTRY_MANAGER", "Secretaria", "Enfermera"])

        self.assertEqual(roles, ["COUNTRY_MANAGER", "SECRETARY", "NURSE"])
        self.assertEqual(get_primary_prescript_role(roles), "COUNTRY_MANAGER")


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
        self.assertTrue(DoctorCredential.objects.filter(email="doctor.mvp@test.local").exists())
        self.assertTrue(Group.objects.filter(name="DOCTOR", user__email="doctor.mvp@test.local").exists())

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


class PreclinicTests(TestCase):
    def setUp(self):
        self.client = APIClient(HTTP_HOST="localhost")
        self.user = get_user_model().objects.create_user(
            username="preclinic-doctor",
            email="preclinic@test.local",
            password="Doctor1234!",
        )
        Group.objects.get_or_create(name="DOCTOR")[0].user_set.add(self.user)
        self.doctor = DoctorPortalProfile.objects.create(
            user=self.user,
            interactive_core_doctor_id=200,
            full_name="Dra. Preclinica",
            specialties=[{"name": "Pediatria", "code": "PED"}],
            status="active",
        )
        self.patient = Patient.objects.create(
            doctor=self.doctor,
            first_name="Paciente",
            last_name="Control",
        )
        self.previous_appointment = Appointment.objects.create(
            doctor=self.doctor,
            patient=self.patient,
            scheduled_at=timezone.now() - timezone.timedelta(days=30),
        )
        PatientVitals.objects.create(
            patient=self.patient,
            appointment=self.previous_appointment,
            blood_pressure_systolic=110,
            blood_pressure_diastolic=70,
            oxygen_saturation="98.00",
            temperature="37.2",
            height_cm="120.00",
            weight_kg="22.50",
        )
        self.appointment = Appointment.objects.create(
            doctor=self.doctor,
            patient=self.patient,
            scheduled_at=timezone.now(),
        )
        self.client.force_authenticate(self.user)

    def test_preclinic_carries_persistent_values_only(self):
        response = self.client.get("/api/v1/preclinic/appointments")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        appointment = next(item for item in response.data if item["id"] == self.appointment.id)
        self.assertEqual(appointment["patient"], self.patient.id)
        self.assertEqual(appointment["patient_name"], self.patient.full_name)
        self.assertIsNone(appointment["current_vitals"])
        self.assertEqual(appointment["comparison_vitals"]["blood_pressure_systolic"], 110)
        self.assertEqual(str(appointment["comparison_vitals"]["height_cm"]), "120.00")
        self.assertEqual(str(appointment["comparison_vitals"]["weight_kg"]), "22.50")
        self.assertNotIn("temperature", appointment["comparison_vitals"])
        self.assertNotIn("oxygen_saturation", appointment["comparison_vitals"])

    def test_preclinic_saves_current_appointment_vitals(self):
        response = self.client.patch(
            f"/api/v1/preclinic/appointments/{self.appointment.id}/vitals",
            {
                "blood_pressure_systolic": 112,
                "blood_pressure_diastolic": 72,
                "oxygen_saturation": "97.50",
                "temperature": "36.8",
                "height_cm": "121.00",
                "weight_kg": "23.10",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        vitals = self.appointment.vitals
        self.assertEqual(vitals.blood_pressure_systolic, 112)
        self.assertEqual(str(vitals.oxygen_saturation), "97.50")
        self.assertEqual(str(vitals.height_cm), "121.00")

    def test_height_is_ignored_for_non_pediatric_specialty(self):
        self.doctor.specialties = [{"name": "Cardiologia", "code": "CAR"}]
        self.doctor.save(update_fields=["specialties"])

        response = self.client.patch(
            f"/api/v1/preclinic/appointments/{self.appointment.id}/vitals",
            {"height_cm": "130.00", "weight_kg": "24.00"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(self.appointment.vitals.height_cm)

    def test_patient_preclinic_vitals_are_upserted_by_selected_date(self):
        selected_date = (timezone.localdate() - timezone.timedelta(days=2)).isoformat()

        first_response = self.client.patch(
            f"/api/v1/preclinic/patients/{self.patient.id}/vitals?date={selected_date}",
            {"blood_pressure_systolic": 118, "blood_pressure_diastolic": 78, "weight_kg": "23.00"},
            format="json",
        )
        second_response = self.client.patch(
            f"/api/v1/preclinic/patients/{self.patient.id}/vitals?date={selected_date}",
            {"blood_pressure_systolic": 120, "blood_pressure_diastolic": 80, "weight_kg": "23.40"},
            format="json",
        )

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        daily_vitals = PatientVitals.objects.filter(
            patient=self.patient,
            appointment__isnull=True,
            recorded_at__date=selected_date,
        )
        self.assertEqual(daily_vitals.count(), 1)
        self.assertEqual(daily_vitals.get().blood_pressure_systolic, 120)
        self.assertEqual(str(second_response.data["current_vitals"]["weight_kg"]), "23.40")

    def test_patient_preclinic_vitals_reject_invalid_date(self):
        response = self.client.patch(
            f"/api/v1/preclinic/patients/{self.patient.id}/vitals?date=fecha-mala",
            {"blood_pressure_systolic": 118},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
