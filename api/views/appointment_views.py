from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from api.models import Appointment
from api.permissions import IsDoctorProfileOwner
from api.serializers import AppointmentSerializer
from api.views.doctor_views import get_current_doctor


class AppointmentListCreateView(generics.ListCreateAPIView):
    serializer_class = AppointmentSerializer

    def get_queryset(self):
        queryset = Appointment.objects.filter(
            doctor=get_current_doctor(self.request.user),
        ).select_related("patient")
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")
        if date_from:
            queryset = queryset.filter(scheduled_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(scheduled_at__date__lte=date_to)
        return queryset

    def perform_create(self, serializer):
        serializer.save(doctor=get_current_doctor(self.request.user))


class AppointmentDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = AppointmentSerializer
    permission_classes = [IsAuthenticated, IsDoctorProfileOwner]

    def get_queryset(self):
        return Appointment.objects.filter(
            doctor=get_current_doctor(self.request.user),
        ).select_related("patient")
