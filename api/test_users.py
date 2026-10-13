from unittest import mock

from django.contrib.auth.models import Group
from django.test import TestCase

from rest_framework import status
from rest_framework.test import APIClient

from api.services.interactive_core import InteractiveCoreUnavailable
from api.test_factories import create_user


ADMIN_EMAILS_IN_INTERACTIVE_CORE = {"admin@test.local"}


def fake_user_is_interactive_core_admin(user):
    return getattr(user, "email", "") in ADMIN_EMAILS_IN_INTERACTIVE_CORE


class AdminUserManagementTests(TestCase):
    def setUp(self):
        self.client = APIClient(HTTP_HOST="localhost")
        self.admin_user = create_user(
            username="admin@test.local",
            email="admin@test.local",
            password="Admin1234!",
            roles=["ADMIN"],
        )
        self.doctor_user = create_user(
            username="doctor-users@test.local",
            email="doctor-users@test.local",
            password="Doctor1234!",
            roles=["DOCTOR"],
        )

        patcher = mock.patch(
            "api.permissions.admin_permissions.user_is_interactive_core_admin",
            side_effect=fake_user_is_interactive_core_admin,
        )
        self.mock_is_interactive_core_admin = patcher.start()
        self.addCleanup(patcher.stop)

    def test_admin_can_list_users(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.get("/api/v1/admin/users")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 2)

    def test_non_admin_cannot_list_users(self):
        self.client.force_authenticate(self.doctor_user)

        response = self.client.get("/api/v1/admin/users")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create_user_with_role(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.post(
            "/api/v1/admin/users",
            {
                "username": "nueva.secretaria@test.local",
                "email": "nueva.secretaria@test.local",
                "first_name": "Nueva",
                "last_name": "Secretaria",
                "password": "Temporal123!",
                "roles": ["SECRETARY"],
                "country_code": "HN",
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Group.objects.filter(name="SECRETARY", user__email="nueva.secretaria@test.local").exists())

    def test_admin_password_reset_generates_temporary_password(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.post(
            f"/api/v1/admin/users/{self.doctor_user.id}/reset-password",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("temporary_password", response.data)
        self.assertNotIn(str(self.doctor_user.id), response.data["temporary_password"])
        self.doctor_user.refresh_from_db()
        self.assertTrue(self.doctor_user.check_password(response.data["temporary_password"]))

    def test_local_admin_group_without_interactive_core_role_is_denied(self):
        local_only_admin = create_user(
            username="fake-admin@test.local",
            email="fake-admin@test.local",
            password="FakeAdmin123!",
            roles=["ADMIN"],
        )
        self.client.force_authenticate(local_only_admin)

        response = self.client.get("/api/v1/admin/users")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_module_returns_503_when_interactive_core_is_unreachable(self):
        self.mock_is_interactive_core_admin.side_effect = InteractiveCoreUnavailable()
        self.client.force_authenticate(self.admin_user)

        response = self.client.get("/api/v1/admin/users")

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

