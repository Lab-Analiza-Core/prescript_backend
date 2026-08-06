from api.services.interactive_core import InteractiveCoreSecretaryService


def get_secretary_assigned_interactive_core_doctor_ids(user):
    secretary = getattr(user, "secretary_portal_profile", None)
    if not secretary or secretary.status != "active":
        return []
    return InteractiveCoreSecretaryService().get_assigned_doctor_ids(
        secretary.secretaria_interactivecore_id
    )
