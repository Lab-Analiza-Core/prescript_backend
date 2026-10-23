import logging

from django.contrib.auth.models import Group
from django.conf import settings
from django.db import DatabaseError, connections
from rest_framework.exceptions import APIException

from api.roles import PRESCRIPT_ROLE_ADMIN, PRESCRIPT_ROLE_NURSE, PRESCRIPT_ROLE_SECRETARY
from api.models import UserCountryAccess
from api.roles import COUNTRY_ADMIN_ROLE_PREFIX, normalize_prescript_role
from api.services.account_origin import is_external_account
from api.services.country_service import get_or_create_country

logger = logging.getLogger(__name__)


class InteractiveCoreUnavailable(APIException):
    status_code = 503
    default_detail = "No se pudo verificar el rol de administrador en InteractiveCore."
    default_code = "interactive_core_unavailable"


class InteractiveCoreAccessService:
    def get_user_workspaces(self, email):
        normalized_email = str(email or "").strip()
        if not normalized_email:
            return []

        with connections["interactive_core"].cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    COALESCE(rp.code, UPPER(g.name)) AS role_code,
                    COALESCE(rp.is_admin, FALSE) AS is_admin,
                    c.id,
                    c.code,
                    c.name,
                    c.currency,
                    c.phone_code,
                    c.dni_mask,
                    c.phone_mask,
                    c.timezone
                FROM api_user u
                INNER JOIN api_user_groups ug ON ug.user_id = u.id
                INNER JOIN auth_group g ON g.id = ug.group_id
                LEFT JOIN api_roleprofile rp ON rp.group_id = g.id
                LEFT JOIN employee_profile ep ON ep.user_id = u.id
                LEFT JOIN api_country c ON c.id = COALESCE(rp.country_id, ep.country_id)
                WHERE LOWER(COALESCE(u.email, '')) = LOWER(%s)
                  AND COALESCE(rp.is_active, TRUE) = TRUE
                ORDER BY COALESCE(rp.sort_order, 0), g.name
                """,
                [normalized_email],
            )
            rows = cursor.fetchall()

        workspaces = []
        allowed_roles = {str(role).upper() for role in settings.PRESCRIPT_INTERACTIVE_CORE_PORTAL_ROLES}
        for row in rows:
            role_code = str(row[0] or "").upper()
            is_admin = bool(row[1])
            if not is_admin and normalize_prescript_role(role_code) not in allowed_roles:
                continue
            country = None
            if row[2]:
                country = {
                    "id": row[2],
                    "code": row[3],
                    "name": row[4],
                    "currency": row[5],
                    "phone_code": row[6],
                    "dni_mask": row[7],
                    "phone_mask": row[8],
                    "timezone": row[9],
                }
            workspaces.append({"role_code": role_code, "is_admin": is_admin, "country": country})
        return workspaces

    def sync_user_workspaces(self, user):
        # Una cuenta autorregistrada no puede heredar roles de IC solo por coincidir el correo.
        if is_external_account(user):
            return []
        workspaces = self.get_user_workspaces(user.email)
        UserCountryAccess.objects.filter(user=user, source="interactive_core").delete()
        admin_groups = list(
            user.groups.filter(name__startswith=COUNTRY_ADMIN_ROLE_PREFIX)
        )
        admin_groups.extend(user.groups.filter(name=PRESCRIPT_ROLE_ADMIN))
        if admin_groups:
            user.groups.remove(*admin_groups)

        if not workspaces:
            return []

        synced = []
        for workspace in workspaces:
            source_country = workspace["country"]
            country = get_or_create_country(
                {
                    "country": source_country,
                    "country_id": source_country.get("id") if source_country else None,
                }
            ) if source_country else None
            role_code = workspace["role_code"]
            canonical_role = PRESCRIPT_ROLE_ADMIN if workspace["is_admin"] else normalize_prescript_role(role_code)
            local_group_code = role_code if workspace["is_admin"] else canonical_role
            group, _ = Group.objects.get_or_create(name=local_group_code)
            user.groups.add(group)
            access, _ = UserCountryAccess.objects.update_or_create(
                user=user,
                role_code=canonical_role,
                country=country,
                defaults={"is_active": True, "source": "interactive_core"},
            )
            synced.append(access)
        return synced
    def has_admin_role(self, email):
        normalized_email = str(email or "").strip()
        if not normalized_email:
            return False

        with connections["interactive_core"].cursor() as cursor:
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM api_user u
                    INNER JOIN api_user_groups ug ON ug.user_id = u.id
                    INNER JOIN auth_group g ON g.id = ug.group_id
                    LEFT JOIN api_roleprofile rp ON rp.group_id = g.id
                    WHERE LOWER(COALESCE(u.email, '')) = LOWER(%s)
                      AND (
                          COALESCE(rp.is_admin, FALSE) = TRUE
                          OR COALESCE(rp.code, UPPER(g.name)) = %s
                      )
                      AND COALESCE(rp.is_active, TRUE) = TRUE
                )
                """,
                [normalized_email, PRESCRIPT_ROLE_ADMIN],
            )
            row = cursor.fetchone()

        return bool(row and row[0])

    # --- Fichas de secretarias y enfermeras (afiliacion) -------------------------------------
    # Se consultan por id exacto: buscar por correo, DNI o texto libre permitiria reclamar la ficha
    # de otra persona conociendo un dato casi publico.

    @staticmethod
    def _escape_like(query):
        escaped = str(query).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"%{escaped}%"

    def get_secretary(self, secretary_id):
        with connections["interactive_core"].cursor() as cursor:
            cursor.execute(
                """
                SELECT s.id, s.full_name, s.email, s.phone, s.dni, s.country_id, c.name AS country_name
                FROM api_secretary s
                LEFT JOIN api_country c ON c.id = s.country_id
                WHERE s.id = %s
                """,
                [secretary_id],
            )
            row = cursor.fetchone()

        if row is None:
            return None

        return {
            "id": row[0],
            "full_name": row[1],
            "email": row[2],
            "phone": row[3],
            "dni": row[4],
            "country_id": row[5],
            "country": row[6],
            "prescript_roles": [PRESCRIPT_ROLE_SECRETARY],
            "prescript_role": PRESCRIPT_ROLE_SECRETARY,
            "has_prescript_access": True,
        }

    def search_secretaries(self, query, limit=10):
        pattern = self._escape_like(query)
        with connections["interactive_core"].cursor() as cursor:
            cursor.execute(
                """
                SELECT s.id, s.full_name, s.dni, c.code, COALESCE(TRIM(s.email), '') <> ''
                FROM api_secretary s
                LEFT JOIN api_country c ON c.id = s.country_id
                WHERE s.full_name ILIKE %s OR COALESCE(s.dni, '') ILIKE %s
                ORDER BY s.full_name
                LIMIT %s
                """,
                [pattern, pattern, limit],
            )
            rows = cursor.fetchall()
        return [
            {"id": row[0], "full_name": row[1], "identifier": row[2], "country_code": row[3], "has_email": bool(row[4])}
            for row in rows
        ]

    # Condicion comun: el usuario de Interactive Core pertenece al grupo con el rol pedido.
    _ROLE_MEMBERSHIP_SQL = """
        EXISTS (
            SELECT 1
            FROM api_user_groups ug
            INNER JOIN auth_group g ON g.id = ug.group_id
            LEFT JOIN api_roleprofile rp ON rp.group_id = g.id
            WHERE ug.user_id = u.id
              AND COALESCE(rp.code, UPPER(g.name)) = %s
        )
    """

    def get_employee_with_role(self, user_id, role_code):
        with connections["interactive_core"].cursor() as cursor:
            cursor.execute(
                f"""
                SELECT u.id, ep.id, ep.full_name, u.email, ep.phone, ep.dni, ep.country_id, c.name
                FROM api_user u
                INNER JOIN employee_profile ep ON ep.user_id = u.id
                LEFT JOIN api_country c ON c.id = ep.country_id
                WHERE u.id = %s AND {self._ROLE_MEMBERSHIP_SQL}
                LIMIT 1
                """,
                [user_id, role_code],
            )
            row = cursor.fetchone()

        if row is None:
            return None

        return {
            "id": row[0],
            "interactive_core_user_id": row[0],
            "interactive_core_employee_id": row[1],
            "full_name": row[2],
            "email": row[3],
            "phone": row[4],
            "dni": row[5],
            "country_id": row[6],
            "country": row[7],
            "prescript_roles": [role_code],
            "prescript_role": role_code,
            "has_prescript_access": True,
        }

    def search_employees_with_role(self, query, role_code, limit=10):
        pattern = self._escape_like(query)
        with connections["interactive_core"].cursor() as cursor:
            cursor.execute(
                f"""
                SELECT u.id, ep.full_name, ep.dni, c.code, COALESCE(TRIM(u.email), '') <> ''
                FROM api_user u
                INNER JOIN employee_profile ep ON ep.user_id = u.id
                LEFT JOIN api_country c ON c.id = ep.country_id
                WHERE (ep.full_name ILIKE %s OR COALESCE(ep.dni, '') ILIKE %s)
                  AND {self._ROLE_MEMBERSHIP_SQL}
                ORDER BY ep.full_name
                LIMIT %s
                """,
                [pattern, pattern, role_code, limit],
            )
            rows = cursor.fetchall()
        return [
            {"id": row[0], "full_name": row[1], "identifier": row[2], "country_code": row[3], "has_email": bool(row[4])}
            for row in rows
        ]

    def get_nurse(self, user_id):
        return self.get_employee_with_role(user_id, PRESCRIPT_ROLE_NURSE)

    def search_nurses(self, query, limit=10):
        return self.search_employees_with_role(query, PRESCRIPT_ROLE_NURSE, limit)


def user_is_interactive_core_admin(user):
    """Fuente de verdad para el acceso al modulo de administracion de usuarios.

    Se consulta en vivo en cada request: el Group local "ADMIN" de Prescript
    no basta por si solo, porque puede asignarse manualmente desde este mismo
    modulo sin que InteractiveCore respalde ese rol.
    """
    email = getattr(user, "email", "") or ""
    if not email or is_external_account(user):
        return False
    try:
        return InteractiveCoreAccessService().has_admin_role(email)
    except DatabaseError:
        logger.exception("No se pudo verificar el rol ADMIN en InteractiveCore para %s", email)
        raise InteractiveCoreUnavailable()
