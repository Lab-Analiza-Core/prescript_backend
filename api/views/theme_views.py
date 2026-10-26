from django.db import transaction
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import IsGlobalAdmin, IsPrescriptAdminOrOrgAdmin
from api.services import theme_service


class EffectiveThemeView(APIView):
    """Tema que debe aplicar la aplicacion al usuario autenticado."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(theme_service.resolve_effective_theme(request.user))


class ThemeOptionsView(APIView):
    permission_classes = [IsPrescriptAdminOrOrgAdmin]

    def get(self, request):
        return Response(theme_service.options_payload())


class ThemeOrganizationListView(APIView):
    """Organizaciones cuyo tema puede gestionar el usuario, ordenadas por pais y nombre."""

    permission_classes = [IsPrescriptAdminOrOrgAdmin]

    def get(self, request):
        organizations = theme_service.manageable_theme_organizations(request.user)
        search = request.query_params.get("search", "").strip()
        if search:
            organizations = organizations.filter(name__icontains=search)
        return Response(
            [
                {
                    "id": organization.id,
                    "name": organization.name,
                    "country": {"code": organization.country.code, "name": organization.country.name},
                    "status": organization.status,
                    "customized": hasattr(organization, "theme") and not organization.theme.is_empty,
                }
                for organization in organizations
            ]
        )


class ThemeTargetMixin:
    """El tema global lo edita solo el administrador global; el de una organizacion, quien la gestione."""

    def get_permissions(self):
        if self.kwargs.get("organization_id") is None:
            return [IsGlobalAdmin()]
        return [IsPrescriptAdminOrOrgAdmin()]

    def get_target(self):
        organization_id = self.kwargs.get("organization_id")
        if organization_id is None:
            return None
        organization = theme_service.manageable_theme_organizations(self.request.user).filter(pk=organization_id).first()
        if organization is None:
            raise NotFound("Organizacion no encontrada.")
        return organization


class ThemeDetailView(ThemeTargetMixin, APIView):
    parser_classes = [JSONParser]

    def get(self, request, organization_id=None):
        return Response(theme_service.serialize_theme(self.get_target()))

    @transaction.atomic
    def put(self, request, organization_id=None):
        organization = self.get_target()
        data = request.data
        if not isinstance(data, dict) or not ({"colors", "font"} & data.keys()):
            raise ValidationError("Envie 'colors' y/o 'font'.")
        row = theme_service.get_row_for_update(organization, request.user)
        if "colors" in data:
            row.colors = theme_service.validate_colors(data["colors"], theme_service.inherited_colors(organization))
        if "font" in data:
            row.font = theme_service.validate_font(data["font"])
        theme_service.save_row(row)
        return Response(theme_service.serialize_theme(organization))

    @transaction.atomic
    def delete(self, request, organization_id=None):
        """Restablece: elimina la personalizacion y el ambito vuelve a heredar."""
        organization = self.get_target()
        theme_service.reset_theme(organization)
        return Response(theme_service.serialize_theme(organization))


class ThemeLogoView(ThemeTargetMixin, APIView):
    parser_classes = [MultiPartParser, FormParser]

    @transaction.atomic
    def post(self, request, organization_id=None):
        organization = self.get_target()
        uploaded = request.FILES.get("logo")
        if uploaded is None:
            raise ValidationError({"logo": "Adjunte el archivo en el campo 'logo'."})
        row = theme_service.get_row_for_update(organization, request.user)
        row.logo = theme_service.build_logo_data_url(uploaded)
        theme_service.save_row(row)
        return Response(theme_service.serialize_theme(organization))

    @transaction.atomic
    def delete(self, request, organization_id=None):
        organization = self.get_target()
        row = theme_service.get_row_for_update(organization, request.user)
        row.logo = ""
        theme_service.save_row(row)
        return Response(theme_service.serialize_theme(organization))
