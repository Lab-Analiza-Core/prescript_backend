from django.db import connections

from .client import InteractiveCoreClient


class InteractiveCoreCatalogService:
    def __init__(self, client=None):
        self.client = client or InteractiveCoreClient()

    def list_medicines(self, params=None):
        return self.client.get("catalog/medicines", params=params)

    def list_exams(self, params=None):
        return self.client.get("catalog/exams", params=params)

    def list_specialties(self, params=None):
        return self.client.get("catalog/specialties", params=params)

    def list_specialties_from_local_db(self):
        """Lee las especialidades directo de la BD de Interactive Core (sin API configurada)."""
        with connections["interactive_core"].cursor() as cursor:
            cursor.execute(
                """
                SELECT s.id, s.name, s.code, s.is_active, c.code
                FROM api_specialty s
                LEFT JOIN api_country c ON c.id = s.country_id
                ORDER BY s.id
                """
            )
            rows = cursor.fetchall()
        return [
            {"id": row[0], "name": row[1], "code": row[2], "is_active": row[3], "country_code": row[4]}
            for row in rows
        ]
