EXTERNAL_ORIGIN = "self_registered"


def is_external_account(user):
    """Cuenta creada por autorregistro: su correo nunca fue verificado contra Interactive Core.

    No debe heredar roles ni permisos de administracion por coincidir con un correo de IC.
    """
    for attribute in ("doctor_portal_profile", "secretary_portal_profile", "nurse_portal_profile"):
        profile = getattr(user, attribute, None)
        if profile and getattr(profile, "origin", None) == EXTERNAL_ORIGIN:
            return True
    return bool(getattr(user, "org_admin_profile", None) or getattr(user, "patient_portal_profile", None))
