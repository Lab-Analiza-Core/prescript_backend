from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0013_doctorportalprofile_clinics"),
    ]

    operations = [
        migrations.AlterField(
            model_name="appointment",
            name="status",
            field=models.CharField(
                choices=[
                    ("scheduled", "Agendada"),
                    ("attended", "Atendida"),
                    ("cancelled", "Cancelada"),
                    ("no_show", "No se presento"),
                    ("rescheduled", "Reprogramada"),
                    ("superseded", "Reprogramada y reemplazada"),
                ],
                default="scheduled",
                max_length=20,
            ),
        ),
    ]
