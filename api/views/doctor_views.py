from rest_framework import generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotAuthenticated, NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.models import DoctorMedicinePreference, DoctorPortalProfile
from api.permissions import IsDoctorProfileOwner
from api.roles import PRESCRIPT_ROLE_ADMIN, PRESCRIPT_ROLE_DOCTOR, get_primary_prescript_role
from api.serializers import DoctorMedicinePreferenceSerializer, DoctorPortalProfileSerializer


def get_current_doctor(user):
    if not user or not user.is_authenticated:
        raise NotAuthenticated("Credenciales de autenticacion no provistas.")
    try:
        return user.doctor_portal_profile
    except DoctorPortalProfile.DoesNotExist as exc:
        raise NotFound("El usuario autenticado no tiene perfil medico en Prescript.") from exc


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def auth_me_view(request):
    user = request.user
    doctor = getattr(user, "doctor_portal_profile", None)

    if doctor:
        profile = DoctorPortalProfileSerializer(doctor).data
        role = get_primary_prescript_role(user.groups.values_list("name", flat=True)) or PRESCRIPT_ROLE_DOCTOR
        display_name = doctor.full_name
    else:
        profile = None
        role = get_primary_prescript_role(user.groups.values_list("name", flat=True))
        if not role:
            role = PRESCRIPT_ROLE_ADMIN if user.is_staff or user.is_superuser else "user"
        display_name = user.get_full_name() or user.username

    return Response(
        {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "name": display_name,
            "role": role,
            "roles": list(user.groups.values_list("name", flat=True)),
            "is_staff": user.is_staff,
            "is_superuser": user.is_superuser,
            "doctor_profile": profile,
        }
    )


class DoctorMeView(generics.RetrieveUpdateAPIView):
    serializer_class = DoctorPortalProfileSerializer
    permission_classes = [IsAuthenticated, IsDoctorProfileOwner]

    def get_object(self):
        return get_current_doctor(self.request.user)


class DoctorMedicinePreferenceListCreateView(generics.ListCreateAPIView):
    serializer_class = DoctorMedicinePreferenceSerializer

    def get_queryset(self):
        return DoctorMedicinePreference.objects.filter(
            doctor=get_current_doctor(self.request.user),
        ).select_related("medicine")

    def perform_create(self, serializer):
        serializer.save(doctor=get_current_doctor(self.request.user))


class DoctorMedicinePreferenceDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = DoctorMedicinePreferenceSerializer
    permission_classes = [IsAuthenticated, IsDoctorProfileOwner]

    def get_queryset(self):
        return DoctorMedicinePreference.objects.filter(
            doctor=get_current_doctor(self.request.user),
        ).select_related("medicine")
