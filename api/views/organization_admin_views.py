from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from rest_framework import generics, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from api.models import (
    CountryDivision,
    OrganizationAdminProfile,
    OrganizationInvitation,
    SecretaryDoctorAssignment,
    SpecialtyCatalogMirror,
    TermsVersion,
)
from api.permissions import IsGlobalAdmin, IsOrganizationManager
from api.roles import PRESCRIPT_ROLE_ORG_ADMIN
from api.serializers.organization_serializers import (
    MemberStatusSerializer,
    OrganizationInvitationSerializer,
    OrganizationSerializer,
    OrgAdminProfileSerializer,
    PublicDivisionSerializer,
    PublicSpecialtySerializer,
    SecretaryAssignmentSerializer,
    TermsVersionSerializer,
    serialize_member,
)
from api.services.country_scope import is_global_admin_user
from api.services.country_service import normalize_country_code
from api.services.organization_admin_service import (
    activate_terms,
    generate_invitation_code,
    get_member_profile,
    manageable_organization_ids,
    manageable_organizations,
    notify_org_admin_decision,
    publish_terms,
    reject_org_admin,
    set_member_active,
    users_in_organizations,
)
from api.utils.pagination import OptionalPageNumberPagination
from api.services.organization_service import OrganizationAdminService
from api.services.registration_service import get_current_terms


class OrganizationListCreateView(generics.ListCreateAPIView):
    """Formulario de organizaciones: la crea el administrador global; el de organizacion solo ve la suya."""

    serializer_class = OrganizationSerializer
    pagination_class = OptionalPageNumberPagination

    def get_permissions(self):
        permission = IsOrganizationManager if self.request.method == "GET" else IsGlobalAdmin
        return [permission()]

    def get_queryset(self):
        queryset = manageable_organizations(self.request.user)
        params = self.request.query_params
        if params.get("country"):
            queryset = queryset.filter(country__code=normalize_country_code(params["country"]) or "")
        if params.get("status") in {"active", "suspended"}:
            queryset = queryset.filter(status=params["status"])
        search = params.get("search", "").strip()
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset.order_by("country__name", "name")


class OrganizationDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = OrganizationSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_permissions(self):
        permission = IsOrganizationManager if self.request.method == "GET" else IsGlobalAdmin
        return [permission()]

    def get_queryset(self):
        return manageable_organizations(self.request.user)


class InvitationListCreateView(generics.ListCreateAPIView):
    serializer_class = OrganizationInvitationSerializer
    permission_classes = [IsOrganizationManager]
    pagination_class = OptionalPageNumberPagination

    def get_organization(self):
        organization = manageable_organizations(self.request.user).filter(pk=self.kwargs["organization_id"]).first()
        if organization is None:
            raise NotFound("Organizacion no encontrada.")
        return organization

    def get_queryset(self):
        return OrganizationInvitation.objects.filter(organization=self.get_organization()).select_related("organization")

    def perform_create(self, serializer):
        organization = self.get_organization()
        if organization.status != "active":
            raise ValidationError({"organization": "La organizacion esta suspendida."})
        serializer.save(
            organization=organization,
            code=generate_invitation_code(),
            created_by=self.request.user,
        )


class InvitationDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Editar o revocar. Eliminar solo revoca: se conserva el rastro de a quien se invito."""

    serializer_class = OrganizationInvitationSerializer
    permission_classes = [IsOrganizationManager]
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self):
        allowed = manageable_organization_ids(self.request.user)
        queryset = OrganizationInvitation.objects.select_related("organization")
        return queryset if allowed is None else queryset.filter(organization_id__in=allowed)

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active"])


class MemberListView(APIView):
    permission_classes = [IsOrganizationManager]

    def get(self, request):
        allowed = manageable_organization_ids(request.user)
        organization_id = request.query_params.get("organization")
        if organization_id:
            if not organization_id.isdigit():
                raise ValidationError({"organization": "Organizacion invalida."})
            organization_id = int(organization_id)
            if allowed is not None and organization_id not in allowed:
                raise PermissionDenied("No puede ver usuarios de otra organizacion.")
            allowed = [organization_id]

        queryset = (
            users_in_organizations(allowed)
            .select_related(
                "doctor_portal_profile__organization",
                "secretary_portal_profile__organization",
                "nurse_portal_profile__organization",
                "org_admin_profile__organization",
                "patient_portal_profile__organization",
            )
            .order_by("first_name", "username")
        )
        search = request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search)
                | Q(email__icontains=search)
                | Q(doctor_portal_profile__full_name__icontains=search)
                | Q(secretary_portal_profile__full_name__icontains=search)
                | Q(nurse_portal_profile__full_name__icontains=search)
                | Q(org_admin_profile__full_name__icontains=search)
                | Q(patient_portal_profile__full_name__icontains=search)
            )
        members = [serialize_member(user) for user in queryset]
        role = request.query_params.get("role", "").strip().upper()
        if role:
            members = [member for member in members if member["role"] == role]
        paginator = OptionalPageNumberPagination()
        page = paginator.paginate_queryset(members, request, view=self)
        if page is not None:
            return paginator.get_paginated_response(page)
        return Response(members)


class MemberStatusView(APIView):
    """Activar o desactivar el acceso de un miembro (nunca cambia roles ni contrasenas)."""

    permission_classes = [IsOrganizationManager]

    def patch(self, request, pk):
        allowed = manageable_organization_ids(request.user)
        target = generics.get_object_or_404(users_in_organizations(allowed), pk=pk)
        if target.pk == request.user.pk:
            raise PermissionDenied("No puede cambiar el estado de su propia cuenta.")
        if is_global_admin_user(target):
            raise PermissionDenied("No puede modificar a un administrador global.")
        role, _ = get_member_profile(target)
        if role == PRESCRIPT_ROLE_ORG_ADMIN and allowed is not None:
            raise PermissionDenied("Solo el administrador global puede modificar administradores de organizacion.")

        serializer = MemberStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        set_member_active(target, serializer.validated_data["is_active"])
        # Se recarga para devolver el perfil ya con su estado actualizado.
        return Response(serialize_member(get_user_model().objects.get(pk=target.pk)))


class SecretaryAssignmentListCreateView(generics.ListCreateAPIView):
    serializer_class = SecretaryAssignmentSerializer
    permission_classes = [IsOrganizationManager]
    pagination_class = OptionalPageNumberPagination

    def get_queryset(self):
        allowed = manageable_organization_ids(self.request.user)
        queryset = SecretaryDoctorAssignment.objects.select_related("secretary", "doctor")
        if allowed is not None:
            queryset = queryset.filter(secretary__organization_id__in=allowed)
        secretary = self.request.query_params.get("secretary")
        if secretary and secretary.isdigit():
            queryset = queryset.filter(secretary_id=int(secretary))
        return queryset.order_by("secretary__full_name", "doctor__full_name")

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class SecretaryAssignmentDetailView(generics.DestroyAPIView):
    permission_classes = [IsOrganizationManager]

    def get_queryset(self):
        allowed = manageable_organization_ids(self.request.user)
        queryset = SecretaryDoctorAssignment.objects.all()
        return queryset if allowed is None else queryset.filter(secretary__organization_id__in=allowed)


class OrgAdminRequestListView(generics.ListAPIView):
    serializer_class = OrgAdminProfileSerializer
    permission_classes = [IsGlobalAdmin]
    pagination_class = OptionalPageNumberPagination

    def get_queryset(self):
        queryset = OrganizationAdminProfile.objects.select_related("organization", "country")
        status_filter = self.request.query_params.get("status")
        if status_filter in {"pending", "active", "inactive"}:
            queryset = queryset.filter(status=status_filter)
        return queryset.order_by("-created_at")


class OrgAdminDecisionView(APIView):
    permission_classes = [IsGlobalAdmin]
    approve = True

    def post(self, request, pk):
        profile = generics.get_object_or_404(
            OrganizationAdminProfile.objects.select_related("user", "organization"), pk=pk
        )
        if self.approve:
            if profile.organization.status != "active":
                raise ValidationError({"detail": "La organizacion esta suspendida."})
            OrganizationAdminService().approve(profile, request.user)
            profile.user.is_active = True
            profile.user.save(update_fields=["is_active"])
        else:
            reject_org_admin(profile)
        notify_org_admin_decision(profile, approved=self.approve)
        return Response(OrgAdminProfileSerializer(profile).data)


class TermsVersionListCreateView(generics.ListCreateAPIView):
    """Publicar una version nueva la vuelve la vigente; las anteriores se conservan como historial."""

    serializer_class = TermsVersionSerializer
    permission_classes = [IsGlobalAdmin]
    pagination_class = OptionalPageNumberPagination
    queryset = TermsVersion.objects.annotate(acceptances_total=Count("acceptances"))

    def perform_create(self, serializer):
        data = serializer.validated_data
        serializer.instance = publish_terms(data["version"], data.get("title", "Terminos y condiciones"), data["content"])


class TermsVersionActivateView(APIView):
    """Convierte en vigente una version ya publicada; la que lo era pasa a historial."""

    permission_classes = [IsGlobalAdmin]

    def post(self, request, pk):
        terms = generics.get_object_or_404(TermsVersion, pk=pk)
        activate_terms(terms)
        return Response(TermsVersionSerializer(terms).data)


# --- Catalogos publicos para el formulario de registro -------------------------------------


class PublicCatalogView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "catalog"

    def get_country_code(self, request):
        code = normalize_country_code(request.query_params.get("country", ""))
        if not code:
            raise ValidationError({"country": "Indique un pais valido."})
        return code


class PublicDivisionListView(PublicCatalogView):
    def get(self, request):
        divisions = CountryDivision.objects.filter(country__code=self.get_country_code(request), is_active=True)
        return Response(PublicDivisionSerializer(divisions, many=True).data)


class PublicSpecialtyListView(PublicCatalogView):
    def get(self, request):
        specialties = SpecialtyCatalogMirror.objects.filter(
            country__code=self.get_country_code(request), is_active=True
        )
        return Response(PublicSpecialtySerializer(specialties, many=True).data)


class PublicCurrentTermsView(PublicCatalogView):
    def get(self, request):
        terms = get_current_terms()
        if terms is None:
            raise NotFound("Los terminos y condiciones aun no estan publicados.")
        return Response({"version": terms.version, "title": terms.title, "content": terms.content})
