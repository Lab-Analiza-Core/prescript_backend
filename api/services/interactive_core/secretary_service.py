from django.db import connections


class InteractiveCoreSecretaryService:
    def get_assigned_doctor_ids(self, secretaria_interactivecore_id):
        if not secretaria_interactivecore_id:
            return []

        with connections["interactive_core"].cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT d.id
                FROM doctor_secretary ds
                INNER JOIN api_doctor d ON d.id = ds.doctor_id
                WHERE ds.secretary_id = %s
                """,
                [secretaria_interactivecore_id],
            )
            rows = cursor.fetchall()

        return [row[0] for row in rows]
