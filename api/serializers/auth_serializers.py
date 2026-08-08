from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.models import Group
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from api.models import DoctorAccessLog, DoctorCredential, DoctorPortalProfile, NursePortalProfile, SecretaryPortalProfile
from api.roles import PRESCRIPT_ROLE_DOCTOR, PRESCRIPT_ROLE_NURSE, PRESCRIPT_ROLE_SECRETARY
from api.services.interactive_core import InteractiveCoreAccessService, InteractiveCoreDoctorService
from api.utils.field_validators import validate_and_format_phone


def get_user_portal_profile(user):
    for attribute in ("doctor_portal_profile", "secretary_portal_profile", "nurse_portal_profile"):
        profile = getattr(user, attribute, None)
        if profile:
            return profile
    return None


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    email = serializers.EmailField(required=False, write_only=True)
    username = serializers.CharField(required=False, write_only=True)
    password = serializers.CharField(write_only=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.username_field in self.fields:
            self.fields[self.username_field].required = False

    def validate(self, attrs):
        identifier = attrs.get("email") or attrs.get("username")
        password = attrs.get("password")

        if not identifier:
            raise serializers.ValidationError(
                {"detail": "Ingrese usuario o correo."},
                code="authorization",
            )

        user_model = get_user_model()
        if "@" in identifier:
            user = user_model.objects.filter(email__iexact=identifier).first()
        else:
            user = user_model.objects.filter(username__iexact=identifier).first()

        if user is None:
            raise serializers.ValidationError(
                {"detail": "No se encontro una cuenta activa con estas credenciales."},
                code="authorization",
            )

        attrs[self.username_field] = user.get_username()
        attrs["password"] = password
        return super().validate(attrs)


class DoctorActivationSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=254, write_only=True)
    email = serializers.EmailField(required=False, write_only=True)
    password = serializers.CharField(min_length=8, write_only=True)
    password_confirm = serializers.CharField(min_length=8, write_only=True)

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Las contrasenas no coinciden."})

        doctor = InteractiveCoreDoctorService().lookup_doctor(attrs["identifier"].strip())
        if doctor is None:
            raise serializers.ValidationError({"identifier": "No se encontro el doctor en Interactive Core."})

        if doctor.get("status") != "active":
            raise serializers.ValidationError({"identifier": "El doctor no esta activo en Interactive Core."})

        if not doctor.get("has_doctor_role"):
            raise serializers.ValidationError({"identifier": "El usuario no tiene rol de doctor en Interactive Core."})

        attrs["interactive_core_doctor"] = doctor
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        doctor_data = validated_data["interactive_core_doctor"]
        email = validated_data.get("email") or doctor_data.get("email")
        if not email:
            raise serializers.ValidationError({"email": "Se requiere correo para crear credenciales."})

        username = email.lower()
        user_model = get_user_model()
        user, _ = user_model.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "first_name": doctor_data.get("full_name", "")[:150],
                "is_active": True,
            },
        )
        user.email = email
        user.is_active = True
        user.set_password(validated_data["password"])
        user.save(update_fields=["email", "is_active", "password"])
        portal_roles = doctor_data.get("prescript_roles") or [PRESCRIPT_ROLE_DOCTOR]
        for role in portal_roles:
            group, _ = Group.objects.get_or_create(name=role)
            user.groups.add(group)

        profile, _ = DoctorPortalProfile.objects.update_or_create(
            interactive_core_doctor_id=doctor_data["id"],
            defaults={
                "user": user,
                "full_name": doctor_data.get("full_name") or username,
                "colegiation_code": doctor_data.get("colegiation_code"),
                "qualification_code": doctor_data.get("qualification_code"),
                "final_score": doctor_data.get("final_score"),
                "phone": doctor_data.get("phone"),
                "public_email": email,
                "specialties": doctor_data.get("specialties") or [],
                "is_top_doctor": doctor_data.get("is_top_doctor", False),
                "status": "active",
                "last_synced_at": timezone.now(),
            },
        )

        credential, _ = DoctorCredential.objects.update_or_create(
            doctor=profile,
            defaults={
                "username": username,
                "email": email,
                "is_portal_enabled": True,
                "password_set_at": timezone.now(),
                "last_password_change_at": timezone.now(),
            },
        )

        DoctorAccessLog.objects.create(
            doctor=profile,
            event_type="password_set",
            metadata={"source": "doctor_activation"},
        )

        refresh = RefreshToken.for_user(user)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "doctor_profile_id": profile.id,
            "credential_id": credential.id,
            "roles": portal_roles,
        }


class PortalAccessActivationSerializer(serializers.Serializer):
    ROLE_CHOICES = (
        (PRESCRIPT_ROLE_DOCTOR, "Doctor"),
        (PRESCRIPT_ROLE_NURSE, "Enfermera"),
        (PRESCRIPT_ROLE_SECRETARY, "Secretaria"),
    )

    role = serializers.ChoiceField(choices=ROLE_CHOICES)
    identifier = serializers.CharField(max_length=254, write_only=True)
    email = serializers.EmailField(required=False, write_only=True)
    password = serializers.CharField(min_length=8, write_only=True)
    password_confirm = serializers.CharField(min_length=8, write_only=True)

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Las contrasenas no coinciden."})

        role = attrs["role"]
        profile = InteractiveCoreAccessService().lookup(role, attrs["identifier"].strip())
        if profile is None:
            raise serializers.ValidationError({"identifier": "No se encontro un registro activo para este rol en Interactive Core."})

        if role == PRESCRIPT_ROLE_DOCTOR and profile.get("status") != "active":
            raise serializers.ValidationError({"identifier": "El doctor no esta activo en Interactive Core."})

        attrs["interactive_core_profile"] = profile
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        role = validated_data["role"]
        profile_data = validated_data["interactive_core_profile"]
        email = validated_data.get("email") or profile_data.get("email")
        if not email:
            raise serializers.ValidationError({"email": "Se requiere correo para crear credenciales."})

        username = email.lower()
        user_model = get_user_model()
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
        user.set_password(validated_data["password"])
        user.save(update_fields=["email", "is_active", "password"])

        group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(group)

        response_ids = {}
        if role == PRESCRIPT_ROLE_DOCTOR:
            profile, _ = DoctorPortalProfile.objects.update_or_create(
                interactive_core_doctor_id=profile_data["id"],
                defaults={
                    "user": user,
                    "full_name": profile_data.get("full_name") or username,
                    "colegiation_code": profile_data.get("colegiation_code"),
                    "qualification_code": profile_data.get("qualification_code"),
                    "final_score": profile_data.get("final_score"),
                    "phone": profile_data.get("phone"),
                    "public_email": email,
                    "specialties": profile_data.get("specialties") or [],
                    "is_top_doctor": profile_data.get("is_top_doctor", False),
                    "status": "active",
                    "last_synced_at": timezone.now(),
                },
            )
            DoctorCredential.objects.update_or_create(
                doctor=profile,
                defaults={
                    "username": username,
                    "email": email,
                    "is_portal_enabled": True,
                    "password_set_at": timezone.now(),
                    "last_password_change_at": timezone.now(),
                },
            )
            response_ids["doctor_profile_id"] = profile.id
        elif role == PRESCRIPT_ROLE_SECRETARY:
            profile, _ = SecretaryPortalProfile.objects.update_or_create(
                secretaria_interactivecore_id=profile_data["id"],
                defaults={
                    "user": user,
                    "full_name": profile_data.get("full_name") or username,
                    "email": email,
                    "phone": profile_data.get("phone"),
                    "country": profile_data.get("country"),
                    "status": "active",
                    "last_synced_at": timezone.now(),
                },
            )
            response_ids["secretary_profile_id"] = profile.id
        elif role == PRESCRIPT_ROLE_NURSE:
            profile, _ = NursePortalProfile.objects.update_or_create(
                interactive_core_user_id=profile_data["interactive_core_user_id"],
                defaults={
                    "user": user,
                    "interactive_core_employee_id": profile_data["interactive_core_employee_id"],
                    "full_name": profile_data.get("full_name") or username,
                    "email": email,
                    "phone": profile_data.get("phone"),
                    "country": profile_data.get("country"),
                    "status": "active",
                    "last_synced_at": timezone.now(),
                },
            )
            response_ids["nurse_profile_id"] = profile.id

        refresh = RefreshToken.for_user(user)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "roles": [role],
            **response_ids,
        }


class UserProfileUpdateSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)
    phone = serializers.CharField(required=False, allow_blank=True, max_length=25)
    current_password = serializers.CharField(required=False, write_only=True)
    new_password = serializers.CharField(required=False, write_only=True, min_length=8)
    password_confirm = serializers.CharField(required=False, write_only=True, min_length=8)

    def validate_email(self, value):
        user = self.context["request"].user
        user_model = get_user_model()
        if user_model.objects.filter(email__iexact=value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("Este correo ya esta en uso.")
        normalized_value = value.lower()
        if user_model.objects.filter(username__iexact=normalized_value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("Este correo ya esta en uso como usuario.")
        return normalized_value

    def validate_phone(self, value):
        user = self.context["request"].user
        profile = get_user_portal_profile(user)
        country = getattr(profile, "country", None) or "HN"
        return validate_and_format_phone(value, country=country)

    def validate(self, attrs):
        new_password = attrs.get("new_password")
        password_confirm = attrs.get("password_confirm")

        if new_password or password_confirm:
            if not new_password:
                raise serializers.ValidationError({"new_password": "Ingrese la nueva contrasena."})
            if not password_confirm:
                raise serializers.ValidationError({"password_confirm": "Confirme la nueva contrasena."})
            if new_password != password_confirm:
                raise serializers.ValidationError({"password_confirm": "Las contrasenas no coinciden."})
            user = self.context["request"].user
            validate_password(new_password, user=user)

        return attrs

    @transaction.atomic
    def update(self, instance, validated_data):
        user = instance
        email = validated_data.get("email")
        phone = validated_data.get("phone")
        new_password = validated_data.get("new_password")
        user_update_fields = []

        if email is not None:
            user.email = email
            user.username = email
            user_update_fields.extend(["email", "username"])

        if new_password:
            user.set_password(new_password)
            user_update_fields.append("password")

        if user_update_fields:
            user.save(update_fields=list(dict.fromkeys(user_update_fields)))

        profile = get_user_portal_profile(user)
        if profile:
            profile_update_fields = []
            if phone is not None and hasattr(profile, "phone"):
                profile.phone = phone.strip() or None
                profile_update_fields.append("phone")
            if email is not None:
                if hasattr(profile, "email"):
                    profile.email = email
                    profile_update_fields.append("email")
                if hasattr(profile, "public_email"):
                    profile.public_email = email
                    profile_update_fields.append("public_email")
            if profile_update_fields:
                profile.save(update_fields=list(dict.fromkeys(profile_update_fields + ["updated_at"])))

        doctor = getattr(user, "doctor_portal_profile", None)
        if doctor and (email is not None or new_password):
            credential_updates = {
                "email": user.email,
                "username": user.username,
            }
            if new_password:
                credential_updates["last_password_change_at"] = timezone.now()
            DoctorCredential.objects.filter(doctor=doctor).update(**credential_updates)

        return user
