from django.db import connections

from api.roles import PRESCRIPT_ROLE_NURSE, PRESCRIPT_ROLE_SECRETARY
from .doctor_service import InteractiveCoreDoctorService


class InteractiveCoreAccessService:
    def lookup(self, role, identifier):
        normalized_role = str(role or "").strip().upper()
        normalized_identifier = str(identifier or "").strip()

        if normalized_role == "DOCTOR":
            return InteractiveCoreDoctorService().lookup_doctor(normalized_identifier)
        if normalized_role == PRESCRIPT_ROLE_SECRETARY:
            return self.lookup_secretary(normalized_identifier)
        if normalized_role == PRESCRIPT_ROLE_NURSE:
            return self.lookup_employee_with_role(normalized_identifier, PRESCRIPT_ROLE_NURSE)
        return None

    def lookup_secretary(self, identifier):
        with connections["interactive_core"].cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    s.id,
                    s.full_name,
                    s.email,
                    s.phone,
                    s.dni,
                    s.country_id,
                    c.name AS country_name
                FROM api_secretary s
                LEFT JOIN api_country c ON c.id = s.country_id
                WHERE CAST(s.id AS TEXT) = %s
                   OR LOWER(COALESCE(s.email, '')) = LOWER(%s)
                   OR LOWER(COALESCE(s.dni, '')) = LOWER(%s)
                LIMIT 1
                """,
                [identifier, identifier, identifier],
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

    def lookup_employee_with_role(self, identifier, role_code):
        with connections["interactive_core"].cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    u.id AS user_id,
                    ep.id AS employee_id,
                    ep.full_name,
                    u.email,
                    ep.phone,
                    ep.dni,
                    ep.country_id,
                    c.name AS country_name
                FROM api_user u
                INNER JOIN employee_profile ep ON ep.user_id = u.id
                LEFT JOIN api_country c ON c.id = ep.country_id
                WHERE (
                    CAST(u.id AS TEXT) = %s
                    OR CAST(ep.id AS TEXT) = %s
                    OR LOWER(COALESCE(u.username, '')) = LOWER(%s)
                    OR LOWER(COALESCE(u.email, '')) = LOWER(%s)
                    OR LOWER(COALESCE(ep.dni, '')) = LOWER(%s)
                )
                AND EXISTS (
                    SELECT 1
                    FROM api_user_groups ug
                    INNER JOIN auth_group g ON g.id = ug.group_id
                    LEFT JOIN api_roleprofile rp ON rp.group_id = g.id
                    WHERE ug.user_id = u.id
                      AND COALESCE(rp.code, UPPER(g.name)) = %s
                )
                LIMIT 1
                """,
                [identifier, identifier, identifier, identifier, identifier, role_code],
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
