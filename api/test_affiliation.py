from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from api.models import DoctorPortalProfile, OneTimeCode, Organization, TermsAcceptance, TermsVersion
from api.services.interactive_core import InteractiveCoreDoctorService
from api.test_factories import create_doctor, create_user

DOCTOR_EMAIL = "doctor-ic@test.local"


def ic_doctor(**overrides):
    doctor = {
        "id": 9100,
        "full_name": "Dr. Interactive",
        "email": DOCTOR_EMAIL,
        "phone": None,
        "status": "active",
        "has_doctor_role": True,
        "prescript_roles": ["DOCTOR"],
        "colegiation_code": "COL-12345",
        "country_code": "HN",
        "country_name": "Honduras",
        "country": {"code": "HN", "name": "Honduras"},
        "specialties": [],
        "clinics": [],
    }
    doctor.update(overrides)
    return doctor


class AffiliationBase(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.terms = TermsVersion.objects.create(version="1.0", content="texto", is_current=True)
        self.doctor = ic_doctor()
        patcher = mock.patch.object(
            InteractiveCoreDoctorService, "get_doctor_for_activation", side_effect=lambda doctor_id: self.lookup(doctor_id)
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        mail.outbox.clear()

    def lookup(self, doctor_id):
        return self.doctor if doctor_id == self.doctor["id"] else None

    def request_code(self, doctor_id=9100):
        return self.client.post("/api/v1/auth/affiliation/request-code", {"profile_id": doctor_id}, format="json")

    def sent_code(self):
        return next(t for t in mail.outbox[-1].body.split() if t.rstrip(".").isdigit()).rstrip(".")

    def activate(self, code, **extra):
        body = {
            "profile_id": 9100,
            "code": code,
            "password": "Clave-Segura-2026",
            "password_confirm": "Clave-Segura-2026",
            "accept_terms": True,
        }
        body.update(extra)
        return self.client.post("/api/v1/auth/affiliation/activate", body, format="json")


class AffiliationSearchTests(AffiliationBase):
    def test_search_returns_only_minimal_non_sensitive_fields(self):
        rows = [{"id": 9100, "full_name": "Dr. Interactive", "colegiation_code": "COL-12345", "country_code": "HN"}]
        with mock.patch.object(InteractiveCoreDoctorService, "search_doctors", return_value=rows) as search:
            response = self.client.get("/api/v1/auth/affiliation/search", {"q": "Inter"})
        self.assertEqual(response.status_code, 200)
        search.assert_called_once_with("Inter")
        self.assertEqual(
            response.data,
            [{"id": 9100, "full_name": "Dr. Interactive", "country_code": "HN", "identifier_label": "Colegiacion",
                "identifier_hint": "***345", "has_email": None}],
        )

    def test_short_queries_do_not_reach_interactive_core(self):
        with mock.patch.object(InteractiveCoreDoctorService, "search_doctors") as search:
            response = self.client.get("/api/v1/auth/affiliation/search", {"q": "Dr"})
        self.assertEqual(response.data, [])
        search.assert_not_called()


class AffiliationCodeTests(AffiliationBase):
    def test_code_is_sent_only_to_the_email_registered_in_interactive_core(self):
        response = self.request_code()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["email_hint"], "d***@test.local")
        self.assertNotIn(DOCTOR_EMAIL, str(response.data))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [DOCTOR_EMAIL])

    def test_unavailable_doctors_never_receive_mail(self):
        for override in ({"status": "inactive"}, {"has_doctor_role": False}, {"email": ""}):
            self.doctor = ic_doctor(**override)
            self.assertEqual(self.request_code().status_code, 400, override)
        self.assertEqual(self.request_code(doctor_id=1).status_code, 400)
        self.assertEqual(len(mail.outbox), 0)

    def test_resend_cooldown(self):
        self.assertEqual(self.request_code().status_code, 200)
        self.assertEqual(self.request_code().status_code, 400)
        self.assertEqual(len(mail.outbox), 1)

    @mock.patch("rest_framework.throttling.ScopedRateThrottle.get_rate", return_value="1000/hour")
    def test_requesting_new_codes_does_not_reset_the_failed_attempt_cap(self, _rate):
        # Sin el limite por IP, para medir solo el tope por destinatario (atacante con varias IP).
        for _ in range(3):
            self.request_code()
            for _ in range(5):
                self.activate("000000" if self.sent_code() != "000000" else "111111")
            OneTimeCode.objects.update(created_at=timezone.now() - timedelta(minutes=5))
        mail.outbox.clear()
        blocked = self.request_code()
        self.assertEqual(blocked.status_code, 400)
        self.assertEqual(len(mail.outbox), 0)


class AffiliationActivationTests(AffiliationBase):
    def test_full_flow_creates_an_interactive_core_account_in_the_country_organization(self):
        self.request_code()
        response = self.activate(self.sent_code())
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIn("access", response.data)

        user = get_user_model().objects.get(email=DOCTOR_EMAIL)
        profile = DoctorPortalProfile.objects.get(user=user)
        self.assertEqual(profile.interactive_core_doctor_id, 9100)
        self.assertEqual(profile.origin, "interactive_core")
        self.assertEqual(profile.organization, Organization.objects.get(country__code="HN", is_interactive_core=True))
        self.assertTrue(TermsAcceptance.objects.filter(user=user, terms=self.terms).exists())

        login = APIClient().post(
            "/api/v1/auth/login", {"email": DOCTOR_EMAIL, "password": "Clave-Segura-2026"}, format="json"
        )
        self.assertEqual(login.status_code, 200)

    def test_wrong_code_creates_nothing(self):
        self.request_code()
        real = self.sent_code()
        wrong = "000000" if real != "000000" else "111111"
        self.assertEqual(self.activate(wrong).status_code, 400)
        self.assertFalse(get_user_model().objects.filter(email=DOCTOR_EMAIL).exists())

    def test_five_wrong_attempts_lock_the_code_even_for_the_right_one(self):
        self.request_code()
        real = self.sent_code()
        wrong = "000000" if real != "000000" else "111111"
        for _ in range(5):
            self.assertEqual(self.activate(wrong).status_code, 400)
        self.assertEqual(self.activate(real).status_code, 400)
        self.assertFalse(get_user_model().objects.filter(email=DOCTOR_EMAIL).exists())

    def test_code_is_single_use(self):
        self.request_code()
        code = self.sent_code()
        self.assertEqual(self.activate(code).status_code, 201)
        self.assertEqual(self.activate(code, password="Otra-Clave-2026", password_confirm="Otra-Clave-2026").status_code, 400)

    def test_terms_must_be_accepted_and_do_not_burn_the_code(self):
        self.request_code()
        code = self.sent_code()
        self.assertEqual(self.activate(code, accept_terms=False).status_code, 400)
        self.assertEqual(self.activate(code).status_code, 201)

    def test_weak_or_mismatched_passwords_do_not_burn_the_code(self):
        self.request_code()
        code = self.sent_code()
        self.assertEqual(self.activate(code, password="12345678", password_confirm="12345678").status_code, 400)
        self.assertEqual(self.activate(code, password_confirm="Distinta-2026").status_code, 400)
        self.assertEqual(self.activate(code).status_code, 201)

    def test_code_for_one_doctor_cannot_activate_another(self):
        self.request_code()
        code = self.sent_code()
        other = ic_doctor(id=9200, email="otro@test.local")
        self.lookup = lambda doctor_id: {9100: self.doctor, 9200: other}.get(doctor_id)
        self.assertEqual(self.activate(code, profile_id=9200).status_code, 400)
        self.assertFalse(get_user_model().objects.filter(email="otro@test.local").exists())

    def test_it_cannot_take_over_an_external_account_with_the_same_email(self):
        external = create_user(DOCTOR_EMAIL, roles=["DOCTOR"])
        create_doctor(user=external, interactive_core_doctor_id=None, origin="self_registered", full_name="Externo")
        self.request_code()
        response = self.activate(self.sent_code())
        self.assertEqual(response.status_code, 400)
        external.refresh_from_db()
        self.assertTrue(external.check_password("Doctor1234!"))

    def test_existing_interactive_core_account_can_reset_its_password_with_the_code(self):
        self.request_code()
        self.activate(self.sent_code())
        OneTimeCode.objects.update(created_at=timezone.now() - timedelta(minutes=5))
        self.request_code()
        response = self.activate(self.sent_code(), password="Nueva-Clave-2026", password_confirm="Nueva-Clave-2026")
        self.assertEqual(response.status_code, 201, response.data)
        user = get_user_model().objects.get(email=DOCTOR_EMAIL)
        self.assertTrue(user.check_password("Nueva-Clave-2026"))
        self.assertEqual(DoctorPortalProfile.objects.filter(interactive_core_doctor_id=9100).count(), 1)
