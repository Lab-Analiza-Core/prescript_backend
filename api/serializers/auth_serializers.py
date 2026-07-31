from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from api.models import DoctorAccessLog, DoctorCredential, DoctorPortalProfile
from api.roles import PRESCRIPT_ROLE_DOCTOR
from api.services.interactive_core import InteractiveCoreDoctorService


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
