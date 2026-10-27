from rest_framework.permissions import BasePermission

from api.models.organization_models import ORIGIN_SELF_REGISTERED


class IsExternalDoctor(BasePermission):
    """Medico autorregistrado: administra su propio catalogo de medicamentos."""

    message = "Solo los medicos externos administran un catalogo propio de medicamentos."

    def has_permission(self, request, view):
        doctor = getattr(request.user, "doctor_portal_profile", None)
        return bool(doctor and doctor.origin == ORIGIN_SELF_REGISTERED)


class IsDoctorProfileOwner(BasePermission):
    def has_object_permission(self, request, view, obj):
        doctor = getattr(obj, "doctor", None)
        if doctor is None and hasattr(obj, "doctor_portal_profile"):
            doctor = obj.doctor_portal_profile
        if doctor is None and obj.__class__.__name__ == "DoctorPortalProfile":
            doctor = obj
        return bool(doctor and doctor.user_id == request.user.id)
