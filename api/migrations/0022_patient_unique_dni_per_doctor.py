from django.db import migrations, models


def normalize_blank_dni(apps, schema_editor):
    Patient = apps.get_model("api", "Patient")
    Patient.objects.filter(dni="").update(dni=None)


def ensure_no_duplicates(apps, schema_editor):
    Patient = apps.get_model("api", "Patient")
    seen = set()
    for doctor_id, dni in Patient.objects.filter(dni__isnull=False).values_list("doctor_id", "dni"):
        if (doctor_id, dni) in seen:
            raise RuntimeError(
                "Hay pacientes duplicados (mismo doctor y DNI). Ejecute "
                "'python manage.py audit_patient_duplicates --merge' antes de migrar."
            )
        seen.add((doctor_id, dni))


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0021_affiliation_request_roles"),
    ]

    operations = [
        migrations.RunPython(normalize_blank_dni, migrations.RunPython.noop),
        migrations.RunPython(ensure_no_duplicates, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="patient",
            constraint=models.UniqueConstraint(
                fields=["doctor", "dni"],
                condition=models.Q(dni__isnull=False),
                name="uniq_patient_doctor_dni",
            ),
        ),
    ]
