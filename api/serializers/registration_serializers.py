import re

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db.models import Value
from django.db.models.functions import Replace
from rest_framework import serializers

from api.models import Patient, PatientPortalProfile, SpecialtyCatalogMirror
from api.roles import (
    PRESCRIPT_ROLE_DOCTOR,
    PRESCRIPT_ROLE_NURSE,
    PRESCRIPT_ROLE_ORG_ADMIN,
    PRESCRIPT_ROLE_PATIENT,
    PRESCRIPT_ROLE_SECRETARY,
)
from api.services.country_service import normalize_country_code
from api.services.organization_service import InvitationService
from api.services.registration_service import get_current_terms
from api.utils.field_validators import validate_and_format_phone

REGISTRATION_ROLES = (
    (PRESCRIPT_ROLE_DOCTOR, "Doctor"),
    (PRESCRIPT_ROLE_SECRETARY, "Secretaria"),
    (PRESCRIPT_ROLE_NURSE, "Enfermera"),
    (PRESCRIPT_ROLE_PATIENT, "Paciente"),
    (PRESCRIPT_ROLE_ORG_ADMIN, "Administrador de organizacion"),
)


def normalize_document(value):
    return re.sub(r"[\s\-.]", "", str(value or "")).upper()


class InvitationValidationSerializer(serializers.Serializer):
    invitation_code = serializers.CharField(max_length=32)

    def validate(self, attrs):
        attrs["invitation"] = InvitationService().get_valid(attrs["invitation_code"])
        return attrs

    def to_representation(self, instance):
        invitation = instance["invitation"]
        organization = invitation.organization
        division = organization.division
        return {
            "role": invitation.role,
            "organization": {
                "id": organization.id,
                "name": organization.name,
                "country": {"code": organization.country.code, "name": organization.country.name},
                "division": division.name if division else None,
                "division_type": division.division_type if division else None,
                "medical_areas": [medical_area.name for medical_area in organization.medical_areas.all()],
            },
        }


class ExternalRegistrationSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=REGISTRATION_ROLES)
    invitation_code = serializers.CharField(max_length=32)
    full_name = serializers.CharField(max_length=255)
    email = serializers.EmailField()
    phone = serializers.CharField(required=False, allow_blank=True, max_length=25)
    password = serializers.CharField(min_length=8, write_only=True)
    password_confirm = serializers.CharField(min_length=8, write_only=True)
    country = serializers.CharField(max_length=100)
    accept_terms = serializers.BooleanField()
    # Doctor
    colegiation_code = serializers.CharField(required=False, allow_blank=True, max_length=50)
    sex = serializers.ChoiceField(choices=["F", "M", "O"], required=False)
    specialty_ids = serializers.ListField(child=serializers.IntegerField(), required=False)
    # Paciente
    document_type = serializers.CharField(required=False, max_length=30, default="DNI")
    document_number = serializers.CharField(required=False, max_length=50)

    def validate_email(self, value):
        user_model = get_user_model()
        if (
            user_model.objects.filter(email__iexact=value).exists()
            or user_model.objects.filter(username__iexact=value).exists()
        ):
            raise serializers.ValidationError("Ya existe una cuenta con este correo.")
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Las contrasenas no coinciden."})
        validate_password(attrs["password"])

        terms = get_current_terms()
        if terms is None:
            raise serializers.ValidationError({"accept_terms": "Los terminos y condiciones aun no estan publicados."})
        if not attrs["accept_terms"]:
            raise serializers.ValidationError({"accept_terms": "Debe aceptar los terminos y condiciones."})
        attrs["terms"] = terms

        role = attrs["role"]
        invitation = InvitationService().get_valid(attrs["invitation_code"], role=role)
        country = invitation.organization.country
        if normalize_country_code(attrs["country"]) != country.code:
            raise serializers.ValidationError({"country": "El pais no coincide con el de la organizacion."})

        attrs["phone"] = validate_and_format_phone(attrs.get("phone"), country=country)

        if role == PRESCRIPT_ROLE_DOCTOR:
            if not attrs.get("colegiation_code", "").strip():
                raise serializers.ValidationError({"colegiation_code": "El codigo de colegiacion es obligatorio."})
            specialty_ids = set(attrs.get("specialty_ids") or [])
            specialties = list(
                SpecialtyCatalogMirror.objects.filter(id__in=specialty_ids, country=country, is_active=True)
            )
            if len(specialties) != len(specialty_ids):
                raise serializers.ValidationError({"specialty_ids": "Hay especialidades invalidas para este pais."})
            attrs["specialty_objects"] = specialties

        if role == PRESCRIPT_ROLE_PATIENT:
            document = normalize_document(attrs.get("document_number"))
            if not document:
                raise serializers.ValidationError({"document_number": "El documento es obligatorio."})
            attrs["document_number"] = document
            attrs["document_type"] = (attrs.get("document_type") or "DNI").upper()
            if PatientPortalProfile.objects.filter(
                country=country, document_type=attrs["document_type"], document_number=document
            ).exists():
                raise serializers.ValidationError({"document_number": "Ya existe una cuenta con este documento."})
        return attrs


class PatientHistoryVerifySerializer(serializers.Serializer):
    code = serializers.CharField(max_length=10)


def find_patient_records(profile):
    """Fichas clinicas del pais cuyo documento coincide con la cuenta."""
    normalized = Replace(Replace(Replace("dni", Value("-"), Value("")), Value(" "), Value("")), Value("."), Value(""))
    return Patient.objects.annotate(normalized_dni=normalized).filter(
        normalized_dni__iexact=profile.document_number,
        doctor__country=profile.country,
        is_active=True,
    )
