from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from api.models import (
    Country,
    CountryDivision,
    Organization,
    OrganizationAdminProfile,
    OrganizationInvitation,
    SecretaryDoctorAssignment,
    SpecialtyCatalogMirror,
    TermsVersion,
)
from api.test_factories import create_doctor, create_secretary, create_user

EXTERNAL = {"origin": "self_registered"}
ADMIN_PERMISSION = "api.permissions.admin_permissions.user_is_interactive_core_admin"


class AdminApiBase(TestCase):
    def setUp(self):
        cache.clear()
        patcher = mock.patch(ADMIN_PERMISSION, return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.hn = Country.objects.get(code="HN")
        self.gt = Country.objects.get(code="GT")
        self.org_a = Organization.objects.create(name="Clinica A", country=self.hn)
        self.org_b = Organization.objects.create(name="Clinica B", country=self.hn)
        self.ic_org = Organization.objects.get(country=self.hn, is_interactive_core=True)
        self.root = create_user("root@test.local", roles=["ADMIN"])
        self.admin_a = self.make_org_admin("admin-a@test.local", self.org_a)
        self.admin_b = self.make_org_admin("admin-b@test.local", self.org_b)

    def make_org_admin(self, username, organization, status_value="active"):
        user = create_user(username, roles=["ORG_ADMIN"])
        OrganizationAdminProfile.objects.create(
            user=user, organization=organization, full_name=username, email=username, country=organization.country,
            status=status_value,
        )
        return user

    def client_for(self, user):
        client = APIClient(HTTP_HOST="localhost")
        client.force_authenticate(type(user).objects.get(pk=user.pk))
        return client

    def external_doctor(self, organization, username):
        return create_doctor(
            user=create_user(username, roles=["DOCTOR"]), interactive_core_doctor_id=None,
            organization=organization, full_name=username, **EXTERNAL,
        )


class OrganizationFormTests(AdminApiBase):
    def setUp(self):
        super().setUp()
        self.division = CountryDivision.objects.get(country=self.hn, name="Cortés")
        self.specialty = SpecialtyCatalogMirror.objects.create(
            interactive_core_id=700, country=self.hn, name="Pediatria"
        )
        self.second_specialty = SpecialtyCatalogMirror.objects.create(
            interactive_core_id=702, country=self.hn, name="Cardiologia"
        )

    def payload(self, **extra):
        data = {
            "name": "Hospital Nuevo",
            "country": self.hn.id,
            "division": self.division.id,
            "medical_areas": [self.specialty.id, self.second_specialty.id],
        }
        data.update(extra)
        return data

    def test_global_admin_creates_organization_with_multiple_medical_areas(self):
        response = self.client_for(self.root).post("/api/v1/admin/organizations", self.payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["division_name"], "Cortés")
        self.assertEqual(response.data["division_type"], "Departamento")
        self.assertEqual(response.data["medical_areas"], [self.second_specialty.id, self.specialty.id])
        self.assertEqual(response.data["medical_area_names"], ["Cardiologia", "Pediatria"])
        self.assertFalse(response.data["is_interactive_core"])

    def test_division_and_medical_area_must_belong_to_the_country(self):
        client = self.client_for(self.root)
        gt_division = CountryDivision.objects.filter(country=self.gt).first()
        bad_division = client.post("/api/v1/admin/organizations", self.payload(division=gt_division.id), format="json")
        self.assertEqual(bad_division.status_code, 400)
        self.assertIn("division", bad_division.data)
        gt_specialty = SpecialtyCatalogMirror.objects.create(interactive_core_id=701, country=self.gt, name="Pediatria")
        bad_area = client.post(
            "/api/v1/admin/organizations",
            self.payload(medical_areas=[self.specialty.id, gt_specialty.id]),
            format="json",
        )
        self.assertEqual(bad_area.status_code, 400)
        self.assertIn("medical_areas", bad_area.data)

    def test_medical_areas_can_be_replaced_and_cleared(self):
        client = self.client_for(self.root)
        created = client.post("/api/v1/admin/organizations", self.payload(), format="json")
        organization_id = created.data["id"]

        replaced = client.patch(
            f"/api/v1/admin/organizations/{organization_id}",
            {"medical_areas": [self.specialty.id]},
            format="json",
        )
        self.assertEqual(replaced.status_code, 200, replaced.data)
        self.assertEqual(replaced.data["medical_area_names"], ["Pediatria"])

        cleared = client.patch(
            f"/api/v1/admin/organizations/{organization_id}",
            {"medical_areas": []},
            format="json",
        )
        self.assertEqual(cleared.status_code, 200, cleared.data)
        self.assertEqual(cleared.data["medical_areas"], [])
        self.assertEqual(cleared.data["medical_area_names"], [])

    def test_duplicate_name_in_the_same_country_is_rejected_but_not_in_another(self):
        client = self.client_for(self.root)
        self.assertEqual(client.post("/api/v1/admin/organizations", self.payload(), format="json").status_code, 201)
        duplicate = client.post("/api/v1/admin/organizations", self.payload(name="hospital nuevo"), format="json")
        self.assertEqual(duplicate.status_code, 400)
        other_country = client.post(
            "/api/v1/admin/organizations", {"name": "Hospital Nuevo", "country": self.gt.id}, format="json"
        )
        self.assertEqual(other_country.status_code, 201, other_country.data)

    def test_country_cannot_change_and_interactive_core_cannot_be_suspended(self):
        client = self.client_for(self.root)
        change = client.patch(f"/api/v1/admin/organizations/{self.org_a.id}", {"country": self.gt.id}, format="json")
        self.assertEqual(change.status_code, 400)
        suspend_ic = client.patch(f"/api/v1/admin/organizations/{self.ic_org.id}", {"status": "suspended"}, format="json")
        self.assertEqual(suspend_ic.status_code, 400)
        suspend = client.patch(f"/api/v1/admin/organizations/{self.org_a.id}", {"status": "suspended"}, format="json")
        self.assertEqual(suspend.status_code, 200)

    def test_only_global_admin_writes_organizations(self):
        body = self.payload()
        self.assertEqual(self.client_for(self.admin_a).post("/api/v1/admin/organizations", body, format="json").status_code, 403)
        country_admin = create_user("admin-hn@test.local", roles=["ADMIN_HN"])
        self.assertEqual(self.client_for(country_admin).post("/api/v1/admin/organizations", body, format="json").status_code, 403)
        patch = self.client_for(self.admin_a).patch(f"/api/v1/admin/organizations/{self.org_a.id}", {"name": "X"}, format="json")
        self.assertEqual(patch.status_code, 403)

    def test_org_admin_only_sees_his_own_organization(self):
        response = self.client_for(self.admin_a).get("/api/v1/admin/organizations")
        self.assertEqual([item["id"] for item in response.data], [self.org_a.id])
        self.assertEqual(
            self.client_for(self.admin_a).get(f"/api/v1/admin/organizations/{self.org_b.id}").status_code, 404
        )

    def test_pending_org_admin_cannot_use_the_api(self):
        pending = self.make_org_admin("pending@test.local", self.org_a, status_value="pending")
        self.assertEqual(self.client_for(pending).get("/api/v1/admin/organizations").status_code, 403)

    def test_list_filters_by_country_and_search(self):
        client = self.client_for(self.root)
        by_country = client.get("/api/v1/admin/organizations", {"country": "HN", "search": "Clinica"})
        self.assertEqual({item["name"] for item in by_country.data}, {"Clinica A", "Clinica B"})


class InvitationApiTests(AdminApiBase):
    def create_invitation(self, user, organization, role="DOCTOR", **extra):
        return self.client_for(user).post(
            f"/api/v1/admin/organizations/{organization.id}/invitations", {"role": role, **extra}, format="json"
        )

    def test_org_admin_creates_an_invitation_with_a_generated_code(self):
        response = self.create_invitation(self.admin_a, self.org_a, max_uses=5)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertRegex(response.data["code"], r"^[A-Z2-9]{5}-[A-Z2-9]{5}$")
        self.assertEqual(response.data["uses"], 0)
        self.assertEqual(OrganizationInvitation.objects.get().created_by, self.admin_a)

    def test_org_admin_cannot_invite_admins_nor_use_another_organization(self):
        self.assertEqual(self.create_invitation(self.admin_a, self.org_a, role="ORG_ADMIN").status_code, 400)
        self.assertEqual(self.create_invitation(self.admin_a, self.org_b).status_code, 404)
        self.assertEqual(self.create_invitation(self.root, self.org_a, role="ORG_ADMIN").status_code, 201)

    def test_suspended_organization_cannot_issue_invitations(self):
        Organization.objects.filter(pk=self.org_a.pk).update(status="suspended")
        self.assertEqual(self.create_invitation(self.root, self.org_a).status_code, 400)

    def test_listing_is_scoped_and_revoking_keeps_the_record(self):
        mine = self.create_invitation(self.admin_a, self.org_a).data
        theirs = self.create_invitation(self.admin_b, self.org_b).data
        listing = self.client_for(self.admin_a).get(f"/api/v1/admin/organizations/{self.org_a.id}/invitations")
        self.assertEqual([item["id"] for item in listing.data], [mine["id"]])
        self.assertEqual(self.client_for(self.admin_a).delete(f"/api/v1/admin/invitations/{theirs['id']}").status_code, 404)

        self.assertEqual(self.client_for(self.admin_a).delete(f"/api/v1/admin/invitations/{mine['id']}").status_code, 204)
        invitation = OrganizationInvitation.objects.get(pk=mine["id"])
        self.assertFalse(invitation.is_active)
        validate = APIClient().post("/api/v1/auth/invitation/validate", {"invitation_code": invitation.code}, format="json")
        self.assertEqual(validate.status_code, 400)

    def test_invalid_limits_are_rejected(self):
        self.assertEqual(self.create_invitation(self.admin_a, self.org_a, max_uses=0).status_code, 400)
        past = (timezone.now() - timedelta(days=1)).isoformat()
        self.assertEqual(self.create_invitation(self.admin_a, self.org_a, expires_at=past).status_code, 400)
        created = self.create_invitation(self.admin_a, self.org_a, max_uses=3).data
        OrganizationInvitation.objects.filter(pk=created["id"]).update(uses=2)
        lower = self.client_for(self.admin_a).patch(f"/api/v1/admin/invitations/{created['id']}", {"max_uses": 1}, format="json")
        self.assertEqual(lower.status_code, 400)
        role = self.client_for(self.admin_a).patch(f"/api/v1/admin/invitations/{created['id']}", {"role": "NURSE"}, format="json")
        self.assertEqual(role.status_code, 400)

    def test_end_to_end_invitation_registration_and_member_listing(self):
        TermsVersion.objects.create(version="1.0", content="t", is_current=True)
        code = self.create_invitation(self.admin_a, self.org_a, max_uses=1).data["code"]
        registration = APIClient().post(
            "/api/v1/auth/register",
            {
                "role": "DOCTOR", "invitation_code": code, "full_name": "Dra Nueva", "email": "nueva@test.local",
                "password": "Clave-Segura-2026", "password_confirm": "Clave-Segura-2026", "country": "HN",
                "accept_terms": True, "colegiation_code": "C-1",
            },
            format="json",
        )
        self.assertEqual(registration.status_code, 201, registration.data)
        members = self.client_for(self.admin_a).get("/api/v1/admin/members", {"role": "DOCTOR"})
        self.assertEqual([m["email"] for m in members.data], ["nueva@test.local"])
        self.assertTrue(members.data[0]["is_external"])
        self.assertEqual(self.client_for(self.admin_b).get("/api/v1/admin/members", {"role": "DOCTOR"}).data, [])


class MemberManagementTests(AdminApiBase):
    def setUp(self):
        super().setUp()
        self.doctor_a = self.external_doctor(self.org_a, "doc-a@test.local")
        self.doctor_b = self.external_doctor(self.org_b, "doc-b@test.local")

    def test_org_admin_lists_only_his_members(self):
        response = self.client_for(self.admin_a).get("/api/v1/admin/members")
        self.assertEqual({m["email"] for m in response.data}, {"doc-a@test.local", "admin-a@test.local"})
        doctor_row = next(m for m in response.data if m["email"] == "doc-a@test.local")
        self.assertEqual(doctor_row["profile_id"], self.doctor_a.id)
        forbidden = self.client_for(self.admin_a).get("/api/v1/admin/members", {"organization": self.org_b.id})
        self.assertEqual(forbidden.status_code, 403)

    def test_global_admin_can_filter_by_organization(self):
        response = self.client_for(self.root).get("/api/v1/admin/members", {"organization": self.org_b.id})
        self.assertEqual({m["email"] for m in response.data}, {"doc-b@test.local", "admin-b@test.local"})

    def test_deactivating_a_member_blocks_login_and_reactivating_restores_it(self):
        client = self.client_for(self.admin_a)
        off = client.patch(f"/api/v1/admin/members/{self.doctor_a.user_id}", {"is_active": False}, format="json")
        self.assertEqual(off.status_code, 200, off.data)
        self.assertFalse(off.data["is_active"])
        self.doctor_a.refresh_from_db()
        self.assertEqual(self.doctor_a.status, "inactive")
        login = APIClient().post("/api/v1/auth/login", {"email": "doc-a@test.local", "password": "Doctor1234!"}, format="json")
        self.assertIn(login.status_code, (400, 401))

        on = client.patch(f"/api/v1/admin/members/{self.doctor_a.user_id}", {"is_active": True}, format="json")
        self.assertTrue(on.data["is_active"])
        login = APIClient().post("/api/v1/auth/login", {"email": "doc-a@test.local", "password": "Doctor1234!"}, format="json")
        self.assertEqual(login.status_code, 200)

    def test_org_admin_cannot_touch_other_organizations_self_or_other_admins(self):
        client = self.client_for(self.admin_a)
        self.assertEqual(client.patch(f"/api/v1/admin/members/{self.doctor_b.user_id}", {"is_active": False}, format="json").status_code, 404)
        self.assertEqual(client.patch(f"/api/v1/admin/members/{self.admin_a.id}", {"is_active": False}, format="json").status_code, 403)
        second_admin = self.make_org_admin("admin-a2@test.local", self.org_a)
        self.assertEqual(client.patch(f"/api/v1/admin/members/{second_admin.id}", {"is_active": False}, format="json").status_code, 403)
        self.assertEqual(
            self.client_for(self.root).patch(f"/api/v1/admin/members/{second_admin.id}", {"is_active": False}, format="json").status_code,
            200,
        )

    def test_reactivating_a_pending_org_admin_does_not_bypass_approval(self):
        pending = self.make_org_admin("pending@test.local", self.org_a, status_value="pending")
        pending.is_active = False
        pending.save()
        response = self.client_for(self.root).patch(f"/api/v1/admin/members/{pending.id}", {"is_active": True}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(OrganizationAdminProfile.objects.get(user=pending).status, "pending")

    def test_regular_users_cannot_use_member_endpoints(self):
        self.assertEqual(self.client_for(self.doctor_a.user).get("/api/v1/admin/members").status_code, 403)


class OrgAdminApprovalTests(AdminApiBase):
    def setUp(self):
        super().setUp()
        self.pending = self.make_org_admin("pending@test.local", self.org_a, status_value="pending")
        self.profile = OrganizationAdminProfile.objects.get(user=self.pending)

    def login(self):
        return APIClient().post("/api/v1/auth/login", {"email": "pending@test.local", "password": "Doctor1234!"}, format="json")

    def test_global_admin_lists_pending_requests(self):
        response = self.client_for(self.root).get("/api/v1/admin/org-admins", {"status": "pending"})
        self.assertEqual([item["id"] for item in response.data], [self.profile.id])
        self.assertEqual(response.data[0]["organization_name"], "Clinica A")

    def test_approval_activates_notifies_and_allows_login(self):
        self.assertEqual(self.login().status_code, 400)
        mail.outbox.clear()
        response = self.client_for(self.root).post(f"/api/v1/admin/org-admins/{self.profile.id}/approve")
        self.assertEqual(response.status_code, 200, response.data)
        self.profile.refresh_from_db()
        self.assertEqual((self.profile.status, self.profile.approved_by), ("active", self.root))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["pending@test.local"])
        self.assertEqual(self.login().status_code, 200)

    def test_rejection_deactivates_and_a_later_approval_reactivates(self):
        client = self.client_for(self.root)
        self.assertEqual(client.post(f"/api/v1/admin/org-admins/{self.profile.id}/reject").status_code, 200)
        self.pending.refresh_from_db()
        self.assertFalse(self.pending.is_active)
        self.assertIn(self.login().status_code, (400, 401))
        client.post(f"/api/v1/admin/org-admins/{self.profile.id}/approve")
        self.pending.refresh_from_db()
        self.assertTrue(self.pending.is_active)
        self.assertEqual(self.login().status_code, 200)

    def test_mail_failure_does_not_undo_the_approval(self):
        with mock.patch("api.services.organization_admin_service.send_mail", side_effect=OSError("smtp caido")):
            response = self.client_for(self.root).post(f"/api/v1/admin/org-admins/{self.profile.id}/approve")
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.status, "active")

    def test_cannot_approve_for_a_suspended_organization(self):
        Organization.objects.filter(pk=self.org_a.pk).update(status="suspended")
        response = self.client_for(self.root).post(f"/api/v1/admin/org-admins/{self.profile.id}/approve")
        self.assertEqual(response.status_code, 400)

    def test_only_global_admin_decides(self):
        for user in (self.admin_a, create_user("admin-hn@test.local", roles=["ADMIN_HN"])):
            client = self.client_for(user)
            self.assertEqual(client.get("/api/v1/admin/org-admins").status_code, 403)
            self.assertEqual(client.post(f"/api/v1/admin/org-admins/{self.profile.id}/approve").status_code, 403)


class SecretaryAssignmentApiTests(AdminApiBase):
    def setUp(self):
        super().setUp()
        self.doctor_a = self.external_doctor(self.org_a, "doc-a@test.local")
        self.doctor_b = self.external_doctor(self.org_b, "doc-b@test.local")
        self.secretary_a = create_secretary(
            secretaria_interactivecore_id=None, organization=self.org_a,
            user=create_user("sec-a@test.local", roles=["SECRETARY"]), **EXTERNAL,
        )

    def assign(self, user, secretary, doctor):
        return self.client_for(user).post(
            "/api/v1/admin/secretary-assignments", {"secretary": secretary.id, "doctor": doctor.id}, format="json"
        )

    def test_org_admin_links_and_unlinks_within_the_organization(self):
        response = self.assign(self.admin_a, self.secretary_a, self.doctor_a)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["doctor_name"], "doc-a@test.local")
        self.assertEqual(SecretaryDoctorAssignment.objects.get().created_by, self.admin_a)
        listing = self.client_for(self.admin_a).get("/api/v1/admin/secretary-assignments")
        self.assertEqual(len(listing.data), 1)
        self.assertEqual(self.client_for(self.admin_b).get("/api/v1/admin/secretary-assignments").data, [])
        delete = self.client_for(self.admin_a).delete(f"/api/v1/admin/secretary-assignments/{response.data['id']}")
        self.assertEqual(delete.status_code, 204)
        self.assertFalse(SecretaryDoctorAssignment.objects.exists())

    def test_cross_organization_duplicate_and_foreign_links_are_rejected(self):
        self.assertEqual(self.assign(self.admin_a, self.secretary_a, self.doctor_b).status_code, 400)
        self.assertEqual(self.assign(self.admin_b, self.secretary_a, self.doctor_a).status_code, 400)
        self.assertEqual(self.assign(self.admin_a, self.secretary_a, self.doctor_a).status_code, 201)
        self.assertEqual(self.assign(self.admin_a, self.secretary_a, self.doctor_a).status_code, 400)

    def test_other_organization_cannot_delete_a_link(self):
        created = self.assign(self.admin_a, self.secretary_a, self.doctor_a)
        delete = self.client_for(self.admin_b).delete(f"/api/v1/admin/secretary-assignments/{created.data['id']}")
        self.assertEqual(delete.status_code, 404)

    def test_global_admin_can_manage_any_organization(self):
        self.assertEqual(self.assign(self.root, self.secretary_a, self.doctor_a).status_code, 201)


class TermsAndPublicCatalogTests(AdminApiBase):
    def test_publishing_a_version_makes_it_the_only_current_one(self):
        client = self.client_for(self.root)
        first = client.post("/api/v1/admin/terms", {"version": "1.0", "content": "Texto uno"}, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        second = client.post("/api/v1/admin/terms", {"version": "2.0", "title": "TyC", "content": "Texto dos"}, format="json")
        self.assertEqual(second.status_code, 201)
        self.assertEqual(list(TermsVersion.objects.filter(is_current=True).values_list("version", flat=True)), ["2.0"])
        self.assertEqual(TermsVersion.objects.count(), 2)
        duplicate = client.post("/api/v1/admin/terms", {"version": "2.0", "content": "x"}, format="json")
        self.assertEqual(duplicate.status_code, 400)

    def test_activating_an_older_version_swaps_the_current_one(self):
        client = self.client_for(self.root)
        old = TermsVersion.objects.create(version="1.0", content="a")
        new = TermsVersion.objects.create(version="2.0", content="b", is_current=True)
        response = client.post(f"/api/v1/admin/terms/{old.id}/activate")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["is_current"])
        self.assertEqual(list(TermsVersion.objects.filter(is_current=True).values_list("pk", flat=True)), [old.pk])
        new.refresh_from_db()
        self.assertFalse(new.is_current)
        self.assertEqual(client.post(f"/api/v1/admin/terms/{old.id}/activate").status_code, 200)

    def test_only_global_admin_activates_terms(self):
        terms = TermsVersion.objects.create(version="1.0", content="a")
        response = self.client_for(self.admin_a).post(f"/api/v1/admin/terms/{terms.id}/activate")
        self.assertEqual(response.status_code, 403)

    def test_terms_list_includes_content_and_acceptance_count(self):
        TermsVersion.objects.create(version="1.0", content="Texto", is_current=True)
        response = self.client_for(self.root).get("/api/v1/admin/terms")
        rows = response.data if isinstance(response.data, list) else response.data["results"]
        self.assertEqual(rows[0]["content"], "Texto")
        self.assertEqual(rows[0]["acceptances_count"], 0)

    def test_only_global_admin_publishes_terms(self):
        response = self.client_for(self.admin_a).post("/api/v1/admin/terms", {"version": "1.0", "content": "x"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_public_terms_endpoint(self):
        anonymous = APIClient()
        self.assertEqual(anonymous.get("/api/v1/auth/terms/current").status_code, 404)
        TermsVersion.objects.create(version="1.0", title="TyC", content="Texto", is_current=True)
        response = anonymous.get("/api/v1/auth/terms/current")
        self.assertEqual(response.data, {"version": "1.0", "title": "TyC", "content": "Texto"})

    def test_public_catalogs_depend_on_the_selected_country(self):
        SpecialtyCatalogMirror.objects.create(interactive_core_id=1, country=self.hn, name="Cardiologia")
        SpecialtyCatalogMirror.objects.create(interactive_core_id=2, country=self.gt, name="Neurologia")
        SpecialtyCatalogMirror.objects.create(interactive_core_id=3, country=self.hn, name="Inactiva", is_active=False)
        anonymous = APIClient()
        hn = anonymous.get("/api/v1/auth/catalog/specialties", {"country": "HN"})
        self.assertEqual([item["name"] for item in hn.data], ["Cardiologia"])
        divisions = anonymous.get("/api/v1/auth/catalog/divisions", {"country": "cr"})
        self.assertEqual(len(divisions.data), 7)
        self.assertEqual({item["division_type"] for item in divisions.data}, {"Provincia"})
        self.assertEqual(anonymous.get("/api/v1/auth/catalog/divisions").status_code, 400)
        self.assertEqual(anonymous.get("/api/v1/auth/catalog/divisions", {"country": "ZZ"}).status_code, 400)
