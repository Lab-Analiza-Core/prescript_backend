from api.roles import (
    PRESCRIPT_ROLE_ADMIN,
    PRESCRIPT_ROLE_DOCTOR,
    PRESCRIPT_ROLE_NURSE,
    PRESCRIPT_ROLE_SECRETARY,
    get_primary_prescript_role,
)


def get_current_prescript_role(user):
    role = get_primary_prescript_role(user.groups.values_list("name", flat=True))
    if role:
        return role
    if getattr(user, "doctor_portal_profile", None):
        return PRESCRIPT_ROLE_DOCTOR
    if getattr(user, "secretary_portal_profile", None):
        return PRESCRIPT_ROLE_SECRETARY
    if getattr(user, "nurse_portal_profile", None):
        return PRESCRIPT_ROLE_NURSE
    if user.is_staff or user.is_superuser:
        return PRESCRIPT_ROLE_ADMIN
    return ""
