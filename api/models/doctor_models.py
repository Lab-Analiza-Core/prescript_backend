from django.conf import settings
from django.db import models


class DoctorPortalProfile(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pendiente"),
        ("active", "Activo"),
        ("inactive", "Inactivo"),
    ]
    SEX_CHOICES = [
        ("F", "Femenino"),
        ("M", "Masculino"),
        ("O", "Otro"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="doctor_portal_profile",
    )
    interactive_core_doctor_id = models.PositiveIntegerField(unique=True)
    full_name = models.CharField(max_length=255)
    sex = models.CharField(max_length=1, choices=SEX_CHOICES, blank=True, null=True)
    colegiation_code = models.CharField(max_length=50, blank=True, null=True)
    qualification_code = models.CharField(max_length=100, blank=True, null=True)
    final_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    country = models.CharField(max_length=80, blank=True, null=True)
    company = models.CharField(max_length=120, blank=True, null=True)
    zone = models.CharField(max_length=120, blank=True, null=True)
    phone = models.CharField(max_length=25, blank=True, null=True)
    public_email = models.EmailField(blank=True, null=True)
    specialties = models.JSONField(default=list, blank=True)
    preferences = models.JSONField(default=dict, blank=True)
    is_top_doctor = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    last_synced_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "doctor_portal_profile"
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name


class DoctorMedicinePreference(models.Model):
    CATEGORY_CHOICES = [
        ("favorite", "Favorito"),
        ("complementary", "Complementario"),
        ("undetermined", "Indeterminado"),
    ]

    doctor = models.ForeignKey(
        DoctorPortalProfile,
        on_delete=models.CASCADE,
        related_name="medicine_preferences",
    )
    medicine = models.ForeignKey(
        "MedicineCatalogMirror",
        on_delete=models.CASCADE,
        related_name="doctor_preferences",
    )
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default="undetermined",
    )
    commercial_house_priority = models.PositiveIntegerField(default=0)
    sort_order = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "doctor_medicine_preferences"
        unique_together = ("doctor", "medicine")
        ordering = ["category", "sort_order", "medicine__name"]

    def __str__(self):
        return f"{self.doctor} - {self.medicine}"


class DoctorCredential(models.Model):
    doctor = models.OneToOneField(
        DoctorPortalProfile,
        on_delete=models.CASCADE,
        related_name="credential",
    )
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True)
    is_portal_enabled = models.BooleanField(default=True)
    password_set_at = models.DateTimeField(blank=True, null=True)
    last_password_change_at = models.DateTimeField(blank=True, null=True)
    last_login_at = models.DateTimeField(blank=True, null=True)
    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "doctor_credentials"
        ordering = ["username"]

    def __str__(self):
        return self.username


class SecretaryPortalProfile(models.Model):
    STATUS_CHOICES = [
        ("active", "Activo"),
        ("inactive", "Inactivo"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="secretary_portal_profile",
    )
    secretaria_interactivecore_id = models.PositiveIntegerField(unique=True)
    full_name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=25, blank=True, null=True)
    country = models.CharField(max_length=80, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    last_synced_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "secretary_portal_profile"
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name


class NursePortalProfile(models.Model):
    STATUS_CHOICES = [
        ("active", "Activo"),
        ("inactive", "Inactivo"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="nurse_portal_profile",
    )
    interactive_core_user_id = models.PositiveIntegerField(unique=True)
    interactive_core_employee_id = models.PositiveIntegerField(unique=True)
    full_name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=25, blank=True, null=True)
    country = models.CharField(max_length=80, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    last_synced_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "nurse_portal_profile"
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name


class DoctorAccessLog(models.Model):
    EVENT_CHOICES = [
        ("login_success", "Inicio de sesion exitoso"),
        ("login_failed", "Inicio de sesion fallido"),
        ("logout", "Cierre de sesion"),
        ("password_set", "Contrasena establecida"),
        ("password_reset", "Contrasena restablecida"),
        ("profile_updated", "Perfil actualizado"),
    ]

    doctor = models.ForeignKey(
        DoctorPortalProfile,
        on_delete=models.CASCADE,
        related_name="access_logs",
    )
    event_type = models.CharField(max_length=40, choices=EVENT_CHOICES)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "doctor_access_logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["doctor", "created_at"]),
            models.Index(fields=["event_type", "created_at"]),
        ]

    def __str__(self):
        return f"{self.doctor} - {self.event_type}"
