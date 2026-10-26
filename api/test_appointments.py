from django.test import TestCase
from django.utils import timezone
from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APIClient

from api.models import Appointment
from api.test_factories import (
    create_appointment,
    create_doctor,
    create_patient,
    create_secretary,
    create_user,
    create_vitals,
)



class AppointmentSchedulingTests(TestCase):
    def setUp(self):
        self.client = APIClient(HTTP_HOST="localhost")
        self.doctor_user = create_user(
            username="agenda-doctor",
            email="agenda.doctor@test.local",
            password="Doctor1234!",
            roles=["DOCTOR"],
        )
        self.doctor = create_doctor(
            user=self.doctor_user,
            interactive_core_doctor_id=300,
            full_name="Dra. Agenda",
            status="active",
        )
        self.patient = create_patient(
            doctor=self.doctor,
            first_name="Paciente",
            last_name="Con Preclinica",
        )
        create_vitals(patient=self.patient, weight_kg="70.00")
        self.scheduled_at = timezone.now() + timezone.timedelta(days=1)

        self.secretary_user = create_user(
            username="agenda-secretary",
            email="agenda.secretary@test.local",
            password="Doctor1234!",
            roles=["SECRETARY"],
        )
        self.secretary_profile = create_secretary(
            user=self.secretary_user,
            secretaria_interactivecore_id=700,
            full_name="Secretaria Agenda",
            email="agenda.secretary@test.local",
            status="active",
        )

        self.nurse_user = create_user(
            username="agenda-nurse",
            email="agenda.nurse@test.local",
            password="Doctor1234!",
            roles=["NURSE"],
        )

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

    def test_doctor_profile_without_group_can_create_patient(self):
        profile_only_user = create_user(
            username="profile-only-doctor@test.local",
            email="profile-only-doctor@test.local",
            password="Doctor1234!",
        )
        doctor = create_doctor(
            user=profile_only_user,
            interactive_core_doctor_id=399,
            full_name="Dr. Perfil Sin Grupo",
            status="active",
        )
        self.client.force_authenticate(profile_only_user)

        response = self.client.post(
            "/api/v1/patients",
            {
                "first_name": "Paciente",
                "last_name": "Sin Grupo",
                "dni": "0801199012345",
                "phone": "88881234",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["doctor"], doctor.id)

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
        create_appointment(
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

    def test_cannot_schedule_overlap_across_midnight(self):
        next_midnight = (timezone.localtime(timezone.now()) + timezone.timedelta(days=2)).replace(
            hour=0,
            minute=10,
            second=0,
            microsecond=0,
        )
        create_appointment(
            doctor=self.doctor,
            patient=self.patient,
            scheduled_at=next_midnight - timezone.timedelta(minutes=20),
            duration_minutes=40,
        )
        self.client.force_authenticate(self.doctor_user)

        response = self.client.post(
            "/api/v1/appointments",
            {
                "patient": self.patient.id,
                "scheduled_at": next_midnight.isoformat(),
                "duration_minutes": 30,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("scheduled_at", response.data)

    def test_cannot_extend_appointment_into_another_slot(self):
        appointment = create_appointment(
            doctor=self.doctor,
            patient=self.patient,
            scheduled_at=self.scheduled_at,
            duration_minutes=30,
        )
        create_appointment(
            doctor=self.doctor,
            patient=self.patient,
            scheduled_at=self.scheduled_at + timezone.timedelta(minutes=45),
            duration_minutes=30,
        )
        self.client.force_authenticate(self.doctor_user)

        response = self.client.patch(
            f"/api/v1/appointments/{appointment.id}",
            {"duration_minutes": 60},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("scheduled_at", response.data)

    def test_different_doctors_can_schedule_same_time(self):
        other_user = create_user(
            username="agenda-other-doctor",
            email="agenda.other.doctor@test.local",
            password="Doctor1234!",
        )
        other_doctor = create_doctor(
            user=other_user,
            interactive_core_doctor_id=301,
            full_name="Dr. Otra Agenda",
            status="active",
        )
        other_patient = create_patient(
            doctor=other_doctor,
            first_name="Paciente",
            last_name="Otro Doctor",
        )
        create_vitals(patient=other_patient, weight_kg="72.00")
        create_appointment(
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
        create_appointment(
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
        patient_without_preclinic = create_patient(
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

    def test_appointment_duration_must_be_positive(self):
        self.client.force_authenticate(self.doctor_user)

        response = self.client.post(
            "/api/v1/appointments",
            {
                "patient": self.patient.id,
                "scheduled_at": self.scheduled_at.isoformat(),
                "duration_minutes": 0,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("duration_minutes", response.data)

    def test_vitals_cannot_link_patient_to_another_doctors_appointment(self):
        other_user = create_user("vitals-other-doctor@test.local", roles=["DOCTOR"])
        other_doctor = create_doctor(user=other_user, interactive_core_doctor_id=987)
        other_patient = create_patient(other_doctor, first_name="Otro", last_name="Paciente")
        other_appointment = create_appointment(other_doctor, other_patient, self.scheduled_at)
        self.client.force_authenticate(self.doctor_user)

        response = self.client.post(
            "/api/v1/patients/vitals",
            {
                "patient": self.patient.id,
                "appointment": other_appointment.id,
                "weight_kg": "70.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("appointment", response.data)

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

    def test_admin_can_create_patient_for_selected_doctor(self):
        admin_user = create_user(
            username="patient-admin@test.local",
            email="patient-admin@test.local",
            password="Admin1234!",
            roles=["ADMIN"],
        )
        self.client.force_authenticate(admin_user)

        response = self.client.post(
            "/api/v1/patients",
            {
                "doctor": self.doctor.id,
                "first_name": "Byron",
                "last_name": "Garcia",
                "dni": "1223434343434",
                "phone": "43554675",
                "email": "byronavila@paciente.prescript.com",
                "birth_date": "2020-08-07",
                "sex": "F",
                "commercial_notes": "Un paciente interesante",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["doctor"], self.doctor.id)
        self.assertEqual(response.data["dni"], "1223-4343-43434")
        self.assertEqual(response.data["phone"], "4355-4675")

    def test_patient_requires_dni_and_phone_in_honduras(self):
        self.client.force_authenticate(self.doctor_user)

        for field in ("dni", "phone"):
            with self.subTest(missing=field):
                payload = {"first_name": "Paciente", "last_name": "Incompleto", "dni": "0801199012345", "phone": "88881234"}
                payload.pop(field)
                response = self.client.post("/api/v1/patients", payload, format="json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(field, response.data)

    def test_patient_requires_dni_or_phone_in_guatemala(self):
        gt_user = create_user(
            username="doctor-gt-patient@test.local",
            email="doctor-gt-patient@test.local",
            password="Doctor1234!",
            roles=["DOCTOR"],
        )
        create_doctor(user=gt_user, interactive_core_doctor_id=498, country="GT")
        self.client.force_authenticate(gt_user)

        empty = self.client.post("/api/v1/patients", {"first_name": "Ana", "last_name": "Gt"}, format="json")
        with_phone = self.client.post(
            "/api/v1/patients", {"first_name": "Ana", "last_name": "Gt", "phone": "31423325"}, format="json"
        )

        self.assertEqual(empty.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("phone", empty.data)
        self.assertEqual(with_phone.status_code, status.HTTP_201_CREATED)

    def test_patient_without_dni_requires_confirmation_for_same_name(self):
        gt_user = create_user(
            username="doctor-gt-duplicate@test.local",
            email="doctor-gt-duplicate@test.local",
            password="Doctor1234!",
            roles=["DOCTOR"],
        )
        create_doctor(user=gt_user, interactive_core_doctor_id=499, country="GT")
        self.client.force_authenticate(gt_user)
        first_payload = {
            "first_name": "Ana",
            "last_name": "Lopez",
            "phone": "31423325",
        }
        duplicate_payload = {
            "first_name": "Ana",
            "last_name": "Lopez",
            "phone": "31423326",
        }

        first = self.client.post("/api/v1/patients", first_payload, format="json")
        duplicate = self.client.post("/api/v1/patients", duplicate_payload, format="json")
        confirmed = self.client.post(
            "/api/v1/patients",
            {**duplicate_payload, "confirm_duplicate": True},
            format="json",
        )

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("confirm_duplicate", duplicate.data)
        self.assertEqual(confirmed.status_code, status.HTTP_201_CREATED)

    def test_patient_list_paginates_by_ten_on_request(self):
        self.client.force_authenticate(self.doctor_user)
        for index in range(11):
            create_patient(self.doctor, first_name=f"Pac{index:02d}", last_name="Paginado")

        full = self.client.get("/api/v1/patients")
        page = self.client.get("/api/v1/patients?page=1")
        last = self.client.get("/api/v1/patients?page=2&search=Paginado")

        self.assertIsInstance(full.data, list)
        self.assertEqual(page.data["count"], len(full.data))
        self.assertEqual(len(page.data["results"]), 10)
        self.assertEqual(last.data["count"], 11)
        self.assertEqual(len(last.data["results"]), 1)

    def test_patient_list_filters(self):
        self.client.force_authenticate(self.doctor_user)
        ana = create_patient(self.doctor, first_name="Ana", last_name="Lopez", sex="F")
        luis = create_patient(self.doctor, first_name="Luis", last_name="Mejia", sex="M")
        inactive = create_patient(self.doctor, first_name="Zoe", last_name="Baja", sex="F", is_active=False)

        def ids(query):
            response = self.client.get(f"/api/v1/patients{query}")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            return {item["id"] for item in response.data}

        self.assertTrue({ana.id, luis.id} <= ids(""))
        self.assertNotIn(inactive.id, ids(""))
        self.assertEqual(ids("?search=mejia") & {ana.id, luis.id}, {luis.id})
        self.assertEqual(ids("?sex=F") & {ana.id, luis.id}, {ana.id})
        self.assertEqual(ids("?is_active=false"), {inactive.id})
        self.assertIn(inactive.id, ids("?is_active=all"))
        self.assertEqual(ids(f"?doctor={self.doctor.id + 999}"), set())
        self.assertEqual(ids("?created_from=2999-01-01"), set())

    def test_patient_dni_and_phone_must_match_country_masks(self):
        self.client.force_authenticate(self.doctor_user)

        response = self.client.post(
            "/api/v1/patients",
            {
                "first_name": "Paciente",
                "last_name": "Invalido",
                "dni": "12345",
                "phone": "999",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("dni", response.data)

    def test_admin_can_list_doctors_for_patient_assignment(self):
        admin_user = create_user(
            username="doctor-list-admin@test.local",
            email="doctor-list-admin@test.local",
            password="Admin1234!",
            roles=["ADMIN"],
        )
        self.client.force_authenticate(admin_user)

        response = self.client.get("/api/v1/doctors")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(any(doctor["id"] == self.doctor.id for doctor in response.data))

    @patch("api.services.secretary_access.InteractiveCoreSecretaryService.get_assigned_doctor_ids")
    def test_secretary_can_reschedule_existing_appointment(self, get_assigned_doctor_ids):
        get_assigned_doctor_ids.return_value = [self.doctor.interactive_core_doctor_id]
        appointment = create_appointment(
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

    def test_doctor_can_cancel_existing_appointment(self):
        appointment = create_appointment(
            doctor=self.doctor,
            patient=self.patient,
            scheduled_at=self.scheduled_at,
        )
        self.client.force_authenticate(self.doctor_user)

        response = self.client.patch(
            f"/api/v1/appointments/{appointment.id}",
            {"status": "cancelled"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "cancelled")
        self.assertEqual(response.data["status"], "cancelled")

        replacement_response = self.client.post(
            "/api/v1/appointments",
            {
                "patient": self.patient.id,
                "scheduled_at": self.scheduled_at.isoformat(),
                "duration_minutes": 30,
                "reason": "Cita de reemplazo",
            },
            format="json",
        )
        self.assertEqual(replacement_response.status_code, status.HTTP_201_CREATED)

    def test_pending_closure_filter_returns_only_past_active_appointments(self):
        past_appointment = create_appointment(
            doctor=self.doctor,
            patient=self.patient,
            scheduled_at=timezone.now() - timezone.timedelta(hours=2),
            duration_minutes=30,
        )
        create_appointment(
            doctor=self.doctor,
            patient=self.patient,
            scheduled_at=timezone.now() - timezone.timedelta(hours=3),
            status="attended",
        )
        create_appointment(
            doctor=self.doctor,
            patient=self.patient,
            scheduled_at=self.scheduled_at,
        )
        self.client.force_authenticate(self.doctor_user)

        response = self.client.get("/api/v1/appointments?pending_closure=true")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in response.data], [past_appointment.id])

    def test_doctor_can_close_past_appointments_as_attended_or_no_show(self):
        attended_appointment = create_appointment(
            doctor=self.doctor,
            patient=self.patient,
            scheduled_at=timezone.now() - timezone.timedelta(hours=3),
        )
        no_show_appointment = create_appointment(
            doctor=self.doctor,
            patient=self.patient,
            scheduled_at=timezone.now() - timezone.timedelta(hours=2),
        )
        self.client.force_authenticate(self.doctor_user)

        attended_response = self.client.patch(
            f"/api/v1/appointments/{attended_appointment.id}",
            {"status": "attended"},
            format="json",
        )
        no_show_response = self.client.patch(
            f"/api/v1/appointments/{no_show_appointment.id}",
            {"status": "no_show"},
            format="json",
        )

        self.assertEqual(attended_response.status_code, status.HTTP_200_OK)
        self.assertEqual(no_show_response.status_code, status.HTTP_200_OK)
        attended_appointment.refresh_from_db()
        no_show_appointment.refresh_from_db()
        self.assertEqual(attended_appointment.status, "attended")
        self.assertEqual(no_show_appointment.status, "no_show")

    def test_doctor_cannot_cancel_past_appointment(self):
        appointment = create_appointment(
            doctor=self.doctor,
            patient=self.patient,
            scheduled_at=timezone.now() - timezone.timedelta(hours=2),
        )
        self.client.force_authenticate(self.doctor_user)

        response = self.client.patch(
            f"/api/v1/appointments/{appointment.id}",
            {"status": "cancelled"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "scheduled")

    def test_doctor_reprograms_past_appointment_without_overwriting_history(self):
        original_scheduled_at = timezone.now() - timezone.timedelta(days=1)
        appointment = create_appointment(
            doctor=self.doctor,
            patient=self.patient,
            scheduled_at=original_scheduled_at,
            duration_minutes=30,
            reason="Consulta original",
        )
        new_scheduled_at = timezone.now() + timezone.timedelta(days=3)
        self.client.force_authenticate(self.doctor_user)

        response = self.client.post(
            f"/api/v1/appointments/{appointment.id}/reschedule",
            {
                "scheduled_at": new_scheduled_at.isoformat(),
                "duration_minutes": 45,
                "reason": "Nueva fecha",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        appointment.refresh_from_db()
        replacement = Appointment.objects.get(pk=response.data["id"])
        self.assertEqual(appointment.status, "superseded")
        self.assertEqual(appointment.scheduled_at, original_scheduled_at)
        self.assertEqual(replacement.status, "scheduled")
        self.assertEqual(replacement.patient, self.patient)
        self.assertEqual(replacement.doctor, self.doctor)
        self.assertEqual(replacement.duration_minutes, 45)

    def test_doctor_cannot_close_future_appointment_as_attended(self):
        appointment = create_appointment(
            doctor=self.doctor,
            patient=self.patient,
            scheduled_at=self.scheduled_at,
        )
        self.client.force_authenticate(self.doctor_user)

        response = self.client.patch(
            f"/api/v1/appointments/{appointment.id}",
            {"status": "attended"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "scheduled")

    @patch("api.services.secretary_access.InteractiveCoreSecretaryService.get_assigned_doctor_ids")
    def test_secretary_cannot_reschedule_to_the_past(self, get_assigned_doctor_ids):
        get_assigned_doctor_ids.return_value = [self.doctor.interactive_core_doctor_id]
        appointment = create_appointment(
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
        appointment = create_appointment(
            doctor=self.doctor,
            patient=self.patient,
            scheduled_at=self.scheduled_at,
        )
        create_appointment(
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



