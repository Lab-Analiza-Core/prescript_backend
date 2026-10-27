from django.db import migrations, models


def copy_medical_area_to_many(apps, schema_editor):
    Organization = apps.get_model("api", "Organization")
    through_model = Organization.medical_areas.through
    rows = Organization.objects.exclude(medical_area_id=None).values_list("id", "medical_area_id")
    through_model.objects.bulk_create(
        [
            through_model(
                organization_id=organization_id,
                specialtycatalogmirror_id=medical_area_id,
            )
            for organization_id, medical_area_id in rows
        ],
        ignore_conflicts=True,
    )


def restore_single_medical_area(apps, schema_editor):
    Organization = apps.get_model("api", "Organization")
    through_model = Organization.medical_areas.through
    first_areas = {}
    for organization_id, medical_area_id in through_model.objects.order_by(
        "organization_id", "specialtycatalogmirror_id"
    ).values_list("organization_id", "specialtycatalogmirror_id"):
        first_areas.setdefault(organization_id, medical_area_id)
    for organization_id, medical_area_id in first_areas.items():
        Organization.objects.filter(pk=organization_id).update(medical_area_id=medical_area_id)


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0024_clinical_integrity_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="medical_areas",
            field=models.ManyToManyField(
                blank=True,
                related_name="organizations",
                to="api.specialtycatalogmirror",
            ),
        ),
        migrations.RunPython(copy_medical_area_to_many, restore_single_medical_area),
        migrations.RemoveField(
            model_name="organization",
            name="medical_area",
        ),
    ]
