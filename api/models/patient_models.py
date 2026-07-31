from django.db import models


class Patient(models.Model):
    SEX_CHOICES = [
        ("F", "Femenino"),
        ("M", "Masculino"),
        ("O", "Otro"),
    ]

    doctor = models.ForeignKey(
        "DoctorPortalProfile",
        on_delete=models.CASCADE,
        related_name="patients",
    )
    first_name = models.CharField(max_length=120)
    last_name = models.CharField(max_length=120)
    dni = models.CharField(max_length=50, blank=True, null=True)
    phone = models.CharField(max_length=25, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    birth_date = models.DateField(blank=True, null=True)
    sex = models.CharField(max_length=1, choices=SEX_CHOICES, blank=True, null=True)
    commercial_notes = models.TextField(blank=True, null=True)
    patient_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "patients"
        ordering = ["last_name", "first_name"]
        indexes = [
            models.Index(fields=["doctor", "dni"]),
            models.Index(fields=["doctor", "last_name", "first_name"]),
        ]

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return self.full_name


class PatientMedicalProfile(models.Model):
    patient = models.OneToOneField(
        Patient,
        on_delete=models.CASCADE,
        related_name="medical_profile",
    )
    allergies = models.JSONField(default=list, blank=True)
    chronic_conditions = models.JSONField(default=list, blank=True)
    blood_type = models.CharField(max_length=5, blank=True, null=True)
    clinical_notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "patient_medical_profile"

    def __str__(self):
        return f"Perfil medico - {self.patient}"


class PatientVitals(models.Model):
    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name="vitals",
    )
    appointment = models.OneToOneField(
        "Appointment",
        on_delete=models.CASCADE,
        related_name="vitals",
        blank=True,
        null=True,
    )
    blood_pressure_systolic = models.PositiveSmallIntegerField(blank=True, null=True)
    blood_pressure_diastolic = models.PositiveSmallIntegerField(blank=True, null=True)
    oxygen_saturation = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
    )
    temperature = models.DecimalField(max_digits=4, decimal_places=1, blank=True, null=True)
    height_cm = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    weight_kg = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "patient_vitals"
        ordering = ["-recorded_at"]

    def __str__(self):
        return f"Signos vitales - {self.patient} - {self.recorded_at:%Y-%m-%d}"


class PatientScore(models.Model):
    patient = models.OneToOneField(
        Patient,
        on_delete=models.CASCADE,
        related_name="score_detail",
    )
    profile_completeness_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    punctuality_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    attendance_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    cancellation_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    no_show_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    final_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    classification = models.CharField(max_length=50, blank=True, null=True)
    calculated_at = models.DateTimeField(blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "patient_score"
        ordering = ["-final_score", "patient__last_name"]

    def __str__(self):
        return f"Score {self.final_score} - {self.patient}"
