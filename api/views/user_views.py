from django.contrib.auth import get_user_model
from django.db.models import Prefetch, Q
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from api.models import UserCountryAccess
from api.permissions import IsPrescriptAdmin, IsPrescriptAdminOrOrgAdmin
from api.services.account_origin import EXTERNAL_ORIGIN
from api.services.country_scope import is_global_admin_user
from api.services.organization_scope import get_organization_scope
from api.utils.pagination import OptionalPageNumberPagination
from api.serializers.user_serializers import AdminUserSerializer, UserPasswordResetSerializer
from api.services.country_scope import get_country_scope


def organization_scoped_users(request):
    """Un administrador de organizacion solo ve a los usuarios de su propia organizacion."""
    organization_scope = get_organization_scope(request.user)
    queryset = get_user_model().objects.all()
    if not organization_scope.organization_id:
        return queryset.none()
    organization_id = organization_scope.organization_id
    return queryset.filter(
        Q(doctor_portal_profile__organization_id=organization_id)
        | Q(secretary_portal_profile__organization_id=organization_id)
        | Q(nurse_portal_profile__organization_id=organization_id)
        | Q(org_admin_profile__organization_id=organization_id)
        | Q(patient_portal_profile__organization_id=organization_id)
    )


def country_scoped_users(request):
    user = request.user
    if getattr(user, "org_admin_profile", None) and not is_global_admin_user(user):
        return organization_scoped_users(request)
    scope = get_country_scope(request).require_valid()
    queryset = get_user_model().objects.all()
    if scope.unrestricted:
        return queryset
    # Los administradores por pais gestionan al personal de Interactive Core; las cuentas
    # externas las controla su administrador de organizacion o el administrador global.
    queryset = queryset.exclude(
        Q(doctor_portal_profile__origin=EXTERNAL_ORIGIN)
        | Q(secretary_portal_profile__origin=EXTERNAL_ORIGIN)
        | Q(nurse_portal_profile__origin=EXTERNAL_ORIGIN)
        | Q(org_admin_profile__isnull=False)
        | Q(patient_portal_profile__isnull=False)
    )
    return queryset.filter(
        Q(prescript_country_accesses__country_id=scope.country_id)
        | Q(doctor_portal_profile__country_id=scope.country_id)
        | Q(secretary_portal_profile__country_id=scope.country_id)
        | Q(nurse_portal_profile__country_id=scope.country_id)
    ).exclude(
        prescript_country_accesses__role_code="ADMIN",
        prescript_country_accesses__country__isnull=True,
    )


class AdminUserListCreateView(generics.ListCreateAPIView):
    serializer_class = AdminUserSerializer
    pagination_class = OptionalPageNumberPagination

    def get_permissions(self):
        permission = IsPrescriptAdminOrOrgAdmin if self.request.method == "GET" else IsPrescriptAdmin
        return [permission()]

    def get_queryset(self):
        queryset = (
            country_scoped_users(self.request)
            .prefetch_related("groups")
            .prefetch_related(
                Prefetch(
                    "prescript_country_accesses",
                    queryset=UserCountryAccess.objects.filter(
                        is_active=True,
                        country__isnull=False,
                    ).select_related("country"),
                    to_attr="_active_country_accesses",
                )
            )
            .select_related(
                "doctor_portal_profile__country",
                "secretary_portal_profile__country",
                "nurse_portal_profile__country",
            )
            .order_by("first_name", "last_name", "username")
        )
        search = self.request.query_params.get("search", "").strip()
        status_filter = self.request.query_params.get("is_active", "").strip().lower()
        role = self.request.query_params.get("role", "").strip()

        if search:
            queryset = queryset.filter(
                Q(username__icontains=search)
                | Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(doctor_portal_profile__full_name__icontains=search)
                | Q(secretary_portal_profile__full_name__icontains=search)
                | Q(nurse_portal_profile__full_name__icontains=search)
            )
        if status_filter in {"true", "false"}:
            queryset = queryset.filter(is_active=status_filter == "true")
        if role:
            queryset = queryset.filter(groups__name=role)

        return queryset.distinct()


class AdminUserDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = AdminUserSerializer

    def get_permissions(self):
        permission = IsPrescriptAdminOrOrgAdmin if self.request.method == "GET" else IsPrescriptAdmin
        return [permission()]

    def get_queryset(self):
        return country_scoped_users(self.request).prefetch_related(
            "groups",
            Prefetch(
                "prescript_country_accesses",
                queryset=UserCountryAccess.objects.filter(
                    is_active=True,
                    country__isnull=False,
                ).select_related("country"),
                to_attr="_active_country_accesses",
            ),
        ).select_related(
            "doctor_portal_profile__country",
            "secretary_portal_profile__country",
            "nurse_portal_profile__country",
        )

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        user.is_active = False
        user.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminUserPasswordResetView(APIView):
    permission_classes = [IsPrescriptAdmin]

    def post(self, request, pk):
        user = generics.get_object_or_404(country_scoped_users(request), pk=pk)
        serializer = UserPasswordResetSerializer(data=request.data, context={"user": user})
        serializer.is_valid(raise_exception=True)
        temporary_password = serializer.save()
        return Response({"detail": "Contrasena actualizada.", "temporary_password": temporary_password})
