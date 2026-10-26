from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from api.models import MedicineCatalogMirror, Prescription, PrescriptionItem
from api.test_factories import create_appointment, create_doctor, create_patient, create_user


class PrescriptionIntegrityTests(TestCase):
    def setUp(self):
        self.client = APIClient(HTTP_HOST="localhost")
        self.user = create_user("prescription-doctor@test.local", roles=["DOCTOR"])
        self.doctor = create_doctor(user=self.user, interactive_core_doctor_id=811)
        self.patient = create_patient(self.doctor, first_name="Paciente", last_name="Receta")
        self.other_patient = create_patient(self.doctor, first_name="Paciente", last_name="Distinto")
        self.appointment = create_appointment(
            self.doctor,
            self.patient,
            timezone.now() + timezone.timedelta(days=1),
        )
        self.other_appointment = create_appointment(
            self.doctor,
            self.other_patient,
            timezone.now() + timezone.timedelta(days=2),
        )
        self.medicine = MedicineCatalogMirror.objects.create(
            interactive_core_product_id=501,
            country=self.doctor.country,
            name="Medicamento de prueba",
        )
        self.client.force_authenticate(self.user)

    def payload(self, **overrides):
        data = {
            "patient": self.patient.id,
            "appointment": self.appointment.id,
            "diagnosis": "Control",
            "items": [
                {
                    "medicine": self.medicine.id,
                    "dosage": "1 tableta",
                    "frequency": "Cada 8 horas",
                    "duration": "5 dias",
                }
            ],
        }
        data.update(overrides)
        return data

    def test_creates_prescription_with_items(self):
        response = self.client.post("/api/v1/prescriptions", self.payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(Prescription.objects.count(), 1)
        self.assertEqual(PrescriptionItem.objects.count(), 1)

    def test_rejects_appointment_for_another_patient(self):
        response = self.client.post(
            "/api/v1/prescriptions",
            self.payload(appointment=self.other_appointment.id),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("appointment", response.data)
        self.assertFalse(Prescription.objects.exists())

    def test_rejects_empty_prescription(self):
        response = self.client.post(
            "/api/v1/prescriptions",
            self.payload(items=[]),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("items", response.data)

    def test_item_failure_rolls_back_header(self):
        with patch.object(PrescriptionItem.objects, "create", side_effect=RuntimeError("write failed")):
            with self.assertRaises(RuntimeError):
                self.client.post("/api/v1/prescriptions", self.payload(), format="json")

        self.assertFalse(Prescription.objects.exists())
