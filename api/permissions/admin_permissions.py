from rest_framework.permissions import BasePermission

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
