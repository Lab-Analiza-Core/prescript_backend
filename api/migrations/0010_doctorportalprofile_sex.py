from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0009_nurseportalprofile"),
    ]

    operations = [
        migrations.AddField(
            model_name="doctorportalprofile",
            name="sex",
            field=models.CharField(
                blank=True,
                choices=[("F", "Femenino"), ("M", "Masculino"), ("O", "Otro")],
                max_length=1,
                null=True,
            ),
        ),
    ]
