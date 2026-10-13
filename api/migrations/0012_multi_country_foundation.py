from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


COUNTRIES = {
    "CR": {
        "name": "Costa Rica",
        "currency": "CRC",
        "phone_code": "+506",
        "dni_mask": "9-9999-9999",
        "phone_mask": "9999-9999",
        "timezone": "America/Costa_Rica",
    },
    "GT": {
        "name": "Guatemala",
        "currency": "GTQ",
        "phone_code": "+502",
        "dni_mask": "9999-99999-9999",
        "phone_mask": "9999-9999",
        "timezone": "America/Guatemala",
    },
    "HN": {
        "name": "Honduras",
        "currency": "HNL",
        "phone_code": "+504",
        "dni_mask": "9999-9999-99999",
        "phone_mask": "9999-9999",
        "timezone": "America/Tegucigalpa",
    },
    "SV": {
        "name": "El Salvador",
        "currency": "USD",
        "phone_code": "+503",
        "dni_mask": "",
        "phone_mask": "9999-9999",
        "timezone": "America/El_Salvador",
    },
}


def seed_and_backfill(apps, schema_editor):
    Country = apps.get_model("api", "Country")
    UserCountryAccess = apps.get_model("api", "UserCountryAccess")
    Doctor = apps.get_model("api", "DoctorPortalProfile")
    Secretary = apps.get_model("api", "SecretaryPortalProfile")
    Nurse = apps.get_model("api", "NursePortalProfile")
    Medicine = apps.get_model("api", "MedicineCatalogMirror")
    Exam = apps.get_model("api", "ExamCatalogMirror")

    countries = {}
    for code, defaults in COUNTRIES.items():
        countries[code], _ = Country.objects.update_or_create(
            code=code,
            defaults={**defaults, "is_active": True},
        )

    names = {values["name"].casefold(): code for code, values in COUNTRIES.items()}

    def resolve(value):
        normalized = str(value or "").strip()
        code = normalized.upper() if normalized.upper() in countries else names.get(normalized.casefold())
        return countries.get(code or "HN", countries["HN"])

    for model in (Doctor, Secretary, Nurse):
        for profile in model.objects.all().iterator():
            profile.country_ref = resolve(profile.country)
            profile.save(update_fields=["country_ref"])

    Medicine.objects.filter(country__isnull=True).update(country=countries["HN"])
    Exam.objects.filter(country__isnull=True).update(country=countries["HN"])

    profile_models = (Doctor, Secretary, Nurse)
    for model in profile_models:
        for profile in model.objects.select_related("user", "country_ref").iterator():
            role_names = list(profile.user.groups.values_list("name", flat=True))
            if not role_names:
                role_names = [
                    "DOCTOR" if model is Doctor else "SECRETARY" if model is Secretary else "NURSE"
                ]
            for role_name in role_names:
                role_code = role_name.upper()
                if role_code.startswith("ADMIN_"):
                    role_code = "ADMIN"
                UserCountryAccess.objects.get_or_create(
                    user=profile.user,
                    role_code=role_code,
                    country=profile.country_ref,
                    defaults={"is_active": True},
                )

    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    for user in User.objects.filter(groups__name="ADMIN").distinct().iterator():
        UserCountryAccess.objects.get_or_create(
            user=user,
            role_code="ADMIN",
            country=None,
            defaults={"is_active": True},
        )

    for code, country in countries.items():
        for user in User.objects.filter(groups__name=f"ADMIN_{code}").distinct().iterator():
            UserCountryAccess.objects.get_or_create(
                user=user,
                role_code="ADMIN",
                country=country,
                defaults={"is_active": True},
            )


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0011_seed_registered_doctor_sex"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Country",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("interactive_core_id", models.PositiveIntegerField(blank=True, null=True, unique=True)),
                ("code", models.CharField(max_length=3, unique=True)),
                ("name", models.CharField(max_length=100, unique=True)),
                ("currency", models.CharField(blank=True, max_length=3)),
                ("phone_code", models.CharField(blank=True, max_length=10)),
                ("dni_mask", models.CharField(blank=True, max_length=50)),
                ("phone_mask", models.CharField(blank=True, max_length=50)),
                ("timezone", models.CharField(blank=True, max_length=50)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "countries", "ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="UserCountryAccess",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role_code", models.CharField(max_length=50)),
                ("is_active", models.BooleanField(default=True)),
                ("source", models.CharField(default="local", max_length=30)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("country", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="user_accesses", to="api.country")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="prescript_country_accesses", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "user_country_access", "ordering": ["user_id", "role_code", "country__name"]},
        ),
        migrations.AddField(
            model_name="doctorportalprofile",
            name="country_ref",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="doctors", to="api.country"),
        ),
        migrations.AddField(
            model_name="secretaryportalprofile",
            name="country_ref",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="secretaries", to="api.country"),
        ),
        migrations.AddField(
            model_name="nurseportalprofile",
            name="country_ref",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="nurses", to="api.country"),
        ),
        migrations.AddField(
            model_name="medicinecatalogmirror",
            name="country",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="medicine_catalog", to="api.country"),
        ),
        migrations.AddField(
            model_name="examcatalogmirror",
            name="country",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="exam_catalog", to="api.country"),
        ),
        migrations.AlterField(
            model_name="medicinecatalogmirror",
            name="interactive_core_product_id",
            field=models.PositiveIntegerField(),
        ),
        migrations.AlterField(
            model_name="medicinecatalogmirror",
            name="code",
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AlterField(
            model_name="examcatalogmirror",
            name="interactive_core_exam_id",
            field=models.PositiveIntegerField(),
        ),
        migrations.RunPython(seed_and_backfill, migrations.RunPython.noop),
        migrations.RemoveField(model_name="doctorportalprofile", name="country"),
        migrations.RemoveField(model_name="secretaryportalprofile", name="country"),
        migrations.RemoveField(model_name="nurseportalprofile", name="country"),
        migrations.RenameField(model_name="doctorportalprofile", old_name="country_ref", new_name="country"),
        migrations.RenameField(model_name="secretaryportalprofile", old_name="country_ref", new_name="country"),
        migrations.RenameField(model_name="nurseportalprofile", old_name="country_ref", new_name="country"),
        migrations.AlterField(
            model_name="medicinecatalogmirror",
            name="country",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="medicine_catalog", to="api.country"),
        ),
        migrations.AlterField(
            model_name="examcatalogmirror",
            name="country",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="exam_catalog", to="api.country"),
        ),
        migrations.AddConstraint(model_name="usercountryaccess", constraint=models.UniqueConstraint(fields=("user", "role_code", "country"), name="user_role_country_unique")),
        migrations.AddConstraint(model_name="usercountryaccess", constraint=models.UniqueConstraint(condition=models.Q(("country__isnull", True)), fields=("user", "role_code"), name="user_global_role_unique")),
        migrations.AddIndex(model_name="usercountryaccess", index=models.Index(fields=["user", "is_active"], name="user_country_active_idx")),
        migrations.AddIndex(model_name="usercountryaccess", index=models.Index(fields=["country", "role_code"], name="country_role_idx")),
        migrations.AddConstraint(model_name="medicinecatalogmirror", constraint=models.UniqueConstraint(fields=("country", "interactive_core_product_id"), name="med_country_product_uniq")),
        migrations.AddConstraint(model_name="medicinecatalogmirror", constraint=models.UniqueConstraint(condition=models.Q(("code__isnull", False)), fields=("country", "code"), name="medicine_country_code_unique")),
        migrations.AddIndex(model_name="medicinecatalogmirror", index=models.Index(fields=["country", "is_active", "name"], name="medicine_country_active_idx")),
        migrations.AddConstraint(model_name="examcatalogmirror", constraint=models.UniqueConstraint(fields=("country", "interactive_core_exam_id"), name="exam_country_product_unique")),
        migrations.AddIndex(model_name="examcatalogmirror", index=models.Index(fields=["country", "is_active", "name"], name="exam_country_active_idx")),
    ]
