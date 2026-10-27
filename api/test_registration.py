from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from api.models import (
    Country,
    DoctorPortalProfile,
    OneTimeCode,
    Organization,
    OrganizationAdminProfile,
    OrganizationInvitation,
    Patient,
    PatientPortalProfile,
    SpecialtyCatalogMirror,
    TermsAcceptance,
    TermsVersion,
    UserCountryAccess,
)
from api.services.organization_service import OrganizationAdminService


def extract_code(message):
    return next(token for token in message.body.split() if token.rstrip(".").isdigit()).rstrip(".")


class RegistrationBase(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.country = Country.objects.get(code="HN")
        self.organization = Organization.objects.create(name="Clinica Norte", country=self.country)
        self.terms = TermsVersion.objects.create(version="1.0", content="texto", is_current=True)
        self.specialty = SpecialtyCatalogMirror.objects.create(
            interactive_core_id=900, country=self.country, name="Cardiologia"
        )
        self.organization.medical_areas.add(self.specialty)

    def invite(self, role, **kwargs):
        return OrganizationInvitation.objects.create(
            organization=self.organization,
            role=role,
            code=f"CODE-{role}-{OrganizationInvitation.objects.count()}",
            **kwargs,
        )

    def payload(self, role, invitation, **extra):
        data = {
            "role": role,
            "invitation_code": invitation.code,
            "full_name": "Ana Lopez",
            "email": "ana@example.com",
            "password": "Clave-Segura-2026",
            "password_confirm": "Clave-Segura-2026",
            "country": "HN",
            "accept_terms": True,
        }
        data.update(extra)
        return data

    def register(self, role, invitation, **extra):
        return self.client.post("/api/v1/auth/register", self.payload(role, invitation, **extra), format="json")


class ExternalRegistrationTests(RegistrationBase):
    def test_doctor_registers_as_external_with_organization_and_terms(self):
        invitation = self.invite("DOCTOR")
        response = self.register("DOCTOR", invitation, colegiation_code="COL-1", specialty_ids=[self.specialty.id])
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertIn("access", response.data)
        doctor = DoctorPortalProfile.objects.get(user__email="ana@example.com")
        self.assertEqual(doctor.origin, "self_registered")
        self.assertIsNone(doctor.interactive_core_doctor_id)
        self.assertEqual(doctor.organization, self.organization)
        self.assertEqual(doctor.specialties[0]["name"], "Cardiologia")
        self.assertTrue(TermsAcceptance.objects.filter(user=doctor.user, terms=self.terms).exists())
        self.assertTrue(
            UserCountryAccess.objects.filter(user=doctor.user, role_code="DOCTOR", country=self.country).exists()
        )
        invitation.refresh_from_db()
        self.assertEqual(invitation.uses, 1)

    def test_doctor_requires_colegiation_code(self):
        response = self.register("DOCTOR", self.invite("DOCTOR"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("colegiation_code", response.data)

    def test_secretary_and_nurse_register(self):
        self.assertEqual(self.register("SECRETARY", self.invite("SECRETARY")).status_code, 201)
        response = self.register("NURSE", self.invite("NURSE"), email="nurse@example.com")
        self.assertEqual(response.status_code, 201, response.data)

    def test_invitation_must_match_role(self):
        response = self.register("DOCTOR", self.invite("SECRETARY"), colegiation_code="X")
        self.assertEqual(response.status_code, 400)
        self.assertIn("invitation_code", response.data)

    def test_expired_revoked_and_exhausted_invitations_are_rejected(self):
        cases = [
            self.invite("SECRETARY", expires_at=timezone.now() - timedelta(days=1)),
            self.invite("SECRETARY", is_active=False),
            self.invite("SECRETARY", max_uses=1, uses=1),
        ]
        for invitation in cases:
            response = self.register("SECRETARY", invitation)
            self.assertEqual(response.status_code, 400)
            self.assertIn("invitation_code", response.data)

    def test_country_must_match_organization(self):
        response = self.register("SECRETARY", self.invite("SECRETARY"), country="GT")
        self.assertEqual(response.status_code, 400)
        self.assertIn("country", response.data)

    def test_terms_are_mandatory(self):
        invitation = self.invite("SECRETARY")
        response = self.register("SECRETARY", invitation, accept_terms=False)
        self.assertEqual(response.status_code, 400)
        self.assertIn("accept_terms", response.data)
        self.terms.delete()
        self.assertEqual(self.register("SECRETARY", invitation).status_code, 400)

    def test_duplicate_email_does_not_touch_existing_account(self):
        user = get_user_model().objects.create_user("ana@example.com", "ana@example.com", "Original-Pass-1")
        response = self.register("SECRETARY", self.invite("SECRETARY"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data)
        user.refresh_from_db()
        self.assertTrue(user.check_password("Original-Pass-1"))

    def test_weak_password_is_rejected(self):
        response = self.register("SECRETARY", self.invite("SECRETARY"), password="12345678", password_confirm="12345678")
        self.assertEqual(response.status_code, 400)

    def test_max_uses_is_enforced_across_registrations(self):
        invitation = self.invite("SECRETARY", max_uses=1)
        self.assertEqual(self.register("SECRETARY", invitation).status_code, 201)
        self.assertEqual(self.register("SECRETARY", invitation, email="otra@example.com").status_code, 400)

    def test_org_admin_registers_pending_without_tokens_and_superuser_approves(self):
        response = self.register("ORG_ADMIN", self.invite("ORG_ADMIN"))
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data["pending_approval"])
        self.assertNotIn("access", response.data)
        profile = OrganizationAdminProfile.objects.get(user__email="ana@example.com")
        self.assertEqual(profile.status, "pending")
        approver = get_user_model().objects.create_superuser("root", "root@example.com", "Root-Pass-2026")
        OrganizationAdminService().approve(profile, approver)
        profile.refresh_from_db()
        self.assertEqual((profile.status, profile.approved_by), ("active", approver))

    def test_invitation_validate_returns_organization_without_consuming(self):
        invitation = self.invite("DOCTOR")
        response = self.client.post(
            "/api/v1/auth/invitation/validate", {"invitation_code": invitation.code}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["organization"]["name"], "Clinica Norte")
        self.assertEqual(response.data["organization"]["medical_areas"], ["Cardiologia"])
        self.assertEqual(response.data["role"], "DOCTOR")
        invitation.refresh_from_db()
        self.assertEqual(invitation.uses, 0)


class PatientHistoryTests(RegistrationBase):
    def setUp(self):
        super().setUp()
        doctor_user = get_user_model().objects.create_user("doc@example.com", "doc@example.com", "x-Pass-12345")
        doctor = DoctorPortalProfile.objects.create(
            user=doctor_user, interactive_core_doctor_id=5, full_name="Dr", country=self.country
        )
        self.record = Patient.objects.create(
            doctor=doctor, first_name="Ana", last_name="Lopez", dni="0801-1990-12345", email="registrada@example.com"
        )
        response = self.register("PATIENT", self.invite("PATIENT"), document_number="0801 1990 12345")
        self.assertEqual(response.status_code, 201, response.data)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        self.profile = PatientPortalProfile.objects.get(user__email="ana@example.com")
        mail.outbox.clear()

    def test_account_starts_without_verified_history(self):
        self.assertIsNone(self.profile.history_verified_at)
        self.assertEqual(self.profile.document_number, "08011990" "12345")

    def test_duplicate_document_is_rejected(self):
        response = self.register(
            "PATIENT", self.invite("PATIENT"), email="otra@example.com", document_number="0801-1990-12345"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("document_number", response.data)

    def test_code_goes_only_to_email_on_clinical_record_and_verifies(self):
        self.assertEqual(self.client.post("/api/v1/patient/history/request").status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["registrada@example.com"])
        code = extract_code(mail.outbox[0])
        self.assertNotIn(code, OneTimeCode.objects.get().code_hash)

        verify = self.client.post("/api/v1/patient/history/verify", {"code": code}, format="json")
        self.assertEqual(verify.status_code, 200, verify.data)
        self.assertEqual(verify.data["records"], 1)
        self.profile.refresh_from_db()
        self.assertIsNotNone(self.profile.history_verified_at)

    def test_response_is_identical_when_no_history_exists(self):
        existing = self.client.post("/api/v1/patient/history/request")
        self.record.delete()
        cache.clear()
        OneTimeCode.objects.all().delete()
        mail.outbox.clear()
        missing = self.client.post("/api/v1/patient/history/request")
        self.assertEqual(existing.data, missing.data)
        self.assertEqual(len(mail.outbox), 0)

    def test_wrong_code_is_rejected_and_attempts_are_limited(self):
        self.client.post("/api/v1/patient/history/request")
        real_code = extract_code(mail.outbox[-1])
        wrong = "000000" if real_code != "000000" else "111111"
        for _ in range(5):
            response = self.client.post("/api/v1/patient/history/verify", {"code": wrong}, format="json")
            self.assertEqual(response.status_code, 400)
        locked = self.client.post("/api/v1/patient/history/verify", {"code": real_code}, format="json")
        self.assertEqual(locked.status_code, 400)
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.history_verified_at)

    def test_resend_cooldown_and_expiry(self):
        self.client.post("/api/v1/patient/history/request")
        self.assertEqual(self.client.post("/api/v1/patient/history/request").status_code, 400)
        OneTimeCode.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
        code = extract_code(mail.outbox[-1])
        self.assertEqual(self.client.post("/api/v1/patient/history/verify", {"code": code}, format="json").status_code, 400)

    def test_non_patient_cannot_use_history_endpoints(self):
        user = get_user_model().objects.create_user("x@example.com", "x@example.com", "Pass-1234-xyz")
        client = APIClient()
        client.force_authenticate(user)
        self.assertEqual(client.post("/api/v1/patient/history/request").status_code, 403)
