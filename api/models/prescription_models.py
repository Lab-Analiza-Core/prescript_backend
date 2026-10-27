from django.db import models


class Prescription(models.Model):
    doctor = models.ForeignKey(
        "DoctorPortalProfile",
        on_delete=models.CASCADE,
        related_name="prescriptions",
    )
    patient = models.ForeignKey(
        "Patient",
        on_delete=models.CASCADE,
        related_name="prescriptions",
    )
    appointment = models.ForeignKey(
        "Appointment",
        on_delete=models.SET_NULL,
        related_name="prescriptions",
        blank=True,
        null=True,
    )
    diagnosis = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "prescriptions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["doctor", "-created_at"], name="rx_doctor_created_idx"),
        ]

    def __str__(self):
        return f"Receta #{self.pk} - {self.patient}"


class PrescriptionItem(models.Model):
    prescription = models.ForeignKey(
        Prescription,
        on_delete=models.CASCADE,
        related_name="items",
    )
    # Un item apunta al catalogo sincronizado (medicos de Interactive Core) o al catalogo propio
    # del medico (externos); el serializer exige exactamente uno.
    medicine = models.ForeignKey(
        "MedicineCatalogMirror",
        on_delete=models.PROTECT,
        related_name="prescription_items",
        blank=True,
        null=True,
    )
    doctor_medicine = models.ForeignKey(
        "DoctorMedicine",
        on_delete=models.SET_NULL,
        related_name="prescription_items",
        blank=True,
        null=True,
    )
    # Copia del medicamento al emitir: la receta no cambia si el catalogo se edita o se borra.
    medicine_name = models.CharField(max_length=255, blank=True, default="")
    presentation = models.CharField(max_length=255, blank=True, default="")
    active_ingredient = models.CharField(max_length=255, blank=True, default="")
    dosage = models.CharField(max_length=120)
    frequency = models.CharField(max_length=120)
    duration = models.CharField(max_length=120)
    instructions = models.TextField(blank=True, null=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "prescription_items"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.medicine_name} - {self.prescription}"
