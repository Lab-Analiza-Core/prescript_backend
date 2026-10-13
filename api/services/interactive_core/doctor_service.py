from decimal import Decimal

from django.conf import settings
from django.db import connections
from django.utils import timezone

from api.roles import (
    PRESCRIPT_ROLE_DOCTOR,
    get_primary_prescript_role,
    normalize_prescript_role,
    normalize_prescript_roles,
)

from .client import InteractiveCoreClient


class InteractiveCoreDoctorService:
    def __init__(self, client=None):
        self.client = client or InteractiveCoreClient()

    def get_doctor_by_colegiation_code(self, colegiation_code):
        return self.client.get("doctors/search", params={"colegiation_code": colegiation_code})

    def get_doctor(self, interactive_core_doctor_id):
        if self.client.base_url:
            response = self.client.get(f"doctor/{interactive_core_doctor_id}")
            doctor = response.get("doctor", response) if isinstance(response, dict) else response
            if doctor:
                doctor["specialties"] = doctor.get("specialties") or doctor.get("specialty") or []
                doctor["clinics"] = doctor.get("clinics") or doctor.get("clinic") or []
            return doctor
        return self.get_doctor_from_local_db(interactive_core_doctor_id)

    def update_doctor_public_profile(self, interactive_core_doctor_id, payload):
        allowed_payload = {
            key: value
            for key, value in payload.items()
            if key in {"phone", "public_email", "specialties", "preferences"}
        }
        return self.client.patch(f"doctors/{interactive_core_doctor_id}", allowed_payload)

    def lookup_doctor(self, identifier):
        if self.client.base_url:
            doctor = self.client.get("doctors/lookup", params={"identifier": identifier})
            if doctor:
                self._set_doctor_role_status(doctor)
            return doctor
        return self.lookup_doctor_from_local_db(identifier)

    def lookup_doctor_from_local_db(self, identifier):
        return self._fetch_doctor_from_local_db(identifier=identifier)

    def get_doctor_from_local_db(self, interactive_core_doctor_id):
        return self._fetch_doctor_from_local_db(
            interactive_core_doctor_id=interactive_core_doctor_id,
        )

    def _fetch_doctor_from_local_db(self, interactive_core_doctor_id=None, identifier=""):
        with connections["interactive_core"].cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    d.id,
                    d.full_name,
                    d.email,
                    d.phone,
                    d.dni,
                    d.colegiation_code,
                    d.status,
                    d.final_score,
                    d.user_id,
                    dc.name AS classification_name,
                    d.country_id,
                    c.code AS country_code,
                    c.name AS country_name,
                    c.currency,
                    c.phone_code,
                    c.dni_mask,
                    c.phone_mask,
                    c.timezone
                FROM api_doctor d
                LEFT JOIN doctor_classification dc ON dc.id = d.classification_id
                LEFT JOIN api_country c ON c.id = d.country_id
                WHERE d.id = COALESCE(%s, -1)
                   OR (
                        %s <> ''
                        AND (
                            LOWER(COALESCE(d.email, '')) = LOWER(%s)
                            OR LOWER(COALESCE(d.colegiation_code, '')) = LOWER(%s)
                            OR LOWER(COALESCE(d.dni, '')) = LOWER(%s)
                        )
                   )
                LIMIT 1
                """,
                [
                    interactive_core_doctor_id,
                    identifier,
                    identifier,
                    identifier,
                    identifier,
                ],
            )
            row = cursor.fetchone()

        if row is None:
            return None

        doctor = {
            "id": row[0],
            "full_name": row[1],
            "email": row[2],
            "phone": row[3],
            "dni": row[4],
            "colegiation_code": row[5],
            "status": row[6],
            "final_score": row[7],
            "user_id": row[8],
            "qualification_code": row[9],
            "country_id": row[10],
            "country_code": row[11],
            "country_name": row[12],
            "country": {
                "id": row[10],
                "code": row[11],
                "name": row[12],
                "currency": row[13],
                "phone_code": row[14],
                "dni_mask": row[15],
                "phone_mask": row[16],
                "timezone": row[17],
            },
            "specialties": self._get_specialties(row[0]),
            "clinics": self._get_clinics(row[0]),
        }
        doctor["is_top_doctor"] = self._is_top_doctor(doctor)
        doctor["roles"] = []
        doctor["prescript_roles"] = [PRESCRIPT_ROLE_DOCTOR]
        doctor["prescript_role"] = PRESCRIPT_ROLE_DOCTOR
        doctor["has_prescript_access"] = True
        doctor["has_doctor_role"] = True
        return doctor

    def _get_specialties(self, doctor_id):
        with connections["interactive_core"].cursor() as cursor:
            cursor.execute(
                """
                SELECT s.id, s.name, s.code
                FROM doctor_specialty ds
                INNER JOIN api_specialty s ON s.id = ds.specialty_id
                WHERE ds.doctor_id = %s
                ORDER BY s.name
                """,
                [doctor_id],
            )
            rows = cursor.fetchall()
        return [{"id": row[0], "name": row[1], "code": row[2]} for row in rows]

    def _get_clinics(self, doctor_id):
        with connections["interactive_core"].cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT
                    clinic.id,
                    clinic.name,
                    clinic.address,
                    region.id,
                    region.name
                FROM doctor_medical_clinic doctor_clinic
                INNER JOIN medical_clinic clinic ON clinic.id = doctor_clinic.clinic_id
                LEFT JOIN region ON region.id = clinic.region_id
                WHERE doctor_clinic.doctor_id = %s
                  AND clinic.is_active = TRUE
                ORDER BY clinic.name
                """,
                [doctor_id],
            )
            rows = cursor.fetchall()

        return [
            {
                "id": row[0],
                "name": row[1],
                "address": row[2],
                "region": {"id": row[3], "name": row[4]} if row[3] else None,
            }
            for row in rows
        ]

    def sync_portal_profile_context(self, profile):
        doctor = self.get_doctor(profile.interactive_core_doctor_id)
        if not doctor:
            return False

        profile.specialties = doctor.get("specialties") or []
        profile.clinics = doctor.get("clinics") or []
        profile.last_synced_at = timezone.now()
        profile.save(update_fields=["specialties", "clinics", "last_synced_at", "updated_at"])
        return True

    def _get_user_roles(self, user_id):
        if not user_id:
            return []

        with connections["interactive_core"].cursor() as cursor:
            cursor.execute(
                """
                SELECT COALESCE(rp.code, g.name)
                FROM api_user_groups ug
                INNER JOIN auth_group g ON g.id = ug.group_id
                LEFT JOIN api_roleprofile rp ON rp.group_id = g.id
                WHERE ug.user_id = %s
                ORDER BY g.name
                """,
                [user_id],
            )
            rows = cursor.fetchall()
        return [row[0] for row in rows]

    def _set_doctor_role_status(self, doctor):
        roles = doctor.get("roles") or doctor.get("user_roles") or []
        allowed_portal_roles = set(normalize_prescript_roles(
            settings.PRESCRIPT_INTERACTIVE_CORE_PORTAL_ROLES
        ))
        allowed_doctor_roles = set(normalize_prescript_roles(
            settings.PRESCRIPT_INTERACTIVE_CORE_DOCTOR_ROLES
        )) or {PRESCRIPT_ROLE_DOCTOR}
        normalized_roles = [
            normalize_prescript_role(role)
            for role in roles
            if normalize_prescript_role(role)
        ]
        prescript_roles = [
            role
            for role in dict.fromkeys(normalized_roles)
            if role in allowed_portal_roles
        ]
        doctor["roles"] = roles
        doctor["prescript_roles"] = prescript_roles
        doctor["prescript_role"] = get_primary_prescript_role(prescript_roles)
        doctor["has_prescript_access"] = bool(prescript_roles)
        doctor["has_doctor_role"] = any(role in allowed_doctor_roles for role in normalized_roles)

    def _is_top_doctor(self, doctor):
        classification = (doctor.get("qualification_code") or "").lower()
        if "top" in classification:
            return True

        final_score = doctor.get("final_score")
        if final_score is None:
            return False

        return Decimal(str(final_score)) >= Decimal(str(settings.PRESCRIPT_TOP_DOCTOR_MIN_SCORE))
