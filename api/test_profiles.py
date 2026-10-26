from django.test import TestCase

from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from api.test_factories import create_doctor, create_nurse, create_user



class DoctorProfileUpdateTests(TestCase):
    def setUp(self):
        self.client = APIClient(HTTP_HOST="localhost")
        self.user = create_user(
            username="profile-doctor@test.local",
            email="profile-doctor@test.local",
            password="Doctor1234!",
            roles=["DOCTOR"],
        )
        self.doctor = create_doctor(
            user=self.user,
            interactive_core_doctor_id=901,
            full_name="Doctora Perfil",
            specialties=[{"id": 1, "name": "Cardiologia", "code": "CAR"}],
            status="active",
        )
        self.client.force_authenticate(self.user)

    def test_specialties_are_read_only_from_doctor_profile_patch(self):
        response = self.client.patch(
            "/api/v1/doctor/me",
            {
                "phone": "88881111",
                "specialties": [{"id": 9, "name": "Dermatologia", "code": "DER"}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.doctor.refresh_from_db()
        self.assertEqual(self.doctor.phone, "88881111")
        self.assertEqual(self.doctor.specialties, [{"id": 1, "name": "Cardiologia", "code": "CAR"}])



class UserProfileUpdateTests(TestCase):
    def setUp(self):
        self.client = APIClient(HTTP_HOST="localhost")
        self.user = create_user(
            username="nurse@test.local",
            email="nurse@test.local",
            password="Doctor1234!",
            roles=["NURSE"],
        )
        self.profile = create_nurse(
            user=self.user,
            interactive_core_user_id=700,
            interactive_core_employee_id=1700,
            full_name="Enfermera Perfil",
            email="nurse@test.local",
            phone="99991111",
            country="HN",
        )
        self.client.force_authenticate(self.user)

    def test_user_can_update_email_and_phone_from_auth_me(self):
        response = self.client.patch(
            "/api/v1/auth/me",
            {
                "email": "nurse.updated@test.local",
                "phone": "88882222",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertEqual(self.user.email, "nurse.updated@test.local")
        self.assertEqual(self.user.username, "nurse.updated@test.local")
        self.assertEqual(self.profile.email, "nurse.updated@test.local")
        self.assertEqual(self.profile.phone, "8888-2222")
        self.assertEqual(response.data["email"], "nurse.updated@test.local")

    def test_user_can_change_password_with_new_password_and_confirmation(self):
        response = self.client.patch(
            "/api/v1/auth/me",
            {
                "current_password": "Doctor1234!",
                "new_password": "Nuevo1234!",
                "password_confirm": "Nuevo1234!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Nuevo1234!"))

    def test_password_change_revokes_existing_access_tokens(self):
        access = str(RefreshToken.for_user(self.user).access_token)
        token_client = APIClient(HTTP_AUTHORIZATION=f"Bearer {access}", HTTP_HOST="localhost")

        changed = token_client.patch(
            "/api/v1/auth/me",
            {
                "current_password": "Doctor1234!",
                "new_password": "Nuevo1234!",
                "password_confirm": "Nuevo1234!",
            },
            format="json",
        )
        rejected = token_client.get("/api/v1/auth/me")

        self.assertEqual(changed.status_code, status.HTTP_200_OK)
        self.assertEqual(rejected.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_cannot_change_password_when_confirmation_does_not_match(self):
        response = self.client.patch(
            "/api/v1/auth/me",
            {
                "current_password": "Doctor1234!",
                "new_password": "Nuevo1234!",
                "password_confirm": "Distinta123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Doctor1234!"))

    def test_user_cannot_change_password_without_correct_current_password(self):
        for extra in ({}, {"current_password": "Incorrecta123!"}):
            with self.subTest(extra=extra):
                response = self.client.patch(
                    "/api/v1/auth/me",
                    {"new_password": "Nuevo1234!", "password_confirm": "Nuevo1234!", **extra},
                    format="json",
                )

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("current_password", response.data)
                self.user.refresh_from_db()
                self.assertTrue(self.user.check_password("Doctor1234!"))
