from rest_framework import generics
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated

from api.models import Patient, PatientVitals
from api.permissions import IsDoctorProfileOwner
from api.serializers import PatientSerializer, PatientVitalsSerializer
from api.views.doctor_views import get_current_doctor


class PatientListCreateView(generics.ListCreateAPIView):
    serializer_class = PatientSerializer

    def get_queryset(self):
        queryset = Patient.objects.filter(
            doctor=get_current_doctor(self.request.user),
        ).select_related("medical_profile")
        include_inactive = self.request.query_params.get("include_inactive") == "true"
        if not include_inactive:
            queryset = queryset.filter(is_active=True)
        return queryset

    def perform_create(self, serializer):
        serializer.save(doctor=get_current_doctor(self.request.user))


class PatientDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = PatientSerializer
    permission_classes = [IsAuthenticated, IsDoctorProfileOwner]

    def get_queryset(self):
        return Patient.objects.filter(
            doctor=get_current_doctor(self.request.user),
        ).select_related("medical_profile")


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
