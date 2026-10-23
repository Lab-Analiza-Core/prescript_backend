import logging
import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from api.models import Organization, OrganizationInvitation, TermsVersion
from api.roles import (
    PRESCRIPT_ROLE_DOCTOR,
    PRESCRIPT_ROLE_NURSE,
    PRESCRIPT_ROLE_ORG_ADMIN,
    PRESCRIPT_ROLE_PATIENT,
    PRESCRIPT_ROLE_SECRETARY,
)
from api.services.country_scope import is_global_admin_user

logger = logging.getLogger(__name__)

PROFILE_ROLES = {
    "doctor_portal_profile": PRESCRIPT_ROLE_DOCTOR,
    "secretary_portal_profile": PRESCRIPT_ROLE_SECRETARY,
    "nurse_portal_profile": PRESCRIPT_ROLE_NURSE,
    "org_admin_profile": PRESCRIPT_ROLE_ORG_ADMIN,
    "patient_portal_profile": PRESCRIPT_ROLE_PATIENT,
}

# Roles que un administrador de organizacion puede invitar. ORG_ADMIN solo lo emite el administrador global.
ORG_ADMIN_INVITABLE_ROLES = (
    PRESCRIPT_ROLE_DOCTOR,
    PRESCRIPT_ROLE_SECRETARY,
    PRESCRIPT_ROLE_NURSE,
    PRESCRIPT_ROLE_PATIENT,
)

# Sin caracteres ambiguos (0/O, 1/I) para que el codigo se dicte o copie sin errores.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def manageable_organization_ids(user):
    """None = todas las organizaciones (administrador global); lista = solo esas."""
    if is_global_admin_user(user):
        return None
    org_admin = getattr(user, "org_admin_profile", None)
    if org_admin and org_admin.status == "active" and org_admin.organization.status == "active":
        return [org_admin.organization_id]
    return []


def manageable_organizations(user):
    organization_ids = manageable_organization_ids(user)
    queryset = Organization.objects.select_related("country", "division", "medical_area")
    return queryset if organization_ids is None else queryset.filter(id__in=organization_ids)


def users_in_organizations(organization_ids=None):
    """Usuarios con perfil en las organizaciones indicadas (None = en cualquiera)."""
    condition = Q()
    for relation in PROFILE_ROLES:
        if organization_ids is None:
            condition |= Q(**{f"{relation}__organization__isnull": False})
        else:
            condition |= Q(**{f"{relation}__organization_id__in": organization_ids})
    return get_user_model().objects.filter(condition).distinct()


def get_member_profile(user):
    for relation, role in PROFILE_ROLES.items():
        profile = getattr(user, relation, None)
        if profile:
            return role, profile
    return None, None


def generate_invitation_code():
    while True:
        raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(10))
        code = f"{raw[:5]}-{raw[5:]}"
        if not OrganizationInvitation.objects.filter(code=code).exists():
            return code


@transaction.atomic
def set_member_active(user, is_active):
    """Activa o desactiva el acceso de un miembro, manteniendo coherente el estado de su perfil."""
    user.is_active = is_active
    user.save(update_fields=["is_active"])
    role, profile = get_member_profile(user)
    if profile is None or not hasattr(profile, "status"):
        return
    # Un administrador pendiente solo se activa por aprobacion explicita del administrador global.
    if role == PRESCRIPT_ROLE_ORG_ADMIN and profile.status == "pending":
        return
    profile.status = "active" if is_active else "inactive"
    profile.save(update_fields=["status", "updated_at"])


@transaction.atomic
def publish_terms(version, title, content):
    TermsVersion.objects.filter(is_current=True).update(is_current=False)
    return TermsVersion.objects.create(version=version, title=title, content=content, is_current=True)


def notify_org_admin_decision(profile, approved):
    """Avisa por correo la decision; un fallo del correo no debe deshacer la aprobacion."""
    email = profile.email or profile.user.email
    if not email:
        return
    if approved:
        subject = "Su cuenta de administrador fue aprobada"
        body = (
            f"Hola {profile.full_name},\n\nSu cuenta como administrador de {profile.organization.name} "
            "fue aprobada. Ya puede iniciar sesion en Prescript."
        )
    else:
        subject = "Su solicitud de administrador no fue aprobada"
        body = (
            f"Hola {profile.full_name},\n\nSu solicitud como administrador de {profile.organization.name} "
            "no fue aprobada. Comuniquese con el administrador global si cree que es un error."
        )
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)
    except Exception:
        logger.warning("No se pudo enviar la notificacion de decision al administrador.", exc_info=True)


def reject_org_admin(profile):
    with transaction.atomic():
        profile.status = "inactive"
        profile.approved_by = None
        profile.approved_at = None
        profile.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
        profile.user.is_active = False
        profile.user.save(update_fields=["is_active"])
    return profile
