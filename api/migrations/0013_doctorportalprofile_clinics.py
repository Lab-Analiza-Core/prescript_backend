from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0012_multi_country_foundation"),
    ]

    operations = [
        migrations.AddField(
            model_name="doctorportalprofile",
            name="clinics",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
