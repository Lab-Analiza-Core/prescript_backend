from django.db.models import Case, IntegerField, Q, Value, When
from rest_framework import generics

from api.models import ExamCatalogMirror, MedicineCatalogMirror
from api.serializers import ExamCatalogMirrorSerializer, MedicineCatalogMirrorSerializer
from api.views.doctor_views import get_current_doctor
from api.services.country_scope import get_country_scope


class MedicineCatalogListView(generics.ListAPIView):
    serializer_class = MedicineCatalogMirrorSerializer

    def get_queryset(self):
        queryset = get_country_scope(self.request).require_valid().filter(
            MedicineCatalogMirror.objects.filter(is_active=True).select_related("country"),
        )
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(active_ingredient__icontains=search)
                | Q(commercial_house__icontains=search)
                | Q(code__icontains=search)
            )
        return queryset.order_by("name")


class RecommendedMedicineListView(generics.ListAPIView):
    serializer_class = MedicineCatalogMirrorSerializer

    def get_queryset(self):
        doctor = get_current_doctor(self.request.user)
        specialty_ids = [
            specialty.get("id")
            for specialty in doctor.specialties
            if isinstance(specialty, dict) and specialty.get("id") is not None
        ]
        preferred_ids = list(
            doctor.medicine_preferences.filter(category="favorite").values_list(
                "medicine_id",
                flat=True,
            )
        )
        queryset = get_country_scope(self.request).require_valid().filter(
            MedicineCatalogMirror.objects.filter(is_active=True).select_related("country"),
        )
        if specialty_ids:
            specialty_query = Q()
            for specialty_id in specialty_ids:
                specialty_query |= Q(specialty_ids__contains=[specialty_id])
            queryset = queryset.filter(Q(id__in=preferred_ids) | specialty_query)
        return queryset.annotate(
            recommendation_rank=Case(
                When(id__in=preferred_ids, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        ).order_by("recommendation_rank", "name")


class ExamCatalogListView(generics.ListAPIView):
    serializer_class = ExamCatalogMirrorSerializer

    def get_queryset(self):
        queryset = get_country_scope(self.request).require_valid().filter(
            ExamCatalogMirror.objects.filter(is_active=True).select_related("country"),
        )
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(area__icontains=search)
                | Q(sample_type__icontains=search)
                | Q(code__icontains=search)
            )
        return queryset.order_by("name")
