from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0023_theme_settings"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="appointment",
            name="appointment_doctor__b1e0a3_idx",
        ),
        migrations.AddIndex(
            model_name="appointment",
            index=models.Index(
                condition=models.Q(status__in=("scheduled", "rescheduled")),
                fields=["doctor", "scheduled_at"],
                name="appt_active_doctor_time_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="appointment",
            constraint=models.CheckConstraint(
                condition=models.Q(duration_minutes__gt=0, duration_minutes__lte=1440),
                name="appointment_duration_valid",
            ),
        ),
        migrations.AddIndex(
            model_name="patientvitals",
            index=models.Index(
                fields=["patient", "-recorded_at"],
                name="vitals_patient_time_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="prescription",
            index=models.Index(
                fields=["doctor", "-created_at"],
                name="rx_doctor_created_idx",
            ),
        ),
    ]
