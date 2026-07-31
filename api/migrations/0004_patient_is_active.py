from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0003_rename_appointment_doctor__2d158e_idx_appointment_doctor__b1e0a3_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="patient",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
    ]
