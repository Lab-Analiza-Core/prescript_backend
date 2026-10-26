from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from api.models import DoctorCredential
from api.services.interactive_core import InteractiveCoreAccessService
from api.services.organization_scope import get_access_block_reason
from api.utils.field_validators import validate_and_format_phone
import logging


logger = logging.getLogger(__name__)


def get_user_portal_profile(user):
    for attribute in (
        "doctor_portal_profile",
        "secretary_portal_profile",
        "nurse_portal_profile",
        "org_admin_profile",
        "patient_portal_profile",
    ):
        profile = getattr(user, attribute, None)
        if profile:
            return profile
    return None


AFFILIATION_PENDING_MESSAGE = "Su solicitud de afiliacion esta en revision. Le avisaremos por correo cuando se apruebe."
AFFILIATION_REJECTED_MESSAGE = "Su solicitud de afiliacion no fue aprobada. Contacte a su administrador."


def get_affiliation_review_message(user):
    """Solo para cuentas inactivas con una solicitud de afiliacion sin aprobar."""
    if user.is_active:
        return ""
    request = getattr(user, "affiliation_request", None)
    if request is None or request.status == "approved":
        return ""
    return AFFILIATION_PENDING_MESSAGE if request.status == "pending" else AFFILIATION_REJECTED_MESSAGE


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

        review_message = get_affiliation_review_message(user)
        if review_message:
            raise serializers.ValidationError({"detail": review_message}, code="authorization")

        attrs[self.username_field] = user.get_username()
        attrs["password"] = password
        payload = super().validate(attrs)
        block_reason = get_access_block_reason(self.user)
        if block_reason:
            raise serializers.ValidationError({"detail": block_reason}, code="authorization")
        try:
            InteractiveCoreAccessService().sync_user_workspaces(self.user)
        except Exception as exc:
            if exc.__class__.__name__ != "DatabaseOperationForbidden":
                logger.warning("No se pudieron sincronizar los workspaces de Interactive Core.", exc_info=True)
        return payload


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
            current_password = attrs.get("current_password")
            if not current_password:
                raise serializers.ValidationError({"current_password": "Ingrese su contrasena actual."})
            if not user.check_password(current_password):
                raise serializers.ValidationError({"current_password": "La contrasena actual es incorrecta."})
            if new_password == current_password:
                raise serializers.ValidationError({"new_password": "La nueva contrasena debe ser distinta de la actual."})
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
