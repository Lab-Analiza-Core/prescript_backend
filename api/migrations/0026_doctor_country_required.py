import django.db.models.deletion
from django.db import migrations, models


def fill_country_from_organization(apps, schema_editor):
    DoctorPortalProfile = apps.get_model("api", "DoctorPortalProfile")
    for doctor in DoctorPortalProfile.objects.filter(country__isnull=True, organization__isnull=False).select_related(
        "organization"
    ):
        doctor.country_id = doctor.organization.country_id
        doctor.save(update_fields=["country"])

    orphan_ids = list(DoctorPortalProfile.objects.filter(country__isnull=True).values_list("id", flat=True))
    if orphan_ids:
        raise RuntimeError(
            "Hay medicos sin pais y sin organizacion que lo defina; asignelos a una organizacion "
            f"o indique su pais antes de migrar. Ids: {orphan_ids}"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0025_organization_medical_areas"),
    ]

    operations = [
        migrations.RunPython(fill_country_from_organization, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="doctorportalprofile",
            name="country",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="doctors",
                to="api.country",
            ),
        ),
    ]
