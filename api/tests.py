from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APIClient

from api.models import (
    Appointment,
    DoctorCredential,
    DoctorPortalProfile,
    NursePortalProfile,
    Patient,
    PatientVitals,
    SecretaryPortalProfile,
)
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


class DoctorProfileUpdateTests(TestCase):
    def setUp(self):
        self.client = APIClient(HTTP_HOST="localhost")
        self.user = get_user_model().objects.create_user(
            username="profile-doctor@test.local",
            email="profile-doctor@test.local",
            password="Doctor1234!",
        )
        Group.objects.get_or_create(name="DOCTOR")[0].user_set.add(self.user)
        self.doctor = DoctorPortalProfile.objects.create(
            user=self.user,
            interactive_core_doctor_id=901,
            full_name="Doctora Perfil",
            specialties=[{"id": 1, "name": "Cardiologia", "code": "CAR"}],
            status="active",
        )
        self.client.force_authenticate(self.user)

    def test_specialties_are_read_only_from_doctor_profile_patch(self):
        response = self.client.patch(
            "/api/v1/doctor/me",
            {
                "phone": "88881111",
                "specialties": [{"id": 9, "name": "Dermatologia", "code": "DER"}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.doctor.refresh_from_db()
        self.assertEqual(self.doctor.phone, "88881111")
        self.assertEqual(self.doctor.specialties, [{"id": 1, "name": "Cardiologia", "code": "CAR"}])


class PortalAccessActivationTests(TestCase):
    def setUp(self):
        self.client = APIClient(HTTP_HOST="localhost")

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


class UserProfileUpdateTests(TestCase):
    def setUp(self):
        self.client = APIClient(HTTP_HOST="localhost")
        self.user = get_user_model().objects.create_user(
            username="nurse@test.local",
            email="nurse@test.local",
            password="Doctor1234!",
        )
        Group.objects.get_or_create(name="NURSE")[0].user_set.add(self.user)
        self.profile = NursePortalProfile.objects.create(
            user=self.user,
            interactive_core_user_id=700,
            interactive_core_employee_id=1700,
            full_name="Enfermera Perfil",
            email="nurse@test.local",
            phone="99991111",
            country="HN",
        )
        self.client.force_authenticate(self.user)

    def test_user_can_update_email_and_phone_from_auth_me(self):
        response = self.client.patch(
            "/api/v1/auth/me",
            {
                "email": "nurse.updated@test.local",
                "phone": "88882222",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertEqual(self.user.email, "nurse.updated@test.local")
        self.assertEqual(self.user.username, "nurse.updated@test.local")
        self.assertEqual(self.profile.email, "nurse.updated@test.local")
        self.assertEqual(self.profile.phone, "88882222")
        self.assertEqual(response.data["email"], "nurse.updated@test.local")

    def test_user_can_change_password_with_current_password(self):
        response = self.client.patch(
            "/api/v1/auth/me",
            {
                "current_password": "Doctor1234!",
                "new_password": "Nuevo1234!",
                "password_confirm": "Nuevo1234!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Nuevo1234!"))

    def test_user_cannot_change_password_with_wrong_current_password(self):
        response = self.client.patch(
            "/api/v1/auth/me",
            {
                "current_password": "Incorrecta123!",
                "new_password": "Nuevo1234!",
                "password_confirm": "Nuevo1234!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Doctor1234!"))


class AppointmentSchedulingTests(TestCase):
    def setUp(self):
        self.client = APIClient(HTTP_HOST="localhost")
        self.doctor_user = get_user_model().objects.create_user(
            username="agenda-doctor",
            email="agenda.doctor@test.local",
            password="Doctor1234!",
        )
        Group.objects.get_or_create(name="DOCTOR")[0].user_set.add(self.doctor_user)
        self.doctor = DoctorPortalProfile.objects.create(
            user=self.doctor_user,
            interactive_core_doctor_id=300,
            full_name="Dra. Agenda",
            status="active",
        )
        self.patient = Patient.objects.create(
            doctor=self.doctor,
            first_name="Paciente",
            last_name="Con Preclinica",
        )
        PatientVitals.objects.create(patient=self.patient, weight_kg="70.00")
        self.scheduled_at = timezone.now() + timezone.timedelta(days=1)

        self.secretary_user = get_user_model().objects.create_user(
            username="agenda-secretary",
            email="agenda.secretary@test.local",
            password="Doctor1234!",
        )
        Group.objects.get_or_create(name="SECRETARY")[0].user_set.add(self.secretary_user)
        self.secretary_profile = SecretaryPortalProfile.objects.create(
            user=self.secretary_user,
            secretaria_interactivecore_id=700,
            full_name="Secretaria Agenda",
            email="agenda.secretary@test.local",
            status="active",
        )

        self.nurse_user = get_user_model().objects.create_user(
            username="agenda-nurse",
            email="agenda.nurse@test.local",
            password="Doctor1234!",
        )
        Group.objects.get_or_create(name="NURSE")[0].user_set.add(self.nurse_user)

    def test_doctor_can_schedule_after_preclinic(self):
        self.client.force_authenticate(self.doctor_user)

        response = self.client.post(
            "/api/v1/appointments",
            {
                "patient": self.patient.id,
                "scheduled_at": self.scheduled_at.isoformat(),
                "duration_minutes": 30,
                "reason": "Seguimiento",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["doctor"], self.doctor.id)
        self.assertEqual(response.data["patient"], self.patient.id)

    @patch("api.services.secretary_access.InteractiveCoreSecretaryService.get_assigned_doctor_ids")
    def test_secretary_can_schedule_after_preclinic(self, get_assigned_doctor_ids):
        get_assigned_doctor_ids.return_value = [self.doctor.interactive_core_doctor_id]
        self.client.force_authenticate(self.secretary_user)

        response = self.client.post(
            "/api/v1/appointments",
            {
                "doctor": self.doctor.id,
                "patient": self.patient.id,
                "scheduled_at": self.scheduled_at.isoformat(),
                "duration_minutes": 45,
                "reason": "Consulta",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["doctor"], self.doctor.id)

    def test_cannot_schedule_overlapping_doctor_appointment(self):
        Appointment.objects.create(
            doctor=self.doctor,
            patient=self.patient,
            scheduled_at=self.scheduled_at,
            duration_minutes=30,
            status="scheduled",
        )
        self.client.force_authenticate(self.doctor_user)

        response = self.client.post(
            "/api/v1/appointments",
            {
                "patient": self.patient.id,
                "scheduled_at": (self.scheduled_at + timezone.timedelta(minutes=15)).isoformat(),
                "duration_minutes": 30,
                "reason": "Seguimiento",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Ese horario ya esta ocupado para este doctor", str(response.data))

    def test_different_doctors_can_schedule_same_time(self):
        other_user = get_user_model().objects.create_user(
            username="agenda-other-doctor",
            email="agenda.other.doctor@test.local",
            password="Doctor1234!",
        )
        other_doctor = DoctorPortalProfile.objects.create(
            user=other_user,
            interactive_core_doctor_id=301,
            full_name="Dr. Otra Agenda",
            status="active",
        )
        other_patient = Patient.objects.create(
            doctor=other_doctor,
            first_name="Paciente",
            last_name="Otro Doctor",
        )
        PatientVitals.objects.create(patient=other_patient, weight_kg="72.00")
        Appointment.objects.create(
            doctor=other_doctor,
            patient=other_patient,
            scheduled_at=self.scheduled_at,
            duration_minutes=30,
            status="scheduled",
        )
        self.client.force_authenticate(self.doctor_user)

        response = self.client.post(
            "/api/v1/appointments",
            {
                "patient": self.patient.id,
                "scheduled_at": self.scheduled_at.isoformat(),
                "duration_minutes": 30,
                "reason": "Seguimiento",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["doctor"], self.doctor.id)

    def test_can_schedule_when_previous_doctor_appointment_has_ended(self):
        Appointment.objects.create(
            doctor=self.doctor,
            patient=self.patient,
            scheduled_at=self.scheduled_at,
            duration_minutes=30,
            status="scheduled",
        )
        self.client.force_authenticate(self.doctor_user)

        response = self.client.post(
            "/api/v1/appointments",
            {
                "patient": self.patient.id,
                "scheduled_at": (self.scheduled_at + timezone.timedelta(minutes=30)).isoformat(),
                "duration_minutes": 30,
                "reason": "Seguimiento",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_schedule_requires_previous_preclinic(self):
        patient_without_preclinic = Patient.objects.create(
            doctor=self.doctor,
            first_name="Paciente",
            last_name="Sin Preclinica",
        )
        self.client.force_authenticate(self.doctor_user)

        response = self.client.post(
            "/api/v1/appointments",
            {
                "patient": patient_without_preclinic.id,
                "scheduled_at": self.scheduled_at.isoformat(),
                "reason": "Seguimiento",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Appointment.objects.filter(patient=patient_without_preclinic).exists())

    def test_cannot_schedule_appointment_in_the_past(self):
        self.client.force_authenticate(self.doctor_user)
        past_date = timezone.now() - timezone.timedelta(hours=1)

        response = self.client.post(
            "/api/v1/appointments",
            {
                "patient": self.patient.id,
                "scheduled_at": past_date.isoformat(),
                "reason": "Seguimiento",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Appointment.objects.filter(scheduled_at=past_date).exists())

    def test_nurse_cannot_schedule_appointment(self):
        self.client.force_authenticate(self.nurse_user)

        response = self.client.post(
            "/api/v1/appointments",
            {
                "doctor": self.doctor.id,
                "patient": self.patient.id,
                "scheduled_at": self.scheduled_at.isoformat(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("api.services.secretary_access.InteractiveCoreSecretaryService.get_assigned_doctor_ids")
    def test_secretary_can_reschedule_existing_appointment(self, get_assigned_doctor_ids):
        get_assigned_doctor_ids.return_value = [self.doctor.interactive_core_doctor_id]
        appointment = Appointment.objects.create(
            doctor=self.doctor,
            patient=self.patient,
            scheduled_at=self.scheduled_at,
        )
        new_date = self.scheduled_at + timezone.timedelta(days=2)
        self.client.force_authenticate(self.secretary_user)

        response = self.client.patch(
            f"/api/v1/appointments/{appointment.id}",
            {"scheduled_at": new_date.isoformat(), "status": "rescheduled"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "rescheduled")

    @patch("api.services.secretary_access.InteractiveCoreSecretaryService.get_assigned_doctor_ids")
    def test_secretary_cannot_reschedule_to_the_past(self, get_assigned_doctor_ids):
        get_assigned_doctor_ids.return_value = [self.doctor.interactive_core_doctor_id]
        appointment = Appointment.objects.create(
            doctor=self.doctor,
            patient=self.patient,
            scheduled_at=self.scheduled_at,
        )
        past_date = timezone.now() - timezone.timedelta(hours=1)
        self.client.force_authenticate(self.secretary_user)

        response = self.client.patch(
            f"/api/v1/appointments/{appointment.id}",
            {"scheduled_at": past_date.isoformat(), "status": "rescheduled"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        appointment.refresh_from_db()
        self.assertEqual(appointment.scheduled_at, self.scheduled_at)

    @patch("api.services.secretary_access.InteractiveCoreSecretaryService.get_assigned_doctor_ids")
    def test_secretary_cannot_reschedule_overlapping_doctor_appointment(self, get_assigned_doctor_ids):
        get_assigned_doctor_ids.return_value = [self.doctor.interactive_core_doctor_id]
        appointment = Appointment.objects.create(
            doctor=self.doctor,
            patient=self.patient,
            scheduled_at=self.scheduled_at,
        )
        Appointment.objects.create(
            doctor=self.doctor,
            patient=self.patient,
            scheduled_at=self.scheduled_at + timezone.timedelta(days=2),
            duration_minutes=30,
            status="scheduled",
        )
        self.client.force_authenticate(self.secretary_user)

        response = self.client.patch(
            f"/api/v1/appointments/{appointment.id}",
            {
                "scheduled_at": (self.scheduled_at + timezone.timedelta(days=2, minutes=10)).isoformat(),
                "status": "rescheduled",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Ese horario ya esta ocupado para este doctor", str(response.data))

    @patch("api.services.secretary_access.InteractiveCoreSecretaryService.get_assigned_doctor_ids")
    def test_secretary_cannot_schedule_for_unlinked_doctor(self, get_assigned_doctor_ids):
        get_assigned_doctor_ids.return_value = []
        self.client.force_authenticate(self.secretary_user)

        response = self.client.post(
            "/api/v1/appointments",
            {
                "doctor": self.doctor.id,
                "patient": self.patient.id,
                "scheduled_at": self.scheduled_at.isoformat(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Appointment.objects.filter(patient=self.patient).exists())


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

    def test_preclinic_rejects_future_appointment_vitals(self):
        future_appointment = Appointment.objects.create(
            doctor=self.doctor,
            patient=self.patient,
            scheduled_at=timezone.now() + timezone.timedelta(days=1),
        )

        response = self.client.patch(
            f"/api/v1/preclinic/appointments/{future_appointment.id}/vitals",
            {"blood_pressure_systolic": 112},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(PatientVitals.objects.filter(appointment=future_appointment).exists())

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

    def test_patient_preclinic_vitals_reject_future_date(self):
        future_date = (timezone.localdate() + timezone.timedelta(days=1)).isoformat()

        response = self.client.patch(
            f"/api/v1/preclinic/patients/{self.patient.id}/vitals?date={future_date}",
            {"blood_pressure_systolic": 118},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            PatientVitals.objects.filter(
                patient=self.patient,
                appointment__isnull=True,
                recorded_at__date=future_date,
            ).exists()
        )
