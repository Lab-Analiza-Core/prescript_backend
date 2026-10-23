from rest_framework.permissions import BasePermission

from api.services.country_scope import is_global_admin_user
from api.services.interactive_core import user_is_interactive_core_admin


class IsPrescriptAdmin(BasePermission):
    message = "Solo usuarios administradores pueden acceder a este modulo."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return user_is_interactive_core_admin(user)


class IsPrescriptAdminOrOrgAdmin(IsPrescriptAdmin):
    """Administrador de Prescript o administrador de organizacion ya aprobado."""

    def has_permission(self, request, view):
        user = request.user
        if user and user.is_authenticated:
            org_admin = getattr(user, "org_admin_profile", None)
            if org_admin and org_admin.status == "active":
                return True
        return super().has_permission(request, view)


class IsGlobalAdmin(IsPrescriptAdmin):
    """Solo el administrador global; los administradores por pais quedan fuera."""

    message = "Solo el administrador global puede realizar esta accion."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated or not is_global_admin_user(user):
            return False
        return super().has_permission(request, view)


class IsOrganizationManager(IsGlobalAdmin):
    """Administrador global o administrador de organizacion ya aprobado."""

    message = "Solo administradores de organizacion pueden realizar esta accion."

    def has_permission(self, request, view):
        user = request.user
        if user and user.is_authenticated:
            org_admin = getattr(user, "org_admin_profile", None)
            if org_admin and org_admin.status == "active":
                return True
        return super().has_permission(request, view)
