from django.db import migrations


DOCTOR_SEX_BY_INTERACTIVE_CORE_ID = {
    1430: "M",  # Aaron Edgardo Carias Gutierrez
    357: "F",  # Ada Lizzeth Cordova Mancedo
    1945: "M",  # Alan Orlando Morel Paz
    999: "M",  # Doc
    1357: "F",  # Elisa Josefina Sierra Osorio
    311: "M",  # Luis Andres Toro Vallecillo
    316: "M",  # Marlon Fabricio Martinez Varela
    3582: "M",  # Randolfo Padilla
}


def set_registered_doctor_sex(apps, schema_editor):
    DoctorPortalProfile = apps.get_model("api", "DoctorPortalProfile")
    for interactive_core_doctor_id, sex in DOCTOR_SEX_BY_INTERACTIVE_CORE_ID.items():
        DoctorPortalProfile.objects.filter(
            interactive_core_doctor_id=interactive_core_doctor_id,
            sex__isnull=True,
        ).update(sex=sex)


def unset_registered_doctor_sex(apps, schema_editor):
    DoctorPortalProfile = apps.get_model("api", "DoctorPortalProfile")
    DoctorPortalProfile.objects.filter(
        interactive_core_doctor_id__in=DOCTOR_SEX_BY_INTERACTIVE_CORE_ID,
        sex__in=DOCTOR_SEX_BY_INTERACTIVE_CORE_ID.values(),
    ).update(sex=None)


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0010_doctorportalprofile_sex"),
    ]

    operations = [
        migrations.RunPython(set_registered_doctor_sex, unset_registered_doctor_sex),
    ]
