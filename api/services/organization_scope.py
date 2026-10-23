from dataclasses import dataclass

from django.db.models import Q

from api.models import Organization
from api.services.country_scope import is_global_admin_user

PROFILE_ATTRIBUTES = ("doctor_portal_profile", "secretary_portal_profile", "nurse_portal_profile")

PENDING_ADMIN_MESSAGE = "Su cuenta de administrador esta pendiente de aprobacion."
INACTIVE_ADMIN_MESSAGE = "Su cuenta de administrador esta desactivada."
SUSPENDED_ORGANIZATION_MESSAGE = "La organizacion a la que pertenece esta suspendida."


@dataclass(frozen=True)
class OrganizationScope:
    """Limita los datos visibles a la organizacion del usuario.

    - unrestricted: administrador global.
    - organization_id: usuario (o admin de organizacion) de una organizacion concreta.
    - interactive_core_only: personal de Interactive Core; ve las organizaciones de IC (y
      registros antiguos sin organizacion), nunca las de organizaciones externas.
    - sin ninguno de los tres: no ve nada.
    """

    unrestricted: bool = False
    organization_id: int | None = None
    interactive_core_only: bool = False

    def filter(self, queryset, field="organization"):
        if self.unrestricted:
            return queryset
        if self.organization_id:
            return queryset.filter(**{f"{field}_id": self.organization_id})
        if self.interactive_core_only:
            return queryset.filter(Q(**{f"{field}__isnull": True}) | Q(**{f"{field}__is_interactive_core": True}))
        return queryset.none()

    def allows_organization(self, organization_id):
        if self.unrestricted:
            return True
        if self.organization_id:
            return organization_id == self.organization_id
        if self.interactive_core_only:
            return organization_id is None or Organization.objects.filter(
                pk=organization_id, is_interactive_core=True
            ).exists()
        return False


def _scope_for_profile_organization(profile):
    organization = profile.organization
    if organization is None:
        return OrganizationScope(interactive_core_only=True)
    if organization.status != "active":
        return OrganizationScope()
    return OrganizationScope(organization_id=organization.id)


def get_organization_scope(user):
    if not user or not user.is_authenticated:
        return OrganizationScope()
    if is_global_admin_user(user):
        return OrganizationScope(unrestricted=True)

    org_admin = getattr(user, "org_admin_profile", None)
    if org_admin:
        if org_admin.status != "active":
            return OrganizationScope()
        return _scope_for_profile_organization(org_admin)

    for attribute in PROFILE_ATTRIBUTES:
        profile = getattr(user, attribute, None)
        if profile:
            return _scope_for_profile_organization(profile)

    if getattr(user, "patient_portal_profile", None):
        return OrganizationScope()
    # Administradores por pais y gerentes de Interactive Core sin perfil de portal.
    return OrganizationScope(interactive_core_only=True)


def get_access_block_reason(user):
    """Motivo por el que una cuenta con credenciales validas no puede ingresar."""
    if is_global_admin_user(user):
        return ""
    org_admin = getattr(user, "org_admin_profile", None)
    if org_admin:
        if org_admin.status == "pending":
            return PENDING_ADMIN_MESSAGE
        if org_admin.status != "active":
            return INACTIVE_ADMIN_MESSAGE
    for attribute in (*PROFILE_ATTRIBUTES, "org_admin_profile", "patient_portal_profile"):
        profile = getattr(user, attribute, None)
        organization = getattr(profile, "organization", None) if profile else None
        if organization is not None and organization.status != "active":
            return SUSPENDED_ORGANIZATION_MESSAGE
    return ""
