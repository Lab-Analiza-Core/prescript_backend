from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from api.models import (
    DoctorAccessLog,
    DoctorCredential,
    DoctorPortalProfile,
    NursePortalProfile,
    SecretaryPortalProfile,
    UserCountryAccess,
)
from api.roles import PRESCRIPT_ROLE_DOCTOR, PRESCRIPT_ROLE_NURSE, PRESCRIPT_ROLE_SECRETARY
from api.services.doctor_display import get_doctor_sex_from_profile_data
from api.services.account_origin import is_external_account
from api.services.country_service import get_or_create_country
from api.services.organization_service import get_interactive_core_organization


class AccessActivationService:
    def _create_or_update_user(self, profile_data, email, password):
        if not email:
            raise serializers.ValidationError({"email": "Se requiere correo para crear credenciales."})

        username = email.lower()
        user_model = get_user_model()
        existing = user_model.objects.filter(username=username).first()
        if existing and is_external_account(existing):
            raise serializers.ValidationError({"email": "Este correo ya esta registrado como cuenta externa."})
        user, _ = user_model.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "first_name": profile_data.get("full_name", "")[:150],
                "is_active": True,
            },
        )
        user.email = email
        user.is_active = True
        user.set_password(password)
        user.save(update_fields=["email", "is_active", "password"])
        return user

    def _add_roles(self, user, roles):
        for role in roles:
            group, _ = Group.objects.get_or_create(name=role)
            user.groups.add(group)

    def _token_payload(self, user):
        refresh = RefreshToken.for_user(user)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }

    def _activate_doctor_profile(self, user, doctor_data, email):
        country = get_or_create_country(doctor_data)
        profile, _ = DoctorPortalProfile.objects.update_or_create(
            interactive_core_doctor_id=doctor_data["id"],
            defaults={
                "user": user,
                "full_name": doctor_data.get("full_name") or email.lower(),
                "sex": get_doctor_sex_from_profile_data(doctor_data),
                "colegiation_code": doctor_data.get("colegiation_code"),
                "qualification_code": doctor_data.get("qualification_code"),
                "final_score": doctor_data.get("final_score"),
                "country": country,
                "organization": get_interactive_core_organization(country),
                "origin": "interactive_core",
                "phone": doctor_data.get("phone"),
                "public_email": email,
                "specialties": doctor_data.get("specialties") or [],
                "clinics": doctor_data.get("clinics") or [],
                "is_top_doctor": doctor_data.get("is_top_doctor", False),
                "status": "active",
                "last_synced_at": timezone.now(),
            },
        )

        credential, _ = DoctorCredential.objects.update_or_create(
            doctor=profile,
            defaults={
                "username": email.lower(),
                "email": email,
                "is_portal_enabled": True,
                "password_set_at": timezone.now(),
                "last_password_change_at": timezone.now(),
            },
        )
        return profile, credential

    def _sync_country_access(self, user, role, country):
        if not country:
            return
        UserCountryAccess.objects.update_or_create(
            user=user,
            role_code=role,
            country=country,
            defaults={"is_active": True},
        )

    def link_doctor(self, user, doctor_data, email, source="doctor_activation"):
        """Crea el perfil de doctor de un usuario ya existente, sin tocar su contrasena."""
        portal_roles = doctor_data.get("prescript_roles") or [PRESCRIPT_ROLE_DOCTOR]
        self._add_roles(user, portal_roles)
        profile, credential = self._activate_doctor_profile(user, doctor_data, email)
        self._sync_country_access(user, PRESCRIPT_ROLE_DOCTOR, profile.country)

        DoctorAccessLog.objects.create(
            doctor=profile,
            event_type="password_set",
            metadata={"source": source},
        )
        return profile, credential, portal_roles

    @transaction.atomic
    def activate_doctor(self, doctor_data, email, password):
        access_email = email or doctor_data.get("email")
        user = self._create_or_update_user(doctor_data, access_email, password)
        profile, credential, portal_roles = self.link_doctor(user, doctor_data, access_email)

        return {
            **self._token_payload(user),
            "doctor_profile_id": profile.id,
            "credential_id": credential.id,
            "roles": portal_roles,
        }

    def link_portal_profile(self, user, role, profile_data, email):
        """Crea el perfil de secretaria o enfermera de un usuario ya existente, sin tocar su contrasena.

        Devuelve el perfil creado o actualizado y el nombre de su id en la respuesta.
        """
        self._add_roles(user, [role])
        country = get_or_create_country(profile_data)
        common = {
            "user": user,
            "full_name": profile_data.get("full_name") or email.lower(),
            "email": email,
            "phone": profile_data.get("phone"),
            "country": country,
            "organization": get_interactive_core_organization(country),
            "origin": "interactive_core",
            "status": "active",
            "last_synced_at": timezone.now(),
        }

        if role == PRESCRIPT_ROLE_SECRETARY:
            profile, _ = SecretaryPortalProfile.objects.update_or_create(
                secretaria_interactivecore_id=profile_data["id"], defaults=common
            )
            id_key = "secretary_profile_id"
        elif role == PRESCRIPT_ROLE_NURSE:
            profile, _ = NursePortalProfile.objects.update_or_create(
                interactive_core_user_id=profile_data["interactive_core_user_id"],
                defaults={**common, "interactive_core_employee_id": profile_data["interactive_core_employee_id"]},
            )
            id_key = "nurse_profile_id"
        else:
            raise ValueError(f"Rol no soportado para vincular un perfil: {role}")

        self._sync_country_access(user, role, country)
        return profile, id_key

    @transaction.atomic
    def activate_portal_access(self, role, profile_data, email, password):
        access_email = email or profile_data.get("email")
        user = self._create_or_update_user(profile_data, access_email, password)
        profile, id_key = self.link_portal_profile(user, role, profile_data, access_email)
        return {
            **self._token_payload(user),
            "roles": [role],
            id_key: profile.id,
        }
