from django.db.models import Prefetch, Q
from django.utils.dateparse import parse_date
from rest_framework import generics
from rest_framework.exceptions import PermissionDenied

from api.models import PatientVitals
from api.serializers import PatientSerializer, PatientVitalsSerializer
from api.services.patient_access import country_scoped_patient_queryset, save_patient_for_user
from api.services.country_scope import get_country_scope
from api.utils.pagination import OptionalPageNumberPagination
from api.views.doctor_views import get_current_doctor


class PatientListCreateView(generics.ListCreateAPIView):
    serializer_class = PatientSerializer
    pagination_class = OptionalPageNumberPagination

    def get_queryset(self):
        params = self.request.query_params
        status_filter = params.get("is_active", "").strip().lower()
        include_inactive = params.get("include_inactive") == "true" or status_filter in {"false", "all"}
        queryset = country_scoped_patient_queryset(
            self.request.user,
            get_country_scope(self.request),
            include_inactive=include_inactive,
        )

        if status_filter in {"true", "false"}:
            queryset = queryset.filter(is_active=status_filter == "true")

        search = params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(dni__icontains=search)
                | Q(phone__icontains=search)
                | Q(email__icontains=search)
            )

        doctor = params.get("doctor", "").strip()
        if doctor.isdigit():
            queryset = queryset.filter(doctor_id=int(doctor))

        sex = params.get("sex", "").strip().upper()
        if sex in {"F", "M", "O"}:
            queryset = queryset.filter(sex=sex)

        created_from = parse_date(params.get("created_from", "").strip())
        if created_from:
            queryset = queryset.filter(created_at__date__gte=created_from)
        created_to = parse_date(params.get("created_to", "").strip())
        if created_to:
            queryset = queryset.filter(created_at__date__lte=created_to)

        return queryset.prefetch_related(
            Prefetch(
                "vitals",
                queryset=PatientVitals.objects.order_by("-recorded_at")[:5],
                to_attr="_recent_vitals",
            )
        )

    def perform_create(self, serializer):
        save_patient_for_user(serializer, self.request.user, scope=get_country_scope(self.request))


class PatientDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = PatientSerializer

    def get_queryset(self):
        return country_scoped_patient_queryset(
            self.request.user,
            get_country_scope(self.request),
        ).select_related("medical_profile").prefetch_related(
            Prefetch(
                "vitals",
                queryset=PatientVitals.objects.order_by("-recorded_at")[:5],
                to_attr="_recent_vitals",
            )
        )

    def perform_update(self, serializer):
        save_patient_for_user(
            serializer,
            self.request.user,
            patient=self.get_object(),
            scope=get_country_scope(self.request),
        )


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
