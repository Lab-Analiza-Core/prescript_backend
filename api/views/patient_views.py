from rest_framework import generics
from rest_framework.exceptions import PermissionDenied

from api.models import PatientVitals
from api.serializers import PatientSerializer, PatientVitalsSerializer
from api.services.patient_access import accessible_patient_queryset, save_patient_for_user
from api.views.doctor_views import get_current_doctor


class PatientListCreateView(generics.ListCreateAPIView):
    serializer_class = PatientSerializer

    def get_queryset(self):
        include_inactive = self.request.query_params.get("include_inactive") == "true"
        return accessible_patient_queryset(self.request.user, include_inactive=include_inactive)

    def perform_create(self, serializer):
        save_patient_for_user(serializer, self.request.user)


class PatientDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = PatientSerializer

    def get_queryset(self):
        return accessible_patient_queryset(self.request.user).select_related("medical_profile")

    def perform_update(self, serializer):
        save_patient_for_user(serializer, self.request.user, patient=self.get_object())


class PatientVitalsListCreateView(generics.ListCreateAPIView):
    serializer_class = PatientVitalsSerializer

    def get_queryset(self):
        return PatientVitals.objects.filter(
            patient__doctor=get_current_doctor(self.request.user),
        ).select_related("patient", "appointment")

    def perform_create(self, serializer):
        doctor = get_current_doctor(self.request.user)
        patient = serializer.validated_data["patient"]
        if patient.doctor_id != doctor.id:
            raise PermissionDenied("No puede registrar signos vitales de otro doctor.")
        serializer.save()
