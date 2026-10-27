from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from api.models import Organization, OrganizationInvitation
from api.roles import PRESCRIPT_ROLE_ORG_ADMIN

INVALID_INVITATION_MESSAGE = "El codigo de invitacion no es valido, vencio o ya no tiene usos disponibles."


class InvitationService:
    def get_valid(self, code, role=None, lock=False):
        queryset = (
            OrganizationInvitation.objects.select_related(
                "organization__country", "organization__division"
            )
            .prefetch_related("organization__medical_areas")
            .filter(code=str(code or "").strip().upper(), is_active=True, organization__status="active")
        )
        if lock:
            queryset = queryset.select_for_update(of=("self",))
        invitation = queryset.first()
        now = timezone.now()
        if (
            invitation is None
            or (role and invitation.role != role)
            or (invitation.expires_at and invitation.expires_at <= now)
            or (invitation.max_uses is not None and invitation.uses >= invitation.max_uses)
        ):
            raise serializers.ValidationError({"invitation_code": INVALID_INVITATION_MESSAGE})
        return invitation

    def consume(self, invitation):
        invitation.uses += 1
        invitation.save(update_fields=["uses"])


class OrganizationAdminService:
    @transaction.atomic
    def approve(self, profile, approver):
        profile.status = "active"
        profile.approved_by = approver
        profile.approved_at = timezone.now()
        profile.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
        return profile

    @transaction.atomic
    def deactivate(self, profile):
        profile.status = "inactive"
        profile.save(update_fields=["status", "updated_at"])
        return profile

    @staticmethod
    def is_org_admin_role(role):
        return role == PRESCRIPT_ROLE_ORG_ADMIN


def get_interactive_core_organization(country):
    """Organizacion que recibe a los afiliados a Interactive Core de un pais."""
    if country is None:
        return None
    return Organization.objects.filter(country=country, is_interactive_core=True).first()
