from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from api.models import (
    Country,
    DoctorMedicine,
    DoctorMedicinePreference,
    DoctorPortalProfile,
    MedicineCatalogMirror,
    Organization,
    Prescription,
    PrescriptionItem,
)
from api.test_factories import create_doctor, create_patient, create_user
from api.test_registration import RegistrationBase


class DoctorCountryTests(RegistrationBase):
    def test_external_doctor_inherits_country_from_organization(self):
        invitation = self.invite("DOCTOR")
        response = self.register("DOCTOR", invitation, colegiation_code="COL-1", specialty_ids=[self.specialty.id])

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        doctor = DoctorPortalProfile.objects.get(user__email="ana@example.com")
        self.assertEqual(doctor.country, self.organization.country)

    def test_doctor_cannot_be_created_without_country(self):
        user = create_user("no-country@test.local", roles=["DOCTOR"])
        with self.assertRaises(IntegrityError), transaction.atomic():
            DoctorPortalProfile.objects.create(user=user, full_name="Sin pais", country=None)


class DoctorCatalogBase(TestCase):
    def setUp(self):
        self.client = APIClient(HTTP_HOST="localhost")
        self.country = Country.objects.get(code="HN")
        self.organization = Organization.objects.create(name="Clinica Externa", country=self.country)

        self.external_user = create_user("externo@test.local", roles=["DOCTOR"])
        self.external = create_doctor(
            user=self.external_user,
            interactive_core_doctor_id=None,
            origin="self_registered",
            organization=self.organization,
        )
        self.other_external_user = create_user("externo2@test.local", roles=["DOCTOR"])
        self.other_external = create_doctor(
            user=self.other_external_user,
            interactive_core_doctor_id=None,
            origin="self_registered",
            organization=self.organization,
        )
        self.ic_user = create_user("ic@test.local", roles=["DOCTOR"])
        self.ic_doctor = create_doctor(user=self.ic_user, interactive_core_doctor_id=910)

    def own_payload(self, **overrides):
        data = {
            "name": "Paracetamol",
            "presentation": "Tableta 500 mg",
            "active_ingredient": "Paracetamol",
            "default_dosage": "1 tableta",
            "default_frequency": "Cada 8 horas",
            "default_duration": "5 dias",
        }
        data.update(overrides)
        return data


class OwnMedicineCrudTests(DoctorCatalogBase):
    def test_external_doctor_creates_updates_and_deletes_own_medicine(self):
        self.client.force_authenticate(self.external_user)

        created = self.client.post("/api/v1/doctor/medicines", self.own_payload(), format="json")
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        medicine = DoctorMedicine.objects.get(pk=created.data["id"])
        self.assertEqual(medicine.doctor, self.external)

        updated = self.client.patch(
            f"/api/v1/doctor/medicines/{medicine.id}", {"category": "favorite"}, format="json"
        )
        self.assertEqual(updated.status_code, status.HTTP_200_OK, updated.data)
        self.assertEqual(updated.data["category"], "favorite")

        deleted = self.client.delete(f"/api/v1/doctor/medicines/{medicine.id}")
        self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(DoctorMedicine.objects.filter(pk=medicine.id).exists())

    def test_interactive_core_doctor_cannot_manage_own_catalog(self):
        self.client.force_authenticate(self.ic_user)

        response = self.client.post("/api/v1/doctor/medicines", self.own_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(DoctorMedicine.objects.exists())

    def test_doctors_do_not_see_or_touch_each_others_medicines(self):
        other = DoctorMedicine.objects.create(doctor=self.other_external, name="Ajeno")
        self.client.force_authenticate(self.external_user)

        listing = self.client.get("/api/v1/doctor/medicines")
        detail = self.client.patch(f"/api/v1/doctor/medicines/{other.id}", {"name": "Mio"}, format="json")
        removal = self.client.delete(f"/api/v1/doctor/medicines/{other.id}")

        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual(listing.data, [])
        self.assertEqual(detail.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(removal.status_code, status.HTTP_404_NOT_FOUND)
        other.refresh_from_db()
        self.assertEqual(other.name, "Ajeno")

    def test_duplicate_name_and_presentation_is_rejected_ignoring_case(self):
        DoctorMedicine.objects.create(doctor=self.external, name="Paracetamol", presentation="Tableta 500 mg")
        self.client.force_authenticate(self.external_user)

        response = self.client.post(
            "/api/v1/doctor/medicines",
            self.own_payload(name="paracetamol", presentation="tableta 500 MG"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", response.data)

    def test_same_name_with_other_presentation_is_allowed(self):
        DoctorMedicine.objects.create(doctor=self.external, name="Paracetamol", presentation="Tableta 500 mg")
        self.client.force_authenticate(self.external_user)

        response = self.client.post(
            "/api/v1/doctor/medicines", self.own_payload(presentation="Jarabe 120 mg/5 ml"), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_another_doctor_can_use_the_same_name(self):
        DoctorMedicine.objects.create(doctor=self.other_external, name="Paracetamol", presentation="Tableta 500 mg")
        self.client.force_authenticate(self.external_user)

        response = self.client.post("/api/v1/doctor/medicines", self.own_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_name_is_required(self):
        self.client.force_authenticate(self.external_user)

        response = self.client.post("/api/v1/doctor/medicines", self.own_payload(name="   "), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class UnifiedCatalogTests(DoctorCatalogBase):
    def setUp(self):
        super().setUp()
        self.synced = MedicineCatalogMirror.objects.create(
            interactive_core_product_id=1, country=self.country, name="Amoxicilina", active_ingredient="Amoxicilina"
        )
        self.synced_favorite = MedicineCatalogMirror.objects.create(
            interactive_core_product_id=2, country=self.country, name="Losartan"
        )
        self.other_country = Country.objects.exclude(code="HN").first()
        self.foreign = MedicineCatalogMirror.objects.create(
            interactive_core_product_id=3, country=self.other_country, name="Otro pais"
        )
        self.inactive = MedicineCatalogMirror.objects.create(
            interactive_core_product_id=4, country=self.country, name="Inactivo", is_active=False
        )

    def names(self, response):
        return [entry["name"] for entry in response.data]

    def test_interactive_core_doctor_gets_synced_catalog_of_their_country(self):
        self.client.force_authenticate(self.ic_user)

        response = self.client.get("/api/v1/doctor/medicine-catalog")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(set(self.names(response)), {"Amoxicilina", "Losartan"})
        self.assertTrue(all(entry["source"] == "catalog" for entry in response.data))

    def test_interactive_core_doctor_sees_preferences_and_favorites_first(self):
        preference = DoctorMedicinePreference.objects.create(
            doctor=self.ic_doctor, medicine=self.synced_favorite, category="favorite", notes="De primera linea"
        )
        self.client.force_authenticate(self.ic_user)

        response = self.client.get("/api/v1/doctor/medicine-catalog")

        self.assertEqual(self.names(response), ["Losartan", "Amoxicilina"])
        first = response.data[0]
        self.assertEqual(first["category"], "favorite")
        self.assertEqual(first["preference_id"], preference.id)
        self.assertEqual(first["notes"], "De primera linea")
        self.assertEqual(first["medicine"], self.synced_favorite.id)
        self.assertIsNone(first["doctor_medicine"])
        self.assertEqual(response.data[1]["category"], "undetermined")
        self.assertIsNone(response.data[1]["preference_id"])

    def test_preferences_of_other_doctors_do_not_leak(self):
        other_ic = create_doctor(user=create_user("ic2@test.local", roles=["DOCTOR"]), interactive_core_doctor_id=911)
        DoctorMedicinePreference.objects.create(doctor=other_ic, medicine=self.synced, category="favorite")
        self.client.force_authenticate(self.ic_user)

        response = self.client.get("/api/v1/doctor/medicine-catalog")

        self.assertTrue(all(entry["category"] == "undetermined" for entry in response.data))

    def test_interactive_core_doctor_filters_by_search_and_category(self):
        DoctorMedicinePreference.objects.create(doctor=self.ic_doctor, medicine=self.synced_favorite, category="favorite")
        self.client.force_authenticate(self.ic_user)

        searched = self.client.get("/api/v1/doctor/medicine-catalog", {"search": "amox"})
        favorites = self.client.get("/api/v1/doctor/medicine-catalog", {"category": "favorite"})

        self.assertEqual(self.names(searched), ["Amoxicilina"])
        self.assertEqual(self.names(favorites), ["Losartan"])

    def test_external_doctor_gets_only_their_own_active_medicines(self):
        DoctorMedicine.objects.create(doctor=self.external, name="Ibuprofeno")
        DoctorMedicine.objects.create(doctor=self.external, name="Archivado", is_active=False)
        DoctorMedicine.objects.create(doctor=self.other_external, name="Ajeno")
        self.client.force_authenticate(self.external_user)

        response = self.client.get("/api/v1/doctor/medicine-catalog")

        self.assertEqual(self.names(response), ["Ibuprofeno"])
        entry = response.data[0]
        self.assertEqual(entry["source"], "own")
        self.assertIsNone(entry["medicine"])
        self.assertEqual(entry["doctor_medicine"], DoctorMedicine.objects.get(name="Ibuprofeno").id)

    def test_external_doctor_orders_favorites_first_and_can_include_archived(self):
        DoctorMedicine.objects.create(doctor=self.external, name="Aspirina")
        DoctorMedicine.objects.create(doctor=self.external, name="Zinc", category="favorite")
        DoctorMedicine.objects.create(doctor=self.external, name="Archivado", is_active=False)
        self.client.force_authenticate(self.external_user)

        ordered = self.client.get("/api/v1/doctor/medicine-catalog")
        with_archived = self.client.get("/api/v1/doctor/medicine-catalog", {"include_inactive": "true"})

        self.assertEqual(self.names(ordered), ["Zinc", "Aspirina"])
        self.assertIn("Archivado", self.names(with_archived))

    def test_catalog_is_paginated_only_on_request(self):
        for index in range(12):
            DoctorMedicine.objects.create(doctor=self.external, name=f"Medicamento {index:02d}")
        self.client.force_authenticate(self.external_user)

        full = self.client.get("/api/v1/doctor/medicine-catalog")
        paged = self.client.get("/api/v1/doctor/medicine-catalog", {"page": 1})

        self.assertEqual(len(full.data), 12)
        self.assertEqual(paged.data["count"], 12)
        self.assertEqual(len(paged.data["results"]), 10)

    def test_user_without_doctor_profile_is_rejected(self):
        self.client.force_authenticate(create_user("nadie@test.local", roles=["SECRETARY"]))

        response = self.client.get("/api/v1/doctor/medicine-catalog")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class PrescriptionCatalogTests(DoctorCatalogBase):
    def setUp(self):
        super().setUp()
        self.synced = MedicineCatalogMirror.objects.create(
            interactive_core_product_id=1,
            country=self.country,
            name="Amoxicilina",
            presentation="Capsula 500 mg",
            active_ingredient="Amoxicilina",
        )
        self.own = DoctorMedicine.objects.create(
            doctor=self.external, name="Ibuprofeno", presentation="Tableta 400 mg", active_ingredient="Ibuprofeno"
        )
        self.ic_patient = create_patient(self.ic_doctor)
        self.external_patient = create_patient(self.external)

    def payload(self, patient, **item):
        entry = {"dosage": "1 unidad", "frequency": "Cada 8 horas", "duration": "5 dias"}
        entry.update(item)
        return {"patient": patient.id, "diagnosis": "Control", "items": [entry]}

    def post(self, user, patient, **item):
        self.client.force_authenticate(user)
        return self.client.post("/api/v1/prescriptions", self.payload(patient, **item), format="json")

    def test_external_doctor_prescribes_from_own_catalog_with_snapshot(self):
        response = self.post(self.external_user, self.external_patient, doctor_medicine=self.own.id)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        item = PrescriptionItem.objects.get()
        self.assertEqual(item.doctor_medicine, self.own)
        self.assertIsNone(item.medicine)
        self.assertEqual(item.medicine_name, "Ibuprofeno")
        self.assertEqual(item.presentation, "Tableta 400 mg")
        self.assertEqual(response.data["items"][0]["medicine_name"], "Ibuprofeno")

    def test_snapshot_survives_editing_and_deleting_the_catalog_entry(self):
        response = self.post(self.external_user, self.external_patient, doctor_medicine=self.own.id)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        self.own.name = "Renombrado"
        self.own.save()
        item = PrescriptionItem.objects.get()
        self.assertEqual(item.medicine_name, "Ibuprofeno")

        self.own.delete()
        item.refresh_from_db()
        self.assertIsNone(item.doctor_medicine)
        self.assertEqual(item.medicine_name, "Ibuprofeno")
        detail = self.client.get(f"/api/v1/prescriptions/{item.prescription_id}")
        self.assertEqual(detail.data["items"][0]["medicine_name"], "Ibuprofeno")

    def test_interactive_core_doctor_prescribes_from_synced_catalog_with_snapshot(self):
        response = self.post(self.ic_user, self.ic_patient, medicine=self.synced.id)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        item = PrescriptionItem.objects.get()
        self.assertEqual(item.medicine_name, "Amoxicilina")
        self.assertEqual(item.presentation, "Capsula 500 mg")
        self.assertIsNone(item.doctor_medicine)

    def test_snapshot_fields_cannot_be_forged_by_the_client(self):
        response = self.post(
            self.external_user, self.external_patient, doctor_medicine=self.own.id, medicine_name="Falso"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(PrescriptionItem.objects.get().medicine_name, "Ibuprofeno")

    def test_external_doctor_cannot_use_another_doctors_medicine(self):
        foreign = DoctorMedicine.objects.create(doctor=self.other_external, name="Ajeno")

        response = self.post(self.external_user, self.external_patient, doctor_medicine=foreign.id)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Prescription.objects.exists())

    def test_external_doctor_cannot_use_archived_medicine(self):
        self.own.is_active = False
        self.own.save()

        response = self.post(self.external_user, self.external_patient, doctor_medicine=self.own.id)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_external_doctor_cannot_use_synced_catalog(self):
        response = self.post(self.external_user, self.external_patient, medicine=self.synced.id)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Prescription.objects.exists())

    def test_interactive_core_doctor_cannot_use_own_catalog(self):
        response = self.post(self.ic_user, self.ic_patient, doctor_medicine=self.own.id)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_interactive_core_doctor_cannot_use_other_country_medicine(self):
        other_country = Country.objects.exclude(code="HN").first()
        foreign = MedicineCatalogMirror.objects.create(
            interactive_core_product_id=9, country=other_country, name="Otro pais"
        )

        response = self.post(self.ic_user, self.ic_patient, medicine=foreign.id)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_item_needs_exactly_one_catalog(self):
        neither = self.post(self.external_user, self.external_patient)
        both = self.post(self.external_user, self.external_patient, doctor_medicine=self.own.id, medicine=self.synced.id)

        self.assertEqual(neither.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(both.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_can_be_filtered_by_patient(self):
        other_patient = create_patient(self.external, first_name="Otro", last_name="Paciente")
        self.post(self.external_user, self.external_patient, doctor_medicine=self.own.id)
        self.post(self.external_user, other_patient, doctor_medicine=self.own.id)

        everything = self.client.get("/api/v1/prescriptions")
        filtered = self.client.get("/api/v1/prescriptions", {"patient": self.external_patient.id})

        self.assertEqual(len(everything.data), 2)
        self.assertEqual([row["patient"] for row in filtered.data], [self.external_patient.id])
