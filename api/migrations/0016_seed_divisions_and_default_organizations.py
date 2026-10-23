from django.db import migrations


DIVISIONS = {
    "GT": (
        "Departamento",
        [
            "Alta Verapaz", "Baja Verapaz", "Chimaltenango", "Chiquimula", "El Progreso",
            "Escuintla", "Guatemala", "Huehuetenango", "Izabal", "Jalapa", "Jutiapa", "Petén",
            "Quetzaltenango", "Quiché", "Retalhuleu", "Sacatepéquez", "San Marcos", "Santa Rosa",
            "Sololá", "Suchitepéquez", "Totonicapán", "Zacapa",
        ],
    ),
    "HN": (
        "Departamento",
        [
            "Atlántida", "Choluteca", "Colón", "Comayagua", "Copán", "Cortés", "El Paraíso",
            "Francisco Morazán", "Gracias a Dios", "Intibucá", "Islas de la Bahía", "La Paz",
            "Lempira", "Ocotepeque", "Olancho", "Santa Bárbara", "Valle", "Yoro",
        ],
    ),
    "SV": (
        "Departamento",
        [
            "Ahuachapán", "Cabañas", "Chalatenango", "Cuscatlán", "La Libertad", "La Paz",
            "La Unión", "Morazán", "San Miguel", "San Salvador", "San Vicente", "Santa Ana",
            "Sonsonate", "Usulután",
        ],
    ),
    "CR": (
        "Provincia",
        ["Alajuela", "Cartago", "Guanacaste", "Heredia", "Limón", "Puntarenas", "San José"],
    ),
}

PROFILE_MODELS = ("DoctorPortalProfile", "SecretaryPortalProfile", "NursePortalProfile")


def seed_and_backfill(apps, schema_editor):
    Country = apps.get_model("api", "Country")
    CountryDivision = apps.get_model("api", "CountryDivision")
    Organization = apps.get_model("api", "Organization")

    for country in Country.objects.filter(code__in=DIVISIONS):
        division_type, names = DIVISIONS[country.code]
        for name in names:
            CountryDivision.objects.get_or_create(
                country=country,
                name=name,
                defaults={"division_type": division_type},
            )

    # Una organizacion de Interactive Core por pais para los perfiles ya existentes.
    for country in Country.objects.all():
        organization, _ = Organization.objects.get_or_create(
            country=country,
            is_interactive_core=True,
            defaults={"name": f"Interactive Core {country.name}", "status": "active"},
        )
        for model_name in PROFILE_MODELS:
            apps.get_model("api", model_name).objects.filter(
                country=country,
                organization__isnull=True,
            ).update(organization=organization)


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0015_organizations_foundation"),
    ]

    operations = [
        # Reversible sin borrar datos: las tablas se eliminan al revertir 0015.
        migrations.RunPython(seed_and_backfill, migrations.RunPython.noop),
    ]
