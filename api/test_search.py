from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from api.models import Prescription
from api.test_factories import create_appointment, create_doctor, create_patient


class GlobalSearchTests(APITestCase):
    def setUp(self):
        self.doctor = create_doctor(interactive_core_doctor_id=810)
        self.patient = create_patient(
            self.doctor,
            first_name="Ana",
            last_name="Martinez",
            dni="0801-1990-12345",
        )
        self.appointment = create_appointment(
            self.doctor,
            self.patient,
            timezone.now() + timezone.timedelta(days=1),
            reason="Control de migraña",
        )
        self.prescription = Prescription.objects.create(
            doctor=self.doctor,
            patient=self.patient,
            appointment=self.appointment,
            diagnosis="Migraña recurrente",
        )
        self.client.force_authenticate(self.doctor.user)

    def test_search_returns_scoped_clinical_records(self):
        response = self.client.get("/api/v1/search", {"q": "Ana"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([row["id"] for row in response.data["patients"]], [self.patient.id])
        self.assertEqual([row["id"] for row in response.data["appointments"]], [self.appointment.id])
        self.assertEqual([row["id"] for row in response.data["prescriptions"]], [self.prescription.id])

    def test_search_does_not_return_another_doctors_records(self):
        other_doctor = create_doctor(interactive_core_doctor_id=811)
        create_patient(other_doctor, first_name="Ana", last_name="Fuera")

        response = self.client.get("/api/v1/search", {"q": "Ana"})

        self.assertEqual(len(response.data["patients"]), 1)
        self.assertEqual(response.data["patients"][0]["id"], self.patient.id)

    def test_search_requires_at_least_two_characters(self):
        response = self.client.get("/api/v1/search", {"q": "A"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["patients"], [])
        self.assertEqual(response.data["appointments"], [])
        self.assertEqual(response.data["prescriptions"], [])
