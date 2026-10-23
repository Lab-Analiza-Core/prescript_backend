from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0020_affiliation_requests"),
    ]

    operations = [
        migrations.RenameField("affiliationrequest", "interactive_core_doctor_id", "interactive_core_id"),
        migrations.RenameField("affiliationrequest", "doctor_name", "full_name"),
        migrations.RenameField("affiliationrequest", "colegiation_code", "identifier"),
        migrations.AddField(
            model_name="affiliationrequest",
            name="role",
            field=models.CharField(
                choices=[("DOCTOR", "Doctor"), ("SECRETARY", "Secretaria"), ("NURSE", "Enfermera")],
                default="DOCTOR",
                max_length=20,
            ),
        ),
    ]
