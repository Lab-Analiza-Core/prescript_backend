from django.utils import timezone
from rest_framework import serializers

from api.models import (
    CountryDivision,
    Organization,
    OrganizationAdminProfile,
    OrganizationInvitation,
    SecretaryDoctorAssignment,
    SpecialtyCatalogMirror,
    TermsVersion,
)
from api.services.organization_admin_service import (
    ORG_ADMIN_INVITABLE_ROLES,
    get_member_profile,
    manageable_organization_ids,
)


class OrganizationSerializer(serializers.ModelSerializer):
    country_code = serializers.CharField(source="country.code", read_only=True)
    country_name = serializers.CharField(source="country.name", read_only=True)
    division_name = serializers.CharField(source="division.name", read_only=True, default=None)
    division_type = serializers.CharField(source="division.division_type", read_only=True, default=None)
    medical_area_name = serializers.CharField(source="medical_area.name", read_only=True, default=None)

    class Meta:
        model = Organization
        fields = [
            "id",
            "name",
            "country",
            "country_code",
            "country_name",
            "division",
            "division_name",
            "division_type",
            "medical_area",
            "medical_area_name",
            "status",
            "is_interactive_core",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "is_interactive_core", "created_at", "updated_at"]

    def validate(self, attrs):
        instance = self.instance
        country = attrs.get("country", instance.country if instance else None)
        if instance and country != instance.country:
            raise serializers.ValidationError(
                {"country": "El pais de una organizacion no se puede cambiar: sus usuarios pertenecen a ese pais."}
            )
        if country is None:
            raise serializers.ValidationError({"country": "El pais es obligatorio."})
        if not country.is_active:
            raise serializers.ValidationError({"country": "El pais no esta activo."})

        division = attrs.get("division", instance.division if instance else None)
        if division and (division.country_id != country.id or not division.is_active):
            raise serializers.ValidationError({"division": "La division no pertenece al pais seleccionado."})

        medical_area = attrs.get("medical_area", instance.medical_area if instance else None)
        if medical_area and (medical_area.country_id != country.id or not medical_area.is_active):
            raise serializers.ValidationError({"medical_area": "El area medica no pertenece al pais seleccionado."})

        name = attrs.get("name", instance.name if instance else "").strip()
        attrs["name"] = name
        duplicates = Organization.objects.filter(country=country, name__iexact=name)
        if instance:
            duplicates = duplicates.exclude(pk=instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError({"name": "Ya existe una organizacion con este nombre en el pais."})

        if instance and instance.is_interactive_core and attrs.get("status") == "suspended":
            raise serializers.ValidationError(
                {"status": "No se puede suspender la organizacion de Interactive Core: bloquearia a todo su personal."}
            )
        return attrs


class OrganizationInvitationSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.name", read_only=True)

    class Meta:
        model = OrganizationInvitation
        fields = [
            "id",
            "organization",
            "organization_name",
            "code",
            "role",
            "expires_at",
            "max_uses",
            "uses",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "organization", "code", "uses", "created_at"]

    def validate_expires_at(self, value):
        if value is not None and value <= timezone.now():
            raise serializers.ValidationError("La fecha de vencimiento debe ser futura.")
        return value

    def validate_max_uses(self, value):
        if value is not None and value < 1:
            raise serializers.ValidationError("El limite de usos debe ser al menos 1.")
        return value

    def validate_role(self, value):
        user = self.context["request"].user
        if manageable_organization_ids(user) is not None and value not in ORG_ADMIN_INVITABLE_ROLES:
            raise serializers.ValidationError("Solo el administrador global puede invitar administradores.")
        return value

    def validate(self, attrs):
        if self.instance and "role" in attrs and attrs["role"] != self.instance.role:
            raise serializers.ValidationError({"role": "El rol de una invitacion no se puede cambiar; cree otra."})
        max_uses = attrs.get("max_uses", self.instance.max_uses if self.instance else None)
        if self.instance and max_uses is not None and max_uses < self.instance.uses:
            raise serializers.ValidationError({"max_uses": "El limite no puede ser menor a los usos ya registrados."})
        return attrs


class SecretaryAssignmentSerializer(serializers.ModelSerializer):
    secretary_name = serializers.CharField(source="secretary.full_name", read_only=True)
    doctor_name = serializers.CharField(source="doctor.full_name", read_only=True)

    class Meta:
        model = SecretaryDoctorAssignment
        fields = ["id", "secretary", "secretary_name", "doctor", "doctor_name", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate(self, attrs):
        secretary, doctor = attrs["secretary"], attrs["doctor"]
        if not secretary.organization_id or secretary.organization_id != doctor.organization_id:
            raise serializers.ValidationError(
                "La secretaria y el doctor deben pertenecer a la misma organizacion."
            )
        allowed = manageable_organization_ids(self.context["request"].user)
        if allowed is not None and secretary.organization_id not in allowed:
            raise serializers.ValidationError("No puede gestionar vinculos de otra organizacion.")
        if SecretaryDoctorAssignment.objects.filter(secretary=secretary, doctor=doctor).exists():
            raise serializers.ValidationError("La secretaria ya esta vinculada a este doctor.")
        return attrs


class TermsVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TermsVersion
        fields = ["id", "version", "title", "content", "is_current", "published_at"]
        read_only_fields = ["id", "is_current", "published_at"]


class MemberStatusSerializer(serializers.Serializer):
    is_active = serializers.BooleanField()


class OrgAdminProfileSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    country_code = serializers.CharField(source="country.code", read_only=True)

    class Meta:
        model = OrganizationAdminProfile
        fields = [
            "id",
            "full_name",
            "email",
            "phone",
            "organization",
            "organization_name",
            "country_code",
            "status",
            "approved_at",
            "created_at",
        ]
        read_only_fields = fields


def serialize_member(user):
    role, profile = get_member_profile(user)
    organization = getattr(profile, "organization", None)
    return {
        "id": user.id,
        "profile_id": profile.id if profile else None,
        "username": user.username,
        "email": user.email,
        "full_name": getattr(profile, "full_name", None) or user.get_full_name() or user.username,
        "role": role,
        "is_active": user.is_active,
        "profile_status": getattr(profile, "status", None),
        "is_external": getattr(profile, "origin", None) == "self_registered" or role in {"ORG_ADMIN", "PATIENT"},
        "organization": {"id": organization.id, "name": organization.name} if organization else None,
    }


class PublicDivisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CountryDivision
        fields = ["id", "name", "division_type"]


class PublicSpecialtySerializer(serializers.ModelSerializer):
    class Meta:
        model = SpecialtyCatalogMirror
        fields = ["id", "name"]


__all__ = [
    "MemberStatusSerializer",
    "OrgAdminProfileSerializer",
    "OrganizationInvitationSerializer",
    "OrganizationSerializer",
    "PublicDivisionSerializer",
    "PublicSpecialtySerializer",
    "SecretaryAssignmentSerializer",
    "TermsVersionSerializer",
    "serialize_member",
]
