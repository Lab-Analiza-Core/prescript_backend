from api.models import DoctorPortalProfile
from api.services.interactive_core import InteractiveCoreSecretaryService


def get_secretary_assigned_interactive_core_doctor_ids(user):
    secretary = getattr(user, "secretary_portal_profile", None)
    if not secretary or secretary.status != "active":
        return []
    return InteractiveCoreSecretaryService().get_assigned_doctor_ids(
        secretary.secretaria_interactivecore_id
    )


def get_secretary_assigned_doctor_ids(user):
    """Ids de DoctorPortalProfile que atiende la secretaria.

    Une los doctores asignados en Interactive Core con los vinculados localmente por la
    organizacion; los locales solo valen si el doctor sigue en la misma organizacion.
    """
    secretary = getattr(user, "secretary_portal_profile", None)
    if not secretary or secretary.status != "active":
        return []

    doctor_ids = set()
    interactive_core_ids = get_secretary_assigned_interactive_core_doctor_ids(user)
    if interactive_core_ids:
        doctor_ids.update(
            DoctorPortalProfile.objects.filter(interactive_core_doctor_id__in=interactive_core_ids).values_list(
                "id", flat=True
            )
        )
    local = secretary.doctor_assignments.all()
    if secretary.organization_id:
        local = local.filter(doctor__organization_id=secretary.organization_id)
    else:
        local = local.none()
    doctor_ids.update(local.values_list("doctor_id", flat=True))
    return list(doctor_ids)
