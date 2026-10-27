from django.db.models import Case, CharField, F, IntegerField, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Coalesce
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from api.models import DoctorMedicine, DoctorMedicinePreference, ExamCatalogMirror, MedicineCatalogMirror
from api.models.organization_models import ORIGIN_SELF_REGISTERED
from api.permissions import IsExternalDoctor
from api.serializers import (
    DoctorMedicineSerializer,
    ExamCatalogMirrorSerializer,
    MedicineCatalogMirrorSerializer,
    OwnCatalogEntrySerializer,
    SyncedCatalogEntrySerializer,
)
from api.utils.pagination import OptionalPageNumberPagination
from api.views.doctor_views import get_current_doctor
from api.services.country_scope import get_country_scope

CATEGORY_RANK = Case(
    When(effective_category="favorite", then=Value(0)),
    When(effective_category="complementary", then=Value(1)),
    default=Value(2),
    output_field=IntegerField(),
)


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


class DoctorMedicineCatalogView(generics.ListAPIView):
    """Catalogo del medico autenticado, sin importar de donde venga.

    Medicos de Interactive Core: el catalogo sincronizado de su pais, con su preferencia aplicada.
    Medicos externos: su catalogo propio. La forma de cada entrada es la misma en ambos casos.
    """

    pagination_class = OptionalPageNumberPagination

    def _is_external(self):
        return get_current_doctor(self.request.user).origin == ORIGIN_SELF_REGISTERED

    def get_serializer_class(self):
        return OwnCatalogEntrySerializer if self._is_external() else SyncedCatalogEntrySerializer

    def get_queryset(self):
        doctor = get_current_doctor(self.request.user)
        params = self.request.query_params
        search = params.get("search", "").strip()
        category = params.get("category", "").strip()

        if doctor.origin == ORIGIN_SELF_REGISTERED:
            queryset = DoctorMedicine.objects.filter(doctor=doctor).annotate(effective_category=F("category"))
            if params.get("include_inactive") != "true":
                queryset = queryset.filter(is_active=True)
        else:
            preference = DoctorMedicinePreference.objects.filter(doctor=doctor, medicine=OuterRef("pk"))
            queryset = (
                MedicineCatalogMirror.objects.filter(country_id=doctor.country_id, is_active=True)
                .annotate(
                    preference_id=Subquery(preference.values("id")[:1]),
                    preference_notes=Subquery(preference.values("notes")[:1], output_field=CharField()),
                    effective_category=Coalesce(
                        Subquery(preference.values("category")[:1], output_field=CharField()),
                        Value("undetermined"),
                    ),
                )
            )

        if search:
            search_filter = Q(name__icontains=search) | Q(active_ingredient__icontains=search)
            if doctor.origin != ORIGIN_SELF_REGISTERED:
                search_filter |= Q(commercial_house__icontains=search) | Q(code__icontains=search)
            queryset = queryset.filter(search_filter)
        if category:
            queryset = queryset.filter(effective_category=category)
        return queryset.annotate(category_rank=CATEGORY_RANK).order_by("category_rank", "name", "id")


class DoctorOwnMedicineListCreateView(generics.ListCreateAPIView):
    serializer_class = DoctorMedicineSerializer
    permission_classes = [IsAuthenticated, IsExternalDoctor]
    pagination_class = OptionalPageNumberPagination

    def get_queryset(self):
        return DoctorMedicine.objects.filter(doctor=get_current_doctor(self.request.user))

    def perform_create(self, serializer):
        serializer.save(doctor=get_current_doctor(self.request.user))


class DoctorOwnMedicineDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = DoctorMedicineSerializer
    permission_classes = [IsAuthenticated, IsExternalDoctor]

    def get_queryset(self):
        return DoctorMedicine.objects.filter(doctor=get_current_doctor(self.request.user))
