PRESCRIPT_ROLE_DOCTOR = "DOCTOR"
PRESCRIPT_ROLE_SECRETARY = "SECRETARY"
PRESCRIPT_ROLE_NURSE = "NURSE"
PRESCRIPT_ROLE_ADMIN = "ADMIN"
PRESCRIPT_ROLE_MANAGER = "COUNTRY_MANAGER"
PRESCRIPT_ROLE_ORG_ADMIN = "ORG_ADMIN"
PRESCRIPT_ROLE_PATIENT = "PATIENT"
COUNTRY_ADMIN_ROLE_PREFIX = "ADMIN_"

PRESCRIPT_ROLE_CHOICES = (
    PRESCRIPT_ROLE_DOCTOR,
    PRESCRIPT_ROLE_SECRETARY,
    PRESCRIPT_ROLE_NURSE,
    PRESCRIPT_ROLE_ADMIN,
    PRESCRIPT_ROLE_MANAGER,
    PRESCRIPT_ROLE_ORG_ADMIN,
    PRESCRIPT_ROLE_PATIENT,
)

PRESCRIPT_ROLE_PRIORITY = (
    PRESCRIPT_ROLE_ADMIN,
    PRESCRIPT_ROLE_MANAGER,
    PRESCRIPT_ROLE_ORG_ADMIN,
    PRESCRIPT_ROLE_DOCTOR,
    PRESCRIPT_ROLE_NURSE,
    PRESCRIPT_ROLE_SECRETARY,
    PRESCRIPT_ROLE_PATIENT,
)

ROLE_ALIASES = {
    "doctor": PRESCRIPT_ROLE_DOCTOR,
    "doctors": PRESCRIPT_ROLE_DOCTOR,
    "medico": PRESCRIPT_ROLE_DOCTOR,
    "médico": PRESCRIPT_ROLE_DOCTOR,
    "physician": PRESCRIPT_ROLE_DOCTOR,
    "secretary": PRESCRIPT_ROLE_SECRETARY,
    "secretaria": PRESCRIPT_ROLE_SECRETARY,
    "assistant": PRESCRIPT_ROLE_SECRETARY,
    "nurse": PRESCRIPT_ROLE_NURSE,
    "enfermera": PRESCRIPT_ROLE_NURSE,
    "enfermero": PRESCRIPT_ROLE_NURSE,
    "admin": PRESCRIPT_ROLE_ADMIN,
    "administrator": PRESCRIPT_ROLE_ADMIN,
    "administrador": PRESCRIPT_ROLE_ADMIN,
    "manager": PRESCRIPT_ROLE_MANAGER,
    "gerente": PRESCRIPT_ROLE_MANAGER,
    "country manager": PRESCRIPT_ROLE_MANAGER,
    "org admin": PRESCRIPT_ROLE_ORG_ADMIN,
    "organization admin": PRESCRIPT_ROLE_ORG_ADMIN,
    "administrador de organizacion": PRESCRIPT_ROLE_ORG_ADMIN,
    "patient": PRESCRIPT_ROLE_PATIENT,
    "paciente": PRESCRIPT_ROLE_PATIENT,
}


def normalize_prescript_role(role):
    raw_role = str(role or "").strip().upper()
    if raw_role.startswith(COUNTRY_ADMIN_ROLE_PREFIX):
        return PRESCRIPT_ROLE_ADMIN
    normalized = raw_role.lower().replace("_", " ")
    return ROLE_ALIASES.get(normalized, normalized)


def is_country_admin_role(role):
    return str(role or "").strip().upper().startswith(COUNTRY_ADMIN_ROLE_PREFIX)


def normalize_prescript_roles(roles):
    normalized_roles = []
    for role in roles or []:
        normalized = normalize_prescript_role(role)
        if normalized in PRESCRIPT_ROLE_CHOICES and normalized not in normalized_roles:
            normalized_roles.append(normalized)
    return normalized_roles


def get_primary_prescript_role(roles):
    role_set = set(normalize_prescript_roles(roles))
    for role in PRESCRIPT_ROLE_PRIORITY:
        if role in role_set:
            return role
    return ""
