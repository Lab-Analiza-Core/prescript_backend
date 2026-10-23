from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from api.models import (
    DoctorAccessLog,
    DoctorCredential,
    DoctorPortalProfile,
    NursePortalProfile,
    OrganizationAdminProfile,
    PatientPortalProfile,
    SecretaryPortalProfile,
    TermsAcceptance,
    TermsVersion,
    UserCountryAccess,
)
from api.models.organization_models import ORIGIN_SELF_REGISTERED
from api.roles import (
    PRESCRIPT_ROLE_DOCTOR,
    PRESCRIPT_ROLE_NURSE,
    PRESCRIPT_ROLE_PATIENT,
    PRESCRIPT_ROLE_SECRETARY,
)
from api.services.organization_service import InvitationService


def get_current_terms():
    return TermsVersion.objects.filter(is_current=True).first()


def record_terms_acceptance(user, terms, ip_address=None):
    if terms is None:
        return None
    acceptance, _ = TermsAcceptance.objects.get_or_create(
        user=user, terms=terms, defaults={"ip_address": ip_address}
    )
    return acceptance


class ExternalRegistrationService:
    """Registro por codigo de invitacion, sin depender de Interactive Core."""

    @transaction.atomic
    def register(self, data, ip_address=None):
        role = data["role"]
        invitation = InvitationService().get_valid(data["invitation_code"], role=role, lock=True)
        organization = invitation.organization
        country = organization.country
        email = data["email"].strip()

        user = get_user_model().objects.create_user(
            username=email.lower(),
            email=email,
            password=data["password"],
            first_name=data["full_name"][:150],
            is_active=True,
        )
        group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(group)

        common = {
            "user": user,
            "organization": organization,
            "full_name": data["full_name"],
            "country": country,
        }
        extra_ids = {}
        pending = False

        if role == PRESCRIPT_ROLE_DOCTOR:
            profile = DoctorPortalProfile.objects.create(
                user=user,
                organization=organization,
                origin=ORIGIN_SELF_REGISTERED,
                full_name=data["full_name"],
                country=country,
                colegiation_code=data.get("colegiation_code") or None,
                phone=data.get("phone"),
                public_email=email,
                sex=data.get("sex") or None,
                specialties=[
                    {"id": specialty.interactive_core_id, "name": specialty.name}
                    for specialty in data.get("specialty_objects", [])
                ],
                status="active",
            )
            DoctorCredential.objects.create(
                doctor=profile,
                username=email.lower(),
                email=email,
                is_portal_enabled=True,
                password_set_at=timezone.now(),
                last_password_change_at=timezone.now(),
            )
            DoctorAccessLog.objects.create(
                doctor=profile, event_type="password_set", metadata={"source": "self_registration"}
            )
            extra_ids["doctor_profile_id"] = profile.id
        elif role == PRESCRIPT_ROLE_SECRETARY:
            profile = SecretaryPortalProfile.objects.create(
                origin=ORIGIN_SELF_REGISTERED, email=email, phone=data.get("phone"), status="active", **common
            )
            extra_ids["secretary_profile_id"] = profile.id
        elif role == PRESCRIPT_ROLE_NURSE:
            profile = NursePortalProfile.objects.create(
                origin=ORIGIN_SELF_REGISTERED, email=email, phone=data.get("phone"), status="active", **common
            )
            extra_ids["nurse_profile_id"] = profile.id
        elif role == PRESCRIPT_ROLE_PATIENT:
            profile = PatientPortalProfile.objects.create(
                email=email,
                phone=data.get("phone"),
                document_type=data["document_type"],
                document_number=data["document_number"],
                status="active",
                **common,
            )
            extra_ids["patient_profile_id"] = profile.id
        else:
            profile = OrganizationAdminProfile.objects.create(
                email=email, phone=data.get("phone"), status="pending", **common
            )
            extra_ids["org_admin_profile_id"] = profile.id
            pending = True

        UserCountryAccess.objects.update_or_create(
            user=user, role_code=role, country=country, defaults={"is_active": True, "source": "self_registration"}
        )
        record_terms_acceptance(user, data["terms"], ip_address)
        InvitationService().consume(invitation)

        payload = {
            "roles": [role],
            "organization_id": organization.id,
            "is_external": True,
            "pending_approval": pending,
            **extra_ids,
        }
        if not pending:
            refresh = RefreshToken.for_user(user)
            payload.update({"access": str(refresh.access_token), "refresh": str(refresh)})
        return payload
