from django.db import models


class Appointment(models.Model):
    STATUS_CHOICES = [
        ("scheduled", "Agendada"),
        ("attended", "Atendida"),
        ("cancelled", "Cancelada"),
        ("no_show", "No se presento"),
        ("rescheduled", "Reprogramada"),
        ("superseded", "Reprogramada y reemplazada"),
    ]

    doctor = models.ForeignKey(
        "DoctorPortalProfile",
        on_delete=models.CASCADE,
        related_name="appointments",
    )
    patient = models.ForeignKey(
        "Patient",
        on_delete=models.CASCADE,
        related_name="appointments",
    )
    scheduled_at = models.DateTimeField()
    duration_minutes = models.PositiveSmallIntegerField(default=30)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="scheduled")
    reason = models.CharField(max_length=255, blank=True, null=True)
    clinical_notes = models.TextField(blank=True, null=True)
    commercial_notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "appointments"
        ordering = ["scheduled_at"]
        indexes = [
            models.Index(fields=["doctor", "scheduled_at"]),
            models.Index(fields=["patient", "scheduled_at"]),
        ]

    def __str__(self):
        return f"{self.patient} - {self.scheduled_at:%Y-%m-%d %H:%M}"
