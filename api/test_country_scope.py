from unittest import mock

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from api.models import Country, UserCountryAccess
from api.test_factories import create_doctor, create_patient, create_user


class CountryScopeApiTests(TestCase):
    def setUp(self):
        self.client = APIClient(HTTP_HOST="localhost")
        self.honduras = Country.objects.get(code="HN")
        self.guatemala = Country.objects.get(code="GT")

        self.hn_doctor = create_doctor(
            interactive_core_doctor_id=8101,
            full_name="Doctora Honduras",
            country=self.honduras,
        )
        self.gt_doctor = create_doctor(
            interactive_core_doctor_id=8102,
            full_name="Doctor Guatemala",
            country=self.guatemala,
        )
        create_patient(self.hn_doctor, first_name="Paciente", last_name="Honduras")
        create_patient(self.gt_doctor, first_name="Paciente", last_name="Guatemala")

    def test_country_admin_only_lists_doctors_from_its_country(self):
        admin = create_user("admin-gt@test.local", roles=["ADMIN_GT"])
        self.client.force_authenticate(admin)

        response = self.client.get("/api/v1/doctors")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([doctor["id"] for doctor in response.data], [self.gt_doctor.id])

    def test_country_admin_cannot_switch_to_an_unassigned_country(self):
        admin = create_user("admin-gt@test.local", roles=["ADMIN_GT"])
        self.client.force_authenticate(admin)

        response = self.client.get("/api/v1/patients", HTTP_X_PRESCRIPT_COUNTRY="HN")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_global_admin_can_view_all_or_select_one_country(self):
        admin = create_user("admin-global@test.local", roles=["ADMIN"])
        self.client.force_authenticate(admin)

        all_response = self.client.get("/api/v1/doctors")
        gt_response = self.client.get("/api/v1/doctors", HTTP_X_PRESCRIPT_COUNTRY="GT")

        self.assertEqual(all_response.status_code, status.HTTP_200_OK)
        self.assertCountEqual(
            [doctor["id"] for doctor in all_response.data],
            [self.hn_doctor.id, self.gt_doctor.id],
        )
        self.assertEqual([doctor["id"] for doctor in gt_response.data], [self.gt_doctor.id])

    def test_manager_access_is_fixed_to_its_country(self):
        manager = create_user("manager-hn@test.local", roles=["COUNTRY_MANAGER"])
        UserCountryAccess.objects.create(
            user=manager,
            role_code="COUNTRY_MANAGER",
            country=self.honduras,
        )
        self.client.force_authenticate(manager)

        response = self.client.get("/api/v1/patients")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["doctor"], self.hn_doctor.id)

    @mock.patch("api.views.doctor_views.InteractiveCoreAccessService.sync_user_workspaces", return_value=[])
    def test_auth_me_exposes_global_country_selector_context(self, _sync_workspaces):
        admin = create_user("admin-context@test.local", roles=["ADMIN"])
        self.client.force_authenticate(admin)

        response = self.client.get("/api/v1/auth/me", HTTP_X_PRESCRIPT_COUNTRY="SV")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        context = response.data["country_context"]
        self.assertTrue(context["is_global_admin"])
        self.assertEqual(context["selected_country"]["code"], "SV")
        self.assertCountEqual(
            [country["code"] for country in context["available_countries"]],
            ["CR", "GT", "HN", "SV"],
        )
