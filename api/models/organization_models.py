from django.conf import settings
from django.db import models
from django.db.models import Q

from api.roles import (
    PRESCRIPT_ROLE_DOCTOR,
    PRESCRIPT_ROLE_NURSE,
    PRESCRIPT_ROLE_ORG_ADMIN,
    PRESCRIPT_ROLE_PATIENT,
    PRESCRIPT_ROLE_SECRETARY,
)

ORIGIN_INTERACTIVE_CORE = "interactive_core"
ORIGIN_SELF_REGISTERED = "self_registered"
ORIGIN_CHOICES = [
    (ORIGIN_INTERACTIVE_CORE, "Interactive Core"),
    (ORIGIN_SELF_REGISTERED, "Autorregistrado (externo)"),
]


class SpecialtyCatalogMirror(models.Model):
    """Espejo del catalogo de especialidades de Interactive Core (area medica)."""

    interactive_core_id = models.PositiveIntegerField(unique=True, blank=True, null=True)
    # En Interactive Core el catalogo es por pais: la misma especialidad tiene un id por pais.
    country = models.ForeignKey(
        "Country",
        on_delete=models.CASCADE,
        related_name="specialties",
        blank=True,
        null=True,
    )
    name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)
    last_synced_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "specialty_catalog_mirror"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["country", "name"], name="specialty_country_name_unique"),
        ]

    def __str__(self):
        return self.name


class CountryDivision(models.Model):
    """Division geografica de primer nivel; su etiqueta depende del pais."""

    country = models.ForeignKey("Country", on_delete=models.CASCADE, related_name="divisions")
    name = models.CharField(max_length=120)
    division_type = models.CharField(max_length=40, default="Departamento")
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "country_divisions"
        ordering = ["country__name", "name"]
        constraints = [
            models.UniqueConstraint(fields=["country", "name"], name="country_division_unique"),
        ]

    def __str__(self):
        return f"{self.name} ({self.country.code})"


class Organization(models.Model):
    STATUS_CHOICES = [
        ("active", "Activa"),
        ("suspended", "Suspendida"),
    ]

    name = models.CharField(max_length=200)
    country = models.ForeignKey("Country", on_delete=models.PROTECT, related_name="organizations")
    division = models.ForeignKey(
        CountryDivision,
        on_delete=models.PROTECT,
        related_name="organizations",
        blank=True,
        null=True,
    )
    medical_area = models.ForeignKey(
        SpecialtyCatalogMirror,
        on_delete=models.PROTECT,
        related_name="organizations",
        blank=True,
        null=True,
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    # Organizacion que recibe a los usuarios afiliados a Interactive Core de su pais.
    is_interactive_core = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "organizations"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["country", "name"], name="organization_country_name_unique"),
            models.UniqueConstraint(
                fields=["country"],
                condition=Q(is_interactive_core=True),
                name="organization_one_interactive_core_per_country",
            ),
        ]

    def __str__(self):
        return self.name


class OrganizationInvitation(models.Model):
    ROLE_CHOICES = [
        (PRESCRIPT_ROLE_DOCTOR, "Doctor"),
        (PRESCRIPT_ROLE_SECRETARY, "Secretaria"),
        (PRESCRIPT_ROLE_NURSE, "Enfermera"),
        (PRESCRIPT_ROLE_PATIENT, "Paciente"),
        (PRESCRIPT_ROLE_ORG_ADMIN, "Administrador de organizacion"),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="invitations")
    code = models.CharField(max_length=32, unique=True)
    role = models.CharField(max_length=30, choices=ROLE_CHOICES)
    expires_at = models.DateTimeField(blank=True, null=True)
    max_uses = models.PositiveIntegerField(blank=True, null=True)
    uses = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_invitations",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "organization_invitations"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "role", "is_active"], name="org_invite_lookup_idx")]

    def __str__(self):
        return f"{self.organization} - {self.role}"


class OrganizationAdminProfile(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pendiente de aprobacion"),
        ("active", "Activo"),
        ("inactive", "Inactivo"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="org_admin_profile",
    )
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="admins")
    full_name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=25, blank=True, null=True)
    country = models.ForeignKey("Country", on_delete=models.PROTECT, related_name="org_admins")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="approved_org_admins",
        blank=True,
        null=True,
    )
    approved_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "org_admin_profile"
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name


class PatientPortalProfile(models.Model):
    STATUS_CHOICES = [
        ("active", "Activo"),
        ("inactive", "Inactivo"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="patient_portal_profile",
    )
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="patient_accounts")
    full_name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=25, blank=True, null=True)
    country = models.ForeignKey("Country", on_delete=models.PROTECT, related_name="patient_accounts")
    document_type = models.CharField(max_length=30, default="DNI")
    document_number = models.CharField(max_length=50)
    # La cuenta solo ve historial una vez que el documento se verifico por OTP.
    history_verified_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "patient_portal_profile"
        ordering = ["full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["country", "document_type", "document_number"],
                name="patient_account_document_unique",
            ),
        ]

    def __str__(self):
        return self.full_name


class TermsVersion(models.Model):
    version = models.CharField(max_length=30, unique=True)
    title = models.CharField(max_length=200, default="Terminos y condiciones")
    content = models.TextField()
    is_current = models.BooleanField(default=False)
    published_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "terms_versions"
        ordering = ["-published_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_current"],
                condition=Q(is_current=True),
                name="terms_single_current_version",
            ),
        ]

    def __str__(self):
        return self.version


class TermsAcceptance(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="terms_acceptances")
    terms = models.ForeignKey(TermsVersion, on_delete=models.PROTECT, related_name="acceptances")
    accepted_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)

    class Meta:
        db_table = "terms_acceptances"
        ordering = ["-accepted_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "terms"], name="terms_acceptance_unique"),
        ]


class OneTimeCode(models.Model):
    PURPOSE_PATIENT_HISTORY = "patient_history"
    PURPOSE_IC_AFFILIATION = "ic_affiliation"

    purpose = models.CharField(max_length=40)
    # Identifica a quien pertenece el codigo (por ejemplo, el id del usuario).
    target = models.CharField(max_length=254)
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    consumed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "one_time_codes"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["purpose", "target", "-created_at"], name="otp_lookup_idx")]


class SecretaryDoctorAssignment(models.Model):
    """Vinculo local secretaria-doctor para quienes no vienen de Interactive Core."""

    secretary = models.ForeignKey(
        "SecretaryPortalProfile", on_delete=models.CASCADE, related_name="doctor_assignments"
    )
    doctor = models.ForeignKey("DoctorPortalProfile", on_delete=models.CASCADE, related_name="secretary_assignments")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_secretary_assignments",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "secretary_doctor_assignments"
        constraints = [
            models.UniqueConstraint(fields=["secretary", "doctor"], name="secretary_doctor_unique"),
        ]


class AffiliationRequest(models.Model):
    """Personal de Interactive Core sin correo en su ficha: un administrador valida el vinculo.

    El solicitante verifico por OTP que controla el correo indicado, pero eso no prueba que sea
    el doctor de la ficha; mientras esta pendiente su cuenta existe inactiva y sin perfil clinico.
    """

    STATUS_CHOICES = [
        ("pending", "Pendiente"),
        ("approved", "Aprobada"),
        ("rejected", "Rechazada"),
    ]

    ROLE_CHOICES = [
        (PRESCRIPT_ROLE_DOCTOR, "Doctor"),
        (PRESCRIPT_ROLE_SECRETARY, "Secretaria"),
        (PRESCRIPT_ROLE_NURSE, "Enfermera"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="affiliation_request")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=PRESCRIPT_ROLE_DOCTOR)
    # Id de la ficha en Interactive Core: doctor, secretaria o usuario de la enfermera segun el rol.
    interactive_core_id = models.PositiveIntegerField(db_index=True)
    # Copia de la ficha al momento de solicitar, para que el administrador la compare.
    full_name = models.CharField(max_length=255)
    # Colegiacion en doctores; documento en secretarias y enfermeras.
    identifier = models.CharField(max_length=50, blank=True, null=True)
    country = models.ForeignKey(
        "Country", on_delete=models.PROTECT, related_name="affiliation_requests", blank=True, null=True
    )
    email = models.EmailField()
    contact_phone = models.CharField(max_length=25, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="decided_affiliation_requests",
        blank=True,
        null=True,
    )
    decided_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "affiliation_requests"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "country"], name="affiliation_status_idx")]
