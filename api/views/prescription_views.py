from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from api.models import Prescription
from api.permissions import IsDoctorProfileOwner
from api.serializers import PrescriptionSerializer
from api.views.doctor_views import get_current_doctor


class PrescriptionListCreateView(generics.ListCreateAPIView):
    serializer_class = PrescriptionSerializer

    def get_queryset(self):
        queryset = Prescription.objects.filter(
            doctor=get_current_doctor(self.request.user),
        ).prefetch_related("items").select_related("patient", "appointment")
        patient = self.request.query_params.get("patient")
        if patient and patient.isdigit():
            queryset = queryset.filter(patient_id=int(patient))
        return queryset

    def perform_create(self, serializer):
        serializer.save(doctor=get_current_doctor(self.request.user))


class PrescriptionDetailView(generics.RetrieveAPIView):
    serializer_class = PrescriptionSerializer
    permission_classes = [IsAuthenticated, IsDoctorProfileOwner]

    def get_queryset(self):
        return Prescription.objects.filter(
            doctor=get_current_doctor(self.request.user),
        ).prefetch_related("items").select_related("patient", "appointment")
