from django.test import TestCase
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APIClient

from api.models import PatientVitals
from api.test_factories import create_appointment, create_doctor, create_patient, create_user, create_vitals



class PreclinicTests(TestCase):
    def setUp(self):
        self.client = APIClient(HTTP_HOST="localhost")
        self.user = create_user(
            username="preclinic-doctor",
            email="preclinic@test.local",
            password="Doctor1234!",
            roles=["DOCTOR"],
        )
        self.doctor = create_doctor(
            user=self.user,
            interactive_core_doctor_id=200,
            full_name="Dra. Preclinica",
            specialties=[{"name": "Pediatria", "code": "PED"}],
            status="active",
        )
        self.patient = create_patient(
            doctor=self.doctor,
            first_name="Paciente",
            last_name="Control",
        )
        self.previous_appointment = create_appointment(
            doctor=self.doctor,
            patient=self.patient,
            scheduled_at=timezone.now() - timezone.timedelta(days=30),
        )
        create_vitals(
            patient=self.patient,
            appointment=self.previous_appointment,
            blood_pressure_systolic=110,
            blood_pressure_diastolic=70,
            oxygen_saturation="98.00",
            temperature="37.2",
            height_cm="120.00",
            weight_kg="22.50",
        )
        self.appointment = create_appointment(
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
        future_appointment = create_appointment(
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

