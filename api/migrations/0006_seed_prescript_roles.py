from django.db import migrations


PRESCRIPT_ROLES = ["DOCTOR", "SECRETARY", "NURSE", "ADMIN", "COUNTRY_MANAGER"]


def forwards(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for role in PRESCRIPT_ROLES:
        Group.objects.get_or_create(name=role)


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0005_doctorportalprofile_company_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
