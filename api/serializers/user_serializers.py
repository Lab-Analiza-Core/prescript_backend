from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers

from api.roles import PRESCRIPT_ROLE_CHOICES
from api.services.admin_user_service import (
    create_admin_user,
    generate_temporary_password,
    reset_user_password,
    update_admin_user,
)
from api.services.role_access import get_current_prescript_role


ROLE_CHOICES = [(role, role) for role in PRESCRIPT_ROLE_CHOICES]


def get_user_profile_summary(user):
    profile_map = (
        ("doctor", getattr(user, "doctor_portal_profile", None)),
        ("secretary", getattr(user, "secretary_portal_profile", None)),
        ("nurse", getattr(user, "nurse_portal_profile", None)),
    )
    for profile_type, profile in profile_map:
        if profile:
            return {
                "type": profile_type,
                "full_name": getattr(profile, "full_name", ""),
                "phone": getattr(profile, "phone", "") or "",
                "country": getattr(profile, "country", "") or "",
                "status": getattr(profile, "status", "") or "",
            }
    return None


class AdminUserSerializer(serializers.ModelSerializer):
    roles = serializers.ListField(
        child=serializers.ChoiceField(choices=ROLE_CHOICES),
        required=False,
        allow_empty=True,
    )
    password = serializers.CharField(write_only=True, required=False, allow_blank=True, min_length=8)
    full_name = serializers.SerializerMethodField()
    primary_role = serializers.SerializerMethodField()
    profile = serializers.SerializerMethodField()

    class Meta:
        model = get_user_model()
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "roles",
            "primary_role",
            "profile",
            "is_active",
            "is_staff",
            "is_superuser",
            "last_login",
            "date_joined",
            "password",
        ]
        read_only_fields = ["id", "full_name", "primary_role", "profile", "is_superuser", "last_login", "date_joined"]

    def get_full_name(self, user):
        profile = get_user_profile_summary(user)
        return (profile or {}).get("full_name") or user.get_full_name() or user.username

    def get_primary_role(self, user):
        return get_current_prescript_role(user)

    def get_profile(self, user):
        return get_user_profile_summary(user)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["roles"] = list(instance.groups.values_list("name", flat=True))
        return data

    def validate_email(self, value):
        email = value.strip().lower()
        user_model = get_user_model()
        queryset = user_model.objects.filter(email__iexact=email)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("Este correo ya esta en uso.")
        return email

    def validate_username(self, value):
        username = value.strip()
        user_model = get_user_model()
        queryset = user_model.objects.filter(username__iexact=username)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("Este usuario ya existe.")
        return username

    def validate_password(self, value):
        if value:
            validate_password(value, user=self.instance)
        return value

    def validate(self, attrs):
        if not self.instance and not attrs.get("password"):
            raise serializers.ValidationError({"password": "Ingrese una contrasena temporal."})
        if not attrs.get("username") and attrs.get("email"):
            attrs["username"] = attrs["email"]
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        return create_admin_user(get_user_model(), validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        return update_admin_user(instance, validated_data)


class UserPasswordResetSerializer(serializers.Serializer):
    password = serializers.CharField(min_length=8, required=False, allow_blank=True, write_only=True)

    def validate_password(self, value):
        if value:
            validate_password(value, user=self.context["user"])
        return value

    def save(self, **kwargs):
        user = self.context["user"]
        password = self.validated_data.get("password") or generate_temporary_password()
        validate_password(password, user=user)
        return reset_user_password(user, password)
