from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from api.models import (
    AffiliationRequest,
    DoctorPortalProfile,
    NursePortalProfile,
    Organization,
    OrganizationAdminProfile,
    SecretaryPortalProfile,
    TermsAcceptance,
    TermsVersion,
)
from api.services.interactive_core import InteractiveCoreAccessService, InteractiveCoreDoctorService
from api.test_factories import create_secretary, create_user

ADMIN_PERMISSION = "api.permissions.admin_permissions.user_is_interactive_core_admin"
PASSWORD = "Clave-Segura-2026"


def secretary_record(**overrides):
    record = {
        "id": 55,
        "full_name": "Secretaria Interactive",
        "email": "secretaria-ic@test.local",
        "phone": "99990000",
        "dni": "0801199900123",
        "country_id": 3,
        "country": "Honduras",
        "prescript_roles": ["SECRETARY"],
        "prescript_role": "SECRETARY",
        "has_prescript_access": True,
    }
    record.update(overrides)
    return record


def nurse_record(**overrides):
    record = {
        "id": 70,
        "interactive_core_user_id": 70,
        "interactive_core_employee_id": 170,
        "full_name": "Enfermera Interactive",
        "email": "enfermera-ic@test.local",
        "phone": "99991111",
        "dni": "0801199800456",
        "country_id": 3,
        "country": "Honduras",
        "prescript_roles": ["NURSE"],
        "prescript_role": "NURSE",
        "has_prescript_access": True,
    }
    record.update(overrides)
    return record


class StaffAffiliationBase(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.terms = TermsVersion.objects.create(version="1.0", content="texto", is_current=True)
        self.secretary = secretary_record()
        self.nurse = nurse_record()
        self.doctor_records = {}
        for target, attribute, key in (
            ("get_secretary", "secretary", 55),
            ("get_nurse", "nurse", 70),
        ):
            patcher = mock.patch.object(
                InteractiveCoreAccessService,
                target,
                side_effect=lambda profile_id, attribute=attribute, key=key: (
                    getattr(self, attribute) if profile_id == key else None
                ),
            )
            patcher.start()
            self.addCleanup(patcher.stop)
        doctor_patcher = mock.patch.object(
            InteractiveCoreDoctorService,
            "get_doctor_for_activation",
            side_effect=lambda profile_id: self.doctor_records.get(profile_id),
        )
        doctor_patcher.start()
        self.addCleanup(doctor_patcher.stop)
        mail.outbox.clear()

    def request_code(self, role, profile_id, email=None):
        body = {"role": role, "profile_id": profile_id, **({"email": email} if email else {})}
        return self.client.post("/api/v1/auth/affiliation/request-code", body, format="json")

    def sent_code(self):
        return next(t for t in mail.outbox[-1].body.split() if t.rstrip(".").isdigit()).rstrip(".")

    def activate(self, role, profile_id, code, **extra):
        body = {
            "role": role,
            "profile_id": profile_id,
            "code": code,
            "password": PASSWORD,
            "password_confirm": PASSWORD,
            "accept_terms": True,
            **extra,
        }
        return self.client.post("/api/v1/auth/affiliation/activate", body, format="json")

    def login(self, email, password=PASSWORD):
        return APIClient().post("/api/v1/auth/login", {"email": email, "password": password}, format="json")


class StaffSearchTests(StaffAffiliationBase):
    def test_search_uses_the_catalog_of_the_requested_role(self):
        secretaries = [
            {"id": 55, "full_name": "Secretaria Interactive", "identifier": "0801199900123", "country_code": "HN", "has_email": True}
        ]
        with mock.patch.object(InteractiveCoreAccessService, "search_secretaries", return_value=secretaries) as search:
            response = self.client.get("/api/v1/auth/affiliation/search", {"q": "Secre", "role": "SECRETARY"})
        search.assert_called_once_with("Secre")
        self.assertEqual(
            response.data,
            [
                {
                    "id": 55,
                    "full_name": "Secretaria Interactive",
                    "country_code": "HN",
                    "identifier_label": "Documento",
                    "identifier_hint": "***123",
                    "has_email": True,
                }
            ],
        )
        # Nunca se devuelve el documento completo ni el correo.
        self.assertNotIn("0801199900123", str(response.data))

    def test_nurses_are_searched_in_their_own_catalog(self):
        with mock.patch.object(InteractiveCoreAccessService, "search_nurses", return_value=[]) as nurses, mock.patch.object(
            InteractiveCoreAccessService, "search_secretaries"
        ) as secretaries:
            response = self.client.get("/api/v1/auth/affiliation/search", {"q": "Enfe", "role": "nurse"})
        self.assertEqual(response.status_code, 200)
        nurses.assert_called_once_with("Enfe")
        secretaries.assert_not_called()

    def test_unknown_role_is_rejected(self):
        response = self.client.get("/api/v1/auth/affiliation/search", {"q": "Alguien", "role": "ADMIN"})
        self.assertEqual(response.status_code, 400)


class StaffVerifiedActivationTests(StaffAffiliationBase):
    def test_secretary_with_email_on_record_activates_with_a_code_sent_there(self):
        self.assertEqual(self.request_code("SECRETARY", 55).status_code, 200)
        self.assertEqual(mail.outbox[0].to, ["secretaria-ic@test.local"])

        response = self.activate("SECRETARY", 55, self.sent_code())
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIn("access", response.data)
        self.assertEqual(response.data["mode"], "verified")

        profile = SecretaryPortalProfile.objects.get(secretaria_interactivecore_id=55)
        self.assertEqual(profile.user.email, "secretaria-ic@test.local")
        self.assertEqual(profile.origin, "interactive_core")
        self.assertEqual(profile.organization, Organization.objects.get(country__code="HN", is_interactive_core=True))
        self.assertTrue(profile.user.groups.filter(name="SECRETARY").exists())
        self.assertTrue(TermsAcceptance.objects.filter(user=profile.user, terms=self.terms).exists())
        self.assertEqual(self.login("secretaria-ic@test.local").status_code, 200)

    def test_nurse_with_email_on_record_activates_with_a_code_sent_there(self):
        self.assertEqual(self.request_code("NURSE", 70).status_code, 200)
        response = self.activate("NURSE", 70, self.sent_code())
        self.assertEqual(response.status_code, 201, response.data)
        profile = NursePortalProfile.objects.get(interactive_core_user_id=70)
        self.assertEqual(profile.interactive_core_employee_id, 170)
        self.assertEqual(profile.user.email, "enfermera-ic@test.local")
        self.assertTrue(profile.user.groups.filter(name="NURSE").exists())

    def test_unknown_record_never_receives_mail(self):
        self.assertEqual(self.request_code("SECRETARY", 999).status_code, 400)
        self.assertEqual(self.request_code("NURSE", 999).status_code, 400)
        self.assertEqual(len(mail.outbox), 0)

    def test_a_code_is_only_valid_for_the_role_it_was_requested_for(self):
        # Mismo id en dos catalogos distintos: el codigo de la secretaria 55 no sirve para el doctor 55.
        self.doctor_records[55] = {
            "id": 55,
            "full_name": "Doctor 55",
            "email": "doctor55@test.local",
            "status": "active",
            "has_doctor_role": True,
            "country": {"code": "HN", "name": "Honduras"},
            "country_code": "HN",
            "prescript_roles": ["DOCTOR"],
            "specialties": [],
            "clinics": [],
        }
        self.request_code("SECRETARY", 55)
        code = self.sent_code()
        crossed = self.activate("DOCTOR", 55, code)
        self.assertEqual(crossed.status_code, 400)
        self.assertFalse(DoctorPortalProfile.objects.exists())
        self.assertEqual(self.activate("SECRETARY", 55, code).status_code, 201)


class StaffManualReviewTests(StaffAffiliationBase):
    def setUp(self):
        super().setUp()
        self.secretary = secretary_record(email="")
        self.nurse = nurse_record(email="")

    def submit(self, role, profile_id, email):
        self.assertEqual(self.request_code(role, profile_id, email).status_code, 200)
        response = self.activate(role, profile_id, self.sent_code(), email=email, phone="9988-7766")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data["pending_review"])
        return get_user_model().objects.get(email=email).affiliation_request

    def test_secretary_without_email_waits_for_review(self):
        request = self.submit("SECRETARY", 55, "mi-correo-sec@test.local")
        self.assertEqual((request.role, request.interactive_core_id, request.identifier), ("SECRETARY", 55, "0801199900123"))
        self.assertFalse(request.user.is_active)
        self.assertFalse(SecretaryPortalProfile.objects.exists())
        self.assertIn("en revision", str(self.login("mi-correo-sec@test.local").data))

    def test_admin_approval_links_each_role_to_its_own_profile(self):
        sec = self.submit("SECRETARY", 55, "mi-correo-sec@test.local")
        cache.clear()
        nur = self.submit("NURSE", 70, "mi-correo-nur@test.local")
        admin = create_user("root@test.local", roles=["ADMIN"])
        client = APIClient(HTTP_HOST="localhost")
        client.force_authenticate(admin)

        with mock.patch(ADMIN_PERMISSION, return_value=True):
            listing = client.get("/api/v1/admin/affiliation-requests", {"status": "pending"})
            rows = {row["role"]: row for row in listing.data}
            self.assertEqual(rows["SECRETARY"]["identifier_label"], "Documento")
            self.assertEqual(rows["NURSE"]["full_name"], "Enfermera Interactive")
            self.assertEqual(client.post(f"/api/v1/admin/affiliation-requests/{sec.id}/approve").status_code, 200)
            self.assertEqual(client.post(f"/api/v1/admin/affiliation-requests/{nur.id}/approve").status_code, 200)

        self.assertEqual(SecretaryPortalProfile.objects.get(secretaria_interactivecore_id=55).user, sec.user)
        nurse_profile = NursePortalProfile.objects.get(interactive_core_user_id=70)
        self.assertEqual((nurse_profile.user, nurse_profile.interactive_core_employee_id), (nur.user, 170))
        self.assertEqual(self.login("mi-correo-sec@test.local").status_code, 200)
        self.assertEqual(self.login("mi-correo-nur@test.local").status_code, 200)

    def test_approval_never_takes_a_secretary_already_linked_to_another_account(self):
        request = self.submit("SECRETARY", 55, "mi-correo-sec@test.local")
        create_secretary(
            secretaria_interactivecore_id=55, user=create_user("duenia@test.local", roles=["SECRETARY"])
        )
        admin = create_user("root@test.local", roles=["ADMIN"])
        client = APIClient(HTTP_HOST="localhost")
        client.force_authenticate(admin)
        with mock.patch(ADMIN_PERMISSION, return_value=True):
            response = client.post(f"/api/v1/admin/affiliation-requests/{request.id}/approve")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(SecretaryPortalProfile.objects.get(secretaria_interactivecore_id=55).user.email, "duenia@test.local")

    def test_competing_requests_only_collide_within_the_same_role_and_record(self):
        # La secretaria 55 y la enfermera 70 son fichas distintas: aprobar una no rechaza la otra.
        sec = self.submit("SECRETARY", 55, "mi-correo-sec@test.local")
        cache.clear()
        nur = self.submit("NURSE", 70, "mi-correo-nur@test.local")
        admin = create_user("root@test.local", roles=["ADMIN"])
        client = APIClient(HTTP_HOST="localhost")
        client.force_authenticate(admin)
        with mock.patch(ADMIN_PERMISSION, return_value=True):
            client.post(f"/api/v1/admin/affiliation-requests/{sec.id}/approve")
        nur.refresh_from_db()
        self.assertEqual(nur.status, "pending")


class ReviewerNotificationTests(StaffAffiliationBase):
    def setUp(self):
        super().setUp()
        self.secretary = secretary_record(email="")
        self.global_admin = create_user("global@test.local", roles=["ADMIN"])
        self.superuser = get_user_model().objects.create_superuser("super", "super@test.local", "Super-Pass-2026")
        self.hn_admin = create_user("admin-hn@test.local", roles=["ADMIN_HN"])
        self.gt_admin = create_user("admin-gt@test.local", roles=["ADMIN_GT"])
        self.inactive_admin = create_user("inactivo@test.local", roles=["ADMIN"], is_active=False)
        org_admin = create_user("orgadmin@test.local", roles=["ORG_ADMIN"])
        OrganizationAdminProfile.objects.create(
            user=org_admin,
            organization=Organization.objects.get(country__code="HN", is_interactive_core=True),
            full_name="Org Admin",
            country=Organization.objects.get(country__code="HN", is_interactive_core=True).country,
            status="active",
        )

    def submit(self):
        self.request_code("SECRETARY", 55, "mi-correo@test.local")
        mail.outbox.clear()
        code = None
        # El codigo se envio antes de limpiar: se vuelve a pedir tras el enfriamiento simulado.
        from api.models import OneTimeCode
        from datetime import timedelta
        from django.utils import timezone

        OneTimeCode.objects.update(created_at=timezone.now() - timedelta(minutes=5))
        self.request_code("SECRETARY", 55, "mi-correo@test.local")
        code = self.sent_code()
        mail.outbox.clear()
        return self.activate("SECRETARY", 55, code, email="mi-correo@test.local", phone="9988-7766")

    def test_only_reviewers_of_that_country_are_told_and_they_cannot_see_each_other(self):
        response = self.submit()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(
            sorted(message.bcc),
            sorted(["global@test.local", "super@test.local", "admin-hn@test.local"]),
        )
        # Ni el pais ajeno, ni el administrador inactivo, ni el de organizacion; y nadie ve a los demas.
        for excluded in ("admin-gt@test.local", "inactivo@test.local", "orgadmin@test.local"):
            self.assertNotIn(excluded, message.bcc)
        self.assertFalse(set(message.to) & set(message.bcc))
        self.assertIn("Secretaria Interactive", message.body)
        self.assertIn("Secretaria", message.body)
        self.assertIn("9988-7766", message.body)
        self.assertIn("mi-correo@test.local", message.body)

    def test_a_mail_failure_does_not_block_the_request(self):
        # Se parchea solo el aviso a administradores: el codigo OTP usa otro camino de envio.
        failing = mock.MagicMock()
        failing.return_value.send.side_effect = OSError("smtp caido")
        with mock.patch("api.services.affiliation_service.EmailMessage", failing):
            response = self.submit()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(AffiliationRequest.objects.count(), 1)

    def test_nobody_is_told_when_there_are_no_reviewers(self):
        get_user_model().objects.exclude(pk=self.superuser.pk).update(is_active=False)
        self.superuser.is_active = False
        self.superuser.save()
        response = self.submit()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(mail.outbox), 0)
