from rest_framework.permissions import BasePermission

from api.roles import PRESCRIPT_ROLE_ADMIN, get_primary_prescript_role


class IsPrescriptAdmin(BasePermission):
    message = "Solo usuarios administradores pueden acceder a este modulo."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_staff or user.is_superuser:
            return True
        role = get_primary_prescript_role(user.groups.values_list("name", flat=True))
        return role == PRESCRIPT_ROLE_ADMIN
