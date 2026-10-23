from django.conf import settings
from django.db import transaction
from django.utils import timezone

from api.models import Country, SpecialtyCatalogMirror
from api.services.country_service import normalize_country_code
from api.services.interactive_core import InteractiveCoreCatalogService


def _extract_rows(payload):
    if isinstance(payload, dict):
        for key in ("results", "data", "items", "specialties"):
            if isinstance(payload.get(key), list):
                return payload[key]
        return []
    return payload if isinstance(payload, list) else []


class SpecialtySyncService:
    """Espeja el catalogo de especialidades de Interactive Core (area medica)."""

    def __init__(self, catalog_service=None):
        self.catalog_service = catalog_service or InteractiveCoreCatalogService()

    def fetch_rows(self):
        # Sin API configurada se usa la BD de Interactive Core, igual que el resto de servicios de IC.
        if not settings.INTERACTIVE_CORE_API_BASE_URL:
            return self.catalog_service.list_specialties_from_local_db()
        rows = []
        params = {}
        payload = self.catalog_service.list_specialties(params=params)
        rows.extend(_extract_rows(payload))
        # Respuestas paginadas al estilo DRF: seguir "next" via el parametro page.
        page = 1
        while isinstance(payload, dict) and payload.get("next"):
            page += 1
            payload = self.catalog_service.list_specialties(params={"page": page})
            rows.extend(_extract_rows(payload))
        return rows

    @transaction.atomic
    def sync(self, deactivate_missing=True):
        now = timezone.now()
        seen_ids = []
        created = updated = 0
        countries = {country.code: country for country in Country.objects.all()}

        for row in self.fetch_rows():
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            external_id = row.get("id")
            if not name or external_id is None:
                continue

            country = countries.get(normalize_country_code(row.get("country_code") or row.get("country")))
            defaults = {
                "country": country,
                "name": name[:150],
                "is_active": row.get("is_active", True) is not False,
                "last_synced_at": now,
            }
            # El nombre es unico: si ya existe una especialidad local con ese nombre, se enlaza.
            obj = (
                SpecialtyCatalogMirror.objects.filter(interactive_core_id=external_id).first()
                or SpecialtyCatalogMirror.objects.filter(
                    name__iexact=name, country=country, interactive_core_id__isnull=True
                ).first()
            )
            if obj is None:
                SpecialtyCatalogMirror.objects.create(interactive_core_id=external_id, **defaults)
                created += 1
            else:
                for field, value in {**defaults, "interactive_core_id": external_id}.items():
                    setattr(obj, field, value)
                obj.save()
                updated += 1
            seen_ids.append(external_id)

        deactivated = 0
        if deactivate_missing and seen_ids:
            deactivated = (
                SpecialtyCatalogMirror.objects.filter(interactive_core_id__isnull=False, is_active=True)
                .exclude(interactive_core_id__in=seen_ids)
                .update(is_active=False, updated_at=now)
            )
        return {"created": created, "updated": updated, "deactivated": deactivated}
