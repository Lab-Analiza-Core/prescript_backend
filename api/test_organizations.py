from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from api.models import (
    Country,
    CountryDivision,
    DoctorPortalProfile,
    Organization,
    PatientPortalProfile,
    TermsVersion,
)
from api.roles import PRESCRIPT_ROLE_ORG_ADMIN, PRESCRIPT_ROLE_PATIENT, get_primary_prescript_role


class OrganizationFoundationTests(TestCase):
    def setUp(self):
        self.country = Country.objects.get(code="GT")

    def test_migration_seeds_divisions_with_country_specific_label(self):
        self.assertEqual(CountryDivision.objects.filter(country__code="GT").count(), 22)
        self.assertEqual(CountryDivision.objects.filter(country__code="HN").count(), 18)
        self.assertEqual(CountryDivision.objects.filter(country__code="SV").count(), 14)
        costa_rica = CountryDivision.objects.filter(country__code="CR")
        self.assertEqual(costa_rica.count(), 7)
        self.assertEqual(costa_rica.first().division_type, "Provincia")

    def test_migration_creates_one_interactive_core_organization_per_country(self):
        for country in Country.objects.all():
            self.assertEqual(
                Organization.objects.filter(country=country, is_interactive_core=True).count(), 1
            )

    def test_only_one_interactive_core_organization_per_country(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Organization.objects.create(name="Otra IC", country=self.country, is_interactive_core=True)

    def test_organization_name_is_unique_per_country(self):
        Organization.objects.create(name="Clinica Norte", country=self.country)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Organization.objects.create(name="Clinica Norte", country=self.country)

    def test_self_registered_doctor_can_exist_without_interactive_core_id(self):
        user = get_user_model().objects.create_user("ext@example.com", "ext@example.com", "pass12345")
        organization = Organization.objects.create(name="Clinica Sur", country=self.country)
        doctor = DoctorPortalProfile.objects.create(
            user=user,
            full_name="Externo",
            organization=organization,
            country=self.country,
            origin="self_registered",
        )
        self.assertIsNone(doctor.interactive_core_doctor_id)

    def test_new_profiles_default_to_interactive_core_origin(self):
        user = get_user_model().objects.create_user("ic@example.com", "ic@example.com", "pass12345")
        doctor = DoctorPortalProfile.objects.create(
            user=user, full_name="IC", interactive_core_doctor_id=1, country=self.country
        )
        self.assertEqual(doctor.origin, "interactive_core")

    def test_patient_document_is_unique_per_country_and_type(self):
        organization = Organization.objects.create(name="Clinica Este", country=self.country)
        user_model = get_user_model()
        PatientPortalProfile.objects.create(
            user=user_model.objects.create_user("p1@example.com", "p1@example.com", "pass12345"),
            organization=organization,
            country=self.country,
            full_name="P1",
            document_number="1234",
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            PatientPortalProfile.objects.create(
                user=user_model.objects.create_user("p2@example.com", "p2@example.com", "pass12345"),
                organization=organization,
                country=self.country,
                full_name="P2",
                document_number="1234",
            )

    def test_only_one_current_terms_version(self):
        TermsVersion.objects.create(version="1.0", content="a", is_current=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            TermsVersion.objects.create(version="2.0", content="b", is_current=True)

    def test_new_roles_resolve_with_expected_priority(self):
        self.assertEqual(get_primary_prescript_role([PRESCRIPT_ROLE_PATIENT]), PRESCRIPT_ROLE_PATIENT)
        self.assertEqual(
            get_primary_prescript_role([PRESCRIPT_ROLE_PATIENT, PRESCRIPT_ROLE_ORG_ADMIN]),
            PRESCRIPT_ROLE_ORG_ADMIN,
        )


class SpecialtySyncTests(TestCase):
    class FakeCatalog:
        def __init__(self, pages):
            self.pages = pages
            self.calls = []

        def list_specialties(self, params=None):
            self.calls.append(params)
            return self.pages[len(self.calls) - 1]

    def sync(self, pages, **kwargs):
        from unittest.mock import patch

        from api.services.specialty_sync_service import SpecialtySyncService

        with patch("api.services.specialty_sync_service.settings.INTERACTIVE_CORE_API_BASE_URL", "http://ic.test"):
            return SpecialtySyncService(catalog_service=self.FakeCatalog(pages)).sync(**kwargs)

    def test_creates_and_updates_from_plain_list(self):
        from api.models import SpecialtyCatalogMirror

        result = self.sync([[{"id": 1, "name": "Pediatria"}, {"id": 2, "name": "Cardiologia"}]])
        self.assertEqual(result["created"], 2)
        result = self.sync([[{"id": 1, "name": "Pediatria General"}]], deactivate_missing=False)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(SpecialtyCatalogMirror.objects.get(interactive_core_id=1).name, "Pediatria General")

    def test_follows_paginated_results_and_deactivates_missing(self):
        from api.models import SpecialtyCatalogMirror

        self.sync([[{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]])
        result = self.sync(
            [
                {"results": [{"id": 1, "name": "A"}], "next": "http://x?page=2"},
                {"results": [{"id": 3, "name": "C"}], "next": None},
            ]
        )
        self.assertEqual(result, {"created": 1, "updated": 1, "deactivated": 1})
        self.assertFalse(SpecialtyCatalogMirror.objects.get(interactive_core_id=2).is_active)

    def test_empty_response_does_not_deactivate_catalog(self):
        from api.models import SpecialtyCatalogMirror

        self.sync([[{"id": 1, "name": "A"}]])
        self.sync([[]])
        self.assertTrue(SpecialtyCatalogMirror.objects.get(interactive_core_id=1).is_active)

    def test_same_name_in_different_countries_is_kept_per_country(self):
        from api.models import SpecialtyCatalogMirror

        result = self.sync(
            [
                [
                    {"id": 6, "name": "Cardiologia", "country_code": "HN"},
                    {"id": 64, "name": "Cardiologia", "country_code": "SV"},
                ]
            ]
        )
        self.assertEqual(result["created"], 2)
        self.assertEqual(
            SpecialtyCatalogMirror.objects.get(country__code="SV", name="Cardiologia").interactive_core_id, 64
        )

    def test_uses_interactive_core_database_when_api_is_not_configured(self):
        from unittest.mock import MagicMock, patch

        catalog = MagicMock()
        catalog.list_specialties_from_local_db.return_value = [
            {"id": 9, "name": "Nefrologia", "is_active": True, "country_code": "GT"}
        ]
        from api.services.specialty_sync_service import SpecialtySyncService

        with patch("api.services.specialty_sync_service.settings.INTERACTIVE_CORE_API_BASE_URL", ""):
            result = SpecialtySyncService(catalog_service=catalog).sync()
        self.assertEqual(result["created"], 1)
        catalog.list_specialties.assert_not_called()
