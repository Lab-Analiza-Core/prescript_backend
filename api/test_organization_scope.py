from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import Group
from django.test import TestCase
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.test import APIClient

from api.models import (
    Appointment,
    Country,
    Organization,
    OrganizationAdminProfile,
    PatientPortalProfile,
    SecretaryDoctorAssignment,
)
from api.permissions.admin_permissions import IsPrescriptAdminOrOrgAdmin
from api.services.access_activation_service import AccessActivationService
from api.services.interactive_core import InteractiveCoreAccessService
from api.services.interactive_core.access_service import user_is_interactive_core_admin
from api.test_factories import (
    create_appointment,
    create_doctor,
    create_nurse,
    create_patient,
    create_secretary,
    create_user,
)

EXTERNAL = {"origin": "self_registered"}


class OrganizationScopeBase(TestCase):
    def setUp(self):
        self.client = APIClient(HTTP_HOST="localhost")
        self.hn = Country.objects.get(code="HN")
        self.ic_org = Organization.objects.get(country=self.hn, is_interactive_core=True)
        self.org_a = Organization.objects.create(name="Clinica A", country=self.hn)
        self.org_b = Organization.objects.create(name="Clinica B", country=self.hn)

        self.ic_doctor = create_doctor(interactive_core_doctor_id=9001, organization=self.ic_org, full_name="Dr IC")
        self.doctor_a = create_doctor(
            interactive_core_doctor_id=None, organization=self.org_a, full_name="Dr A", **EXTERNAL,
            user=create_user("doc-a@test.local", roles=["DOCTOR"]),
        )
        self.doctor_b = create_doctor(
            interactive_core_doctor_id=None, organization=self.org_b, full_name="Dr B", **EXTERNAL,
            user=create_user("doc-b@test.local", roles=["DOCTOR"]),
        )
        self.patient_ic = create_patient(self.ic_doctor, last_name="DeIC")
        self.patient_a = create_patient(self.doctor_a, last_name="DeA")
        self.patient_b = create_patient(self.doctor_b, last_name="DeB")

    def patients_seen_by(self, user):
        self.client.force_authenticate(user)
        response = self.client.get("/api/v1/patients")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return {item["last_name"] for item in response.data}


class PatientVisibilityTests(OrganizationScopeBase):
    def test_external_nurse_only_sees_her_organization(self):
        nurse = create_nurse(
            interactive_core_user_id=None, interactive_core_employee_id=None,
            organization=self.org_a, user=create_user("nurse-a@test.local", roles=["NURSE"]), **EXTERNAL,
        )
        self.assertEqual(self.patients_seen_by(nurse.user), {"DeA"})

    def test_interactive_core_nurse_does_not_see_external_organizations(self):
        nurse = create_nurse(organization=self.ic_org)
        self.assertEqual(self.patients_seen_by(nurse.user), {"DeIC"})

    def test_country_manager_without_profile_does_not_see_external_organizations(self):
        manager = create_user("manager-hn@test.local", roles=["COUNTRY_MANAGER"])
        from api.models import UserCountryAccess

        UserCountryAccess.objects.create(user=manager, role_code="COUNTRY_MANAGER", country=self.hn)
        self.assertEqual(self.patients_seen_by(manager), {"DeIC"})

    def test_global_admin_sees_every_organization(self):
        admin = create_user("root@test.local", roles=["ADMIN"])
        self.assertEqual(self.patients_seen_by(admin), {"DeIC", "DeA", "DeB"})

    def test_org_admin_only_sees_his_organization_and_only_when_approved(self):
        user = create_user("orgadmin@test.local", roles=["ORG_ADMIN"])
        profile = OrganizationAdminProfile.objects.create(
            user=user, organization=self.org_a, full_name="Admin A", country=self.hn, status="pending"
        )
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get("/api/v1/patients").data, [])
        profile.status = "active"
        profile.save()
        # El administrador de organizacion no es personal clinico: no ve pacientes por ese rol.
        self.assertEqual(self.client.get("/api/v1/patients").data, [])

    def test_suspended_organization_hides_its_data_from_members(self):
        nurse = create_nurse(
            interactive_core_user_id=None, interactive_core_employee_id=None,
            organization=self.org_a, user=create_user("nurse-s@test.local", roles=["NURSE"]), **EXTERNAL,
        )
        self.org_a.status = "suspended"
        self.org_a.save()
        self.assertEqual(self.patients_seen_by(nurse.user), set())

    def test_nurse_cannot_assign_patient_to_doctor_of_another_organization(self):
        nurse = create_nurse(
            interactive_core_user_id=None, interactive_core_employee_id=None,
            organization=self.org_a, user=create_user("nurse-w@test.local", roles=["NURSE"]), **EXTERNAL,
        )
        self.client.force_authenticate(nurse.user)
        response = self.client.post(
            "/api/v1/patients",
            {"first_name": "X", "last_name": "Y", "dni": "0801199012345", "phone": "88881234", "doctor": self.doctor_b.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)


class ExternalFlagTests(OrganizationScopeBase):
    def test_patients_and_appointments_flag_external_doctors(self):
        admin = create_user("root-flag@test.local", roles=["ADMIN"])
        client = APIClient(HTTP_HOST="localhost")
        client.force_authenticate(admin)

        flags = {item["last_name"]: item["doctor_is_external"] for item in client.get("/api/v1/patients").data}
        self.assertEqual(flags, {"DeIC": False, "DeA": True, "DeB": True})

        when = timezone.now() + timedelta(days=1)
        create_appointment(self.doctor_a, self.patient_a, when)
        appointment = Appointment.objects.get(doctor=self.doctor_a)
        # El doctor externo ve su propia cita marcada como externa.
        client.force_authenticate(self.doctor_a.user)
        listing = client.get("/api/v1/appointments")
        self.assertEqual([item["doctor_is_external"] for item in listing.data], [True])
        self.assertEqual(appointment.doctor, self.doctor_a)

    def test_doctor_profile_exposes_is_external(self):
        client = APIClient(HTTP_HOST="localhost")
        client.force_authenticate(self.doctor_a.user)
        self.assertTrue(client.get("/api/v1/doctor/me").data["is_external"])
        client.force_authenticate(self.ic_doctor.user)
        self.assertFalse(client.get("/api/v1/doctor/me").data["is_external"])


class SecretaryAssignmentTests(OrganizationScopeBase):
    def setUp(self):
        super().setUp()
        self.secretary = create_secretary(
            secretaria_interactivecore_id=None, organization=self.org_a,
            user=create_user("sec-a@test.local", roles=["SECRETARY"]), **EXTERNAL,
        )

    def test_secretary_without_assignments_sees_nothing(self):
        self.assertEqual(self.patients_seen_by(self.secretary.user), set())

    def test_secretary_sees_only_locally_assigned_doctors(self):
        SecretaryDoctorAssignment.objects.create(secretary=self.secretary, doctor=self.doctor_a)
        self.assertEqual(self.patients_seen_by(self.secretary.user), {"DeA"})

    def test_assignment_to_doctor_of_another_organization_is_ignored(self):
        SecretaryDoctorAssignment.objects.create(secretary=self.secretary, doctor=self.doctor_b)
        self.assertEqual(self.patients_seen_by(self.secretary.user), set())

    def test_secretary_sees_appointments_and_doctors_of_assigned_doctors_only(self):
        SecretaryDoctorAssignment.objects.create(secretary=self.secretary, doctor=self.doctor_a)
        when = timezone.now() + timedelta(days=1)
        create_appointment(self.doctor_a, self.patient_a, when)
        create_appointment(self.doctor_b, self.patient_b, when + timedelta(hours=2))
        self.client.force_authenticate(self.secretary.user)

        appointments = self.client.get("/api/v1/appointments")
        self.assertEqual({item["patient"] for item in appointments.data}, {self.patient_a.id})
        doctors = self.client.get("/api/v1/doctors")
        self.assertEqual([item["id"] for item in doctors.data], [self.doctor_a.id])


class AdminUsersScopeTests(OrganizationScopeBase):
    def setUp(self):
        super().setUp()
        self.admin_user = create_user("orgadmin-a@test.local", roles=["ORG_ADMIN"])
        OrganizationAdminProfile.objects.create(
            user=self.admin_user, organization=self.org_a, full_name="Admin A", country=self.hn, status="active"
        )

    def test_org_admin_lists_only_users_of_his_organization(self):
        self.client.force_authenticate(self.admin_user)
        response = self.client.get("/api/v1/admin/users")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        usernames = {item["username"] for item in response.data}
        self.assertEqual(usernames, {"doc-a@test.local", "orgadmin-a@test.local"})

    def test_org_admin_cannot_write_users_or_reset_passwords(self):
        self.client.force_authenticate(self.admin_user)
        create = self.client.post(
            "/api/v1/admin/users",
            {"username": "n@test.local", "email": "n@test.local", "password": "Nueva-Clave-2026", "roles": ["ADMIN"]},
            format="json",
        )
        self.assertEqual(create.status_code, status.HTTP_403_FORBIDDEN)
        reset = self.client.post(f"/api/v1/admin/users/{self.doctor_a.user_id}/reset-password", {}, format="json")
        self.assertEqual(reset.status_code, status.HTTP_403_FORBIDDEN)
        delete = self.client.delete(f"/api/v1/admin/users/{self.doctor_a.user_id}")
        self.assertEqual(delete.status_code, status.HTTP_403_FORBIDDEN)

    def test_pending_org_admin_has_no_access(self):
        OrganizationAdminProfile.objects.filter(user=self.admin_user).update(status="pending")
        # Usuario recargado, como en una peticion real (evita el perfil cacheado en la instancia).
        self.client.force_authenticate(type(self.admin_user).objects.get(pk=self.admin_user.pk))
        self.assertEqual(self.client.get("/api/v1/admin/users").status_code, status.HTTP_403_FORBIDDEN)

    def test_country_admin_manages_interactive_core_staff_but_not_external_accounts(self):
        country_admin = create_user("admin-hn@test.local", roles=["ADMIN_HN"])
        with mock.patch("api.permissions.admin_permissions.user_is_interactive_core_admin", return_value=True):
            self.client.force_authenticate(country_admin)
            response = self.client.get("/api/v1/admin/users")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        usernames = {item["username"] for item in response.data}
        self.assertIn(self.ic_doctor.user.username, usernames)
        self.assertNotIn("doc-a@test.local", usernames)
        self.assertNotIn("orgadmin-a@test.local", usernames)

    def test_global_admin_sees_all_users(self):
        root = create_user("root@test.local", roles=["ADMIN"])
        with mock.patch("api.permissions.admin_permissions.user_is_interactive_core_admin", return_value=True):
            self.client.force_authenticate(root)
            response = self.client.get("/api/v1/admin/users")
        usernames = {item["username"] for item in response.data}
        self.assertTrue({"doc-a@test.local", "doc-b@test.local", "orgadmin-a@test.local"} <= usernames)


class ExternalAccountSecurityTests(OrganizationScopeBase):
    def test_external_account_with_an_interactive_core_admin_email_gets_no_roles(self):
        victim_email = "admin-ic@test.local"
        attacker = create_user(victim_email, roles=["DOCTOR"])
        create_doctor(
            user=attacker, interactive_core_doctor_id=None, organization=self.org_a, **EXTERNAL,
        )
        workspace = {"role_code": "ADMIN", "is_admin": True, "country": None}
        with mock.patch.object(InteractiveCoreAccessService, "get_user_workspaces", return_value=[workspace]):
            result = InteractiveCoreAccessService().sync_user_workspaces(attacker)
        self.assertEqual(result, [])
        self.assertFalse(attacker.groups.filter(name="ADMIN").exists())

    def test_external_account_is_never_an_interactive_core_admin(self):
        user = create_user("admin-ic2@test.local", roles=["DOCTOR"])
        create_doctor(user=user, interactive_core_doctor_id=None, organization=self.org_a, **EXTERNAL)
        with mock.patch.object(InteractiveCoreAccessService, "has_admin_role", return_value=True) as has_admin:
            self.assertFalse(user_is_interactive_core_admin(user))
        has_admin.assert_not_called()

    def test_interactive_core_activation_cannot_take_over_an_external_account(self):
        user = create_user("shared@test.local", roles=["DOCTOR"])
        create_doctor(user=user, interactive_core_doctor_id=None, organization=self.org_a, **EXTERNAL)
        with self.assertRaises(serializers.ValidationError):
            AccessActivationService().activate_doctor(
                {"id": 4242, "full_name": "Otro", "country": {"code": "HN"}}, "shared@test.local", "Nueva-Clave-2026"
            )
        user.refresh_from_db()
        self.assertTrue(user.check_password("Doctor1234!"))

    def test_external_doctor_without_interactive_core_id_can_load_auth_me(self):
        self.client.force_authenticate(self.doctor_a.user)
        response = self.client.get("/api/v1/auth/me")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(response.data["is_external"])
        self.assertEqual(response.data["organization"]["name"], "Clinica A")

    def test_interactive_core_user_is_not_marked_external(self):
        self.client.force_authenticate(self.ic_doctor.user)
        with mock.patch("api.views.doctor_views.InteractiveCoreDoctorService.sync_portal_profile_context"):
            response = self.client.get("/api/v1/auth/me")
        self.assertFalse(response.data["is_external"])
        self.assertTrue(response.data["organization"]["is_interactive_core"])


class LoginBlockTests(OrganizationScopeBase):
    def login(self, email, password="Doctor1234!"):
        return APIClient(HTTP_HOST="localhost").post(
            "/api/v1/auth/login", {"email": email, "password": password}, format="json"
        )

    def test_pending_org_admin_cannot_log_in_until_approved(self):
        user = create_user("pending@test.local", roles=["ORG_ADMIN"])
        profile = OrganizationAdminProfile.objects.create(
            user=user, organization=self.org_a, full_name="P", country=self.hn, status="pending"
        )
        response = self.login("pending@test.local")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("pendiente", str(response.data))
        profile.status = "active"
        profile.save()
        self.assertEqual(self.login("pending@test.local").status_code, status.HTTP_200_OK)

    def test_members_of_a_suspended_organization_cannot_log_in(self):
        self.assertEqual(self.login("doc-a@test.local").status_code, status.HTTP_200_OK)
        self.org_a.status = "suspended"
        self.org_a.save()
        response = self.login("doc-a@test.local")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("suspendida", str(response.data))


class PatientOwnHistoryTests(OrganizationScopeBase):
    def setUp(self):
        super().setUp()
        self.patient_a.dni = "0801-1990-12345"
        self.patient_a.commercial_notes = "NOTA INTERNA"
        self.patient_a.email = "ficha@test.local"
        self.patient_a.save()
        user = create_user("paciente@test.local", roles=["PATIENT"])
        self.profile = PatientPortalProfile.objects.create(
            user=user, organization=self.org_a, full_name="Paciente", country=self.hn,
            document_type="DNI", document_number="0801199012345",
        )
        self.client.force_authenticate(user)

    def test_history_requires_verification(self):
        response = self.client.get("/api/v1/patient/me/history")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_verified_patient_sees_only_whitelisted_fields_of_his_own_records(self):
        create_appointment(self.doctor_a, self.patient_a, timezone.now() + timedelta(days=1), reason="Control")
        create_appointment(self.doctor_b, self.patient_b, timezone.now() + timedelta(days=2), reason="Ajeno")
        self.profile.history_verified_at = timezone.now()
        self.profile.save()

        response = self.client.get("/api/v1/patient/me/history")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual([record["last_name"] for record in response.data["records"]], ["DeA"])
        self.assertEqual([item["reason"] for item in response.data["appointments"]], ["Control"])
        body = str(response.data)
        self.assertNotIn("NOTA INTERNA", body)
        self.assertNotIn("ficha@test.local", body)

    def test_patient_account_has_no_access_to_clinical_endpoints(self):
        self.profile.history_verified_at = timezone.now()
        self.profile.save()
        self.assertEqual(self.client.get("/api/v1/patients").data, [])
        self.assertEqual(self.client.get("/api/v1/appointments").data, [])
        self.assertEqual(self.client.get("/api/v1/doctors").data, [])
        self.assertEqual(self.client.get("/api/v1/search", {"q": "DeA"}).data["patients"], [])
