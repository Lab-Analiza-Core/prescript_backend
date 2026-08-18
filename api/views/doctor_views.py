from rest_framework import generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotAuthenticated, NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.models import DoctorMedicinePreference, DoctorPortalProfile
from api.permissions import IsDoctorProfileOwner
from api.roles import (
    PRESCRIPT_ROLE_ADMIN,
    PRESCRIPT_ROLE_MANAGER,
    PRESCRIPT_ROLE_NURSE,
    PRESCRIPT_ROLE_SECRETARY,
)
from api.services.role_access import get_current_prescript_role
from api.services.doctor_display import format_doctor_display_name
from api.serializers import (
    DoctorMedicinePreferenceSerializer,
    DoctorPortalProfileSerializer,
    NursePortalProfileSerializer,
    SecretaryPortalProfileSerializer,
)
from api.serializers.auth_serializers import UserProfileUpdateSerializer


def get_current_doctor(user):
    if not user or not user.is_authenticated:
        raise NotAuthenticated("Credenciales de autenticacion no provistas.")
    try:
        return user.doctor_portal_profile
    except DoctorPortalProfile.DoesNotExist as exc:
        raise NotFound("El usuario autenticado no tiene perfil medico en Prescript.") from exc


def build_auth_me_payload(user):
    doctor = getattr(user, "doctor_portal_profile", None)
    secretary = getattr(user, "secretary_portal_profile", None)
    nurse = getattr(user, "nurse_portal_profile", None)

    active_profile = doctor or secretary or nurse
    doctor_profile = DoctorPortalProfileSerializer(doctor).data if doctor else None
    role = get_current_prescript_role(user) or "user"

    display_name = getattr(active_profile, "full_name", None) or user.get_full_name() or user.username
    if doctor:
        display_name = format_doctor_display_name(doctor.full_name, doctor.sex)

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "name": display_name,
        "full_name": display_name,
        "display_name": display_name,
        "role": role,
        "roles": list(user.groups.values_list("name", flat=True)),
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "doctor_profile": doctor_profile,
        "secretary_profile": SecretaryPortalProfileSerializer(secretary).data if secretary else None,
        "nurse_profile": NursePortalProfileSerializer(nurse).data if nurse else None,
    }


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def auth_me_view(request):
    if request.method == "PATCH":
        serializer = UserProfileUpdateSerializer(
            request.user,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

    return Response(build_auth_me_payload(request.user))


class DoctorMeView(generics.RetrieveUpdateAPIView):
    serializer_class = DoctorPortalProfileSerializer
    permission_classes = [IsAuthenticated, IsDoctorProfileOwner]

    def get_object(self):
        return get_current_doctor(self.request.user)


class DoctorListView(generics.ListAPIView):
    serializer_class = DoctorPortalProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        doctor = getattr(self.request.user, "doctor_portal_profile", None)
        if doctor:
            return DoctorPortalProfile.objects.filter(pk=doctor.pk)

        role = get_current_prescript_role(self.request.user)
        secretary = getattr(self.request.user, "secretary_portal_profile", None)
        if role == PRESCRIPT_ROLE_SECRETARY and secretary:
            from api.services.interactive_core import InteractiveCoreSecretaryService

            doctor_ids = InteractiveCoreSecretaryService().get_assigned_doctor_ids(
                secretary.secretaria_interactivecore_id
            )
            return DoctorPortalProfile.objects.filter(
                interactive_core_doctor_id__in=doctor_ids,
                status="active",
            ).order_by("full_name")

        if role in {PRESCRIPT_ROLE_ADMIN, PRESCRIPT_ROLE_MANAGER, PRESCRIPT_ROLE_NURSE}:
            return DoctorPortalProfile.objects.filter(status="active").order_by("full_name")

        return DoctorPortalProfile.objects.none()


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
