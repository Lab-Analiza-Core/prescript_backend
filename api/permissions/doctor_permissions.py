from rest_framework.permissions import BasePermission


class IsDoctorProfileOwner(BasePermission):
    def has_object_permission(self, request, view, obj):
        doctor = getattr(obj, "doctor", None)
        if doctor is None and hasattr(obj, "doctor_portal_profile"):
            doctor = obj.doctor_portal_profile
        if doctor is None and obj.__class__.__name__ == "DoctorPortalProfile":
            doctor = obj
        return bool(doctor and doctor.user_id == request.user.id)
