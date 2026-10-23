from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from rest_framework.test import APIClient

from api.models import AffiliationRequest, Country, DoctorPortalProfile, Organization, TermsAcceptance
from api.services.interactive_core import InteractiveCoreDoctorService
from api.test_affiliation import DOCTOR_EMAIL, AffiliationBase, ic_doctor
from api.test_factories import create_doctor, create_user

# Doctores sin correo en su ficha: revision manual por un administrador de Interactive Core.

OWN_EMAIL = "mi-correo@test.local"
ADMIN_PERMISSION = "api.permissions.admin_permissions.user_is_interactive_core_admin"


class ManualReviewBase(AffiliationBase):
    def setUp(self):
        super().setUp()
        self.doctor = ic_doctor(email="")

    def request_own_code(self, email=OWN_EMAIL, doctor_id=9100):
        return self.client.post(
            "/api/v1/auth/affiliation/request-code", {"profile_id": doctor_id, "email": email}, format="json"
        )

    def submit_request(self, email=OWN_EMAIL, **extra):
        self.assertEqual(self.request_own_code(email).status_code, 200)
        return self.activate(self.sent_code(), email=email, **extra)

    def login(self, email=OWN_EMAIL, password="Clave-Segura-2026"):
        return APIClient().post("/api/v1/auth/login", {"email": email, "password": password}, format="json")


class ManualReviewRequestTests(ManualReviewBase):
    def test_search_reports_whether_the_record_has_an_email_without_exposing_it(self):
        rows = [
            {"id": 1, "full_name": "Con Correo", "colegiation_code": "AAA111", "country_code": "HN", "has_email": True},
            {"id": 2, "full_name": "Sin Correo", "colegiation_code": "BBB222", "country_code": "HN", "has_email": False},
        ]
        with mock.patch.object(InteractiveCoreDoctorService, "search_doctors", return_value=rows):
            response = self.client.get("/api/v1/auth/affiliation/search", {"q": "Corr"})
        self.assertEqual([item["has_email"] for item in response.data], [True, False])
        self.assertNotIn("@", str(response.data))

    def test_record_without_email_asks_for_the_doctors_own_email(self):
        response = self.client.post("/api/v1/auth/affiliation/request-code", {"profile_id": 9100}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.data["requires_own_email"])
        self.assertEqual(len(mail.outbox), 0)

    def test_code_goes_to_the_email_the_doctor_provides(self):
        response = self.request_own_code()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["mode"], "manual_review")
        self.assertEqual(response.data["email_hint"], "m***@test.local")
        self.assertEqual(mail.outbox[0].to, [OWN_EMAIL])

    def test_a_record_with_email_ignores_a_supplied_email(self):
        self.doctor = ic_doctor()
        response = self.request_own_code(email="otro@test.local")
        self.assertEqual(response.data["mode"], "verified")
        self.assertEqual(mail.outbox[0].to, [DOCTOR_EMAIL])

    def test_email_already_registered_or_doctor_already_linked_never_get_mail(self):
        create_user(OWN_EMAIL)
        self.assertEqual(self.request_own_code().status_code, 400)
        create_doctor(interactive_core_doctor_id=9100, user=create_user("otra-cuenta@test.local"))
        self.assertEqual(self.request_own_code(email="libre@test.local").status_code, 400)
        self.assertEqual(len(mail.outbox), 0)

    def test_submission_creates_an_inactive_account_and_a_pending_request(self):
        response = self.submit_request(phone="9988-7766")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data["pending_review"])
        self.assertNotIn("access", response.data)

        user = get_user_model().objects.get(email=OWN_EMAIL)
        self.assertFalse(user.is_active)
        self.assertFalse(DoctorPortalProfile.objects.filter(interactive_core_doctor_id=9100).exists())
        request = user.affiliation_request
        self.assertEqual(
            (request.status, request.interactive_core_id, request.contact_phone, request.country.code),
            ("pending", 9100, "9988-7766", "HN"),
        )
        self.assertEqual(request.identifier, "COL-12345")
        self.assertTrue(TermsAcceptance.objects.filter(user=user, terms=self.terms).exists())

    def test_the_code_only_works_for_the_email_it_was_sent_to(self):
        self.request_own_code()
        code = self.sent_code()
        wrong = self.activate(code, email="otro-correo@test.local")
        self.assertEqual(wrong.status_code, 400)
        self.assertFalse(get_user_model().objects.filter(email="otro-correo@test.local").exists())
        self.assertEqual(self.activate(code, email=OWN_EMAIL).status_code, 201)

    def test_a_pending_request_cannot_log_in_and_sees_why(self):
        self.submit_request()
        response = self.login()
        self.assertEqual(response.status_code, 400)
        self.assertIn("en revision", str(response.data))

    def test_wrong_code_creates_nothing(self):
        self.request_own_code()
        real = self.sent_code()
        wrong = "000000" if real != "000000" else "111111"
        self.assertEqual(self.activate(wrong, email=OWN_EMAIL).status_code, 400)
        self.assertFalse(get_user_model().objects.filter(email=OWN_EMAIL).exists())


class ManualReviewDecisionTests(ManualReviewBase):
    def setUp(self):
        super().setUp()
        self.admin = create_user("admin-global@test.local", roles=["ADMIN"])
        patcher = mock.patch(ADMIN_PERMISSION, return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.admin_client = APIClient(HTTP_HOST="localhost")
        self.admin_client.force_authenticate(self.admin)

    def pending_request(self, email=OWN_EMAIL):
        cache.clear()
        self.submit_request(email=email)
        mail.outbox.clear()
        return get_user_model().objects.get(email=email).affiliation_request

    def test_admin_sees_the_record_data_to_compare(self):
        request = self.pending_request()
        response = self.admin_client.get("/api/v1/admin/affiliation-requests", {"status": "pending"})
        self.assertEqual(response.status_code, 200)
        row = response.data[0]
        self.assertEqual(
            (row["id"], row["full_name"], row["identifier"], row["email"], row["country_code"]),
            (request.id, "Dr. Interactive", "COL-12345", OWN_EMAIL, "HN"),
        )

    def test_approval_links_the_record_keeps_the_password_and_notifies(self):
        request = self.pending_request()
        response = self.admin_client.post(f"/api/v1/admin/affiliation-requests/{request.id}/approve")
        self.assertEqual(response.status_code, 200, response.data)

        profile = DoctorPortalProfile.objects.get(interactive_core_doctor_id=9100)
        self.assertEqual(profile.user.email, OWN_EMAIL)
        self.assertEqual(profile.origin, "interactive_core")
        self.assertEqual(profile.organization, Organization.objects.get(country__code="HN", is_interactive_core=True))
        request.refresh_from_db()
        self.assertEqual((request.status, request.decided_by), ("approved", self.admin))
        self.assertEqual(mail.outbox[0].to, [OWN_EMAIL])
        # Entra con la contrasena que eligio al solicitar, sin que nadie la restablezca.
        self.assertEqual(self.login().status_code, 200)

    def test_approval_rejects_competing_requests_for_the_same_record(self):
        first = self.pending_request()
        second = self.pending_request(email="rival@test.local")
        self.admin_client.post(f"/api/v1/admin/affiliation-requests/{first.id}/approve")
        second.refresh_from_db()
        self.assertEqual(second.status, "rejected")
        self.assertFalse(second.user.is_active)
        self.assertEqual(DoctorPortalProfile.objects.filter(interactive_core_doctor_id=9100).count(), 1)
        self.assertEqual(self.login(email="rival@test.local").status_code, 400)

    def test_rejection_keeps_the_account_inactive_and_says_so_on_login(self):
        request = self.pending_request()
        response = self.admin_client.post(f"/api/v1/admin/affiliation-requests/{request.id}/reject")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(DoctorPortalProfile.objects.exists())
        self.assertEqual(mail.outbox[0].to, [OWN_EMAIL])
        login = self.login()
        self.assertEqual(login.status_code, 400)
        self.assertIn("no fue aprobada", str(login.data))

    def test_a_resolved_request_cannot_be_decided_again(self):
        request = self.pending_request()
        self.admin_client.post(f"/api/v1/admin/affiliation-requests/{request.id}/approve")
        again = self.admin_client.post(f"/api/v1/admin/affiliation-requests/{request.id}/reject")
        self.assertEqual(again.status_code, 400)
        request.refresh_from_db()
        self.assertEqual(request.status, "approved")

    def test_approval_never_takes_a_record_already_linked_to_another_account(self):
        request = self.pending_request()
        create_doctor(interactive_core_doctor_id=9100, user=create_user("duenio@test.local", roles=["DOCTOR"]))
        response = self.admin_client.post(f"/api/v1/admin/affiliation-requests/{request.id}/approve")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            DoctorPortalProfile.objects.get(interactive_core_doctor_id=9100).user.email, "duenio@test.local"
        )
        request.refresh_from_db()
        self.assertEqual(request.status, "pending")

    def test_approval_requires_the_record_to_still_be_active(self):
        request = self.pending_request()
        self.doctor = ic_doctor(email="", status="inactive")
        response = self.admin_client.post(f"/api/v1/admin/affiliation-requests/{request.id}/approve")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(DoctorPortalProfile.objects.exists())

    def test_mail_failure_does_not_undo_the_decision(self):
        request = self.pending_request()
        with mock.patch("api.services.affiliation_service.send_mail", side_effect=OSError("smtp caido")):
            response = self.admin_client.post(f"/api/v1/admin/affiliation-requests/{request.id}/approve")
        self.assertEqual(response.status_code, 200)
        request.refresh_from_db()
        self.assertEqual(request.status, "approved")

    def test_country_admin_only_decides_requests_of_its_own_country(self):
        hn_request = self.pending_request()
        gt_request = self.pending_request(email="gt@test.local")
        AffiliationRequest.objects.filter(pk=gt_request.pk).update(country=Country.objects.get(code="GT"))
        country_admin = create_user("admin-hn@test.local", roles=["ADMIN_HN"])
        client = APIClient(HTTP_HOST="localhost")
        client.force_authenticate(country_admin)

        listing = client.get("/api/v1/admin/affiliation-requests")
        self.assertEqual([row["id"] for row in listing.data], [hn_request.id])
        self.assertEqual(client.post(f"/api/v1/admin/affiliation-requests/{gt_request.id}/approve").status_code, 404)
        self.assertEqual(client.post(f"/api/v1/admin/affiliation-requests/{hn_request.id}/approve").status_code, 200)

    def test_only_interactive_core_administrators_can_review(self):
        request = self.pending_request()
        outsiders = [
            create_user("doctor-x@test.local", roles=["DOCTOR"]),
            create_user("org-admin@test.local", roles=["ORG_ADMIN"]),
        ]
        with mock.patch(ADMIN_PERMISSION, return_value=False):
            for user in outsiders:
                client = APIClient(HTTP_HOST="localhost")
                client.force_authenticate(user)
                self.assertEqual(client.get("/api/v1/admin/affiliation-requests").status_code, 403)
                self.assertEqual(
                    client.post(f"/api/v1/admin/affiliation-requests/{request.id}/approve").status_code, 403
                )
            self.assertEqual(APIClient().get("/api/v1/admin/affiliation-requests").status_code, 401)
