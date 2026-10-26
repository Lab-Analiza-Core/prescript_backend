from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from api.models import Appointment, Patient, PatientVitals, Prescription


def _norm_name(patient):
    return " ".join(f"{patient.first_name} {patient.last_name}".lower().split())


class Command(BaseCommand):
    help = (
        "Audita pacientes duplicados. Por defecto solo reporta. Con --merge fusiona los duplicados "
        "exactos (mismo doctor y mismo DNI) en el registro mas antiguo."
    )

    def add_arguments(self, parser):
        parser.add_argument("--merge", action="store_true", help="Fusionar duplicados exactos por (doctor, DNI).")

    def handle(self, *args, **options):
        patients = list(Patient.objects.exclude(dni__isnull=True).exclude(dni="").order_by("created_at", "id"))
        by_dni = defaultdict(list)
        for patient in patients:
            by_dni[(patient.doctor_id, patient.dni)].append(patient)
        exact = {key: group for key, group in by_dni.items() if len(group) > 1}

        self.stdout.write(self.style.MIGRATE_HEADING(f"Duplicados exactos (doctor + DNI): {len(exact)} grupos"))
        for (doctor_id, dni), group in exact.items():
            names = ", ".join(f"#{p.id} {p.full_name}" for p in group)
            self.stdout.write(f"  doctor={doctor_id} dni={dni}: {names}")

        cross = defaultdict(set)
        for patient in patients:
            cross[patient.dni].add(patient.doctor_id)
        shared = {dni: docs for dni, docs in cross.items() if len(docs) > 1}
        self.stdout.write(self.style.MIGRATE_HEADING(f"Mismo DNI con varios doctores: {len(shared)} (informativo)"))
        for dni, docs in shared.items():
            self.stdout.write(f"  dni={dni}: doctores {sorted(docs)}")

        by_name = defaultdict(list)
        for patient in Patient.objects.filter(dni__isnull=True) | Patient.objects.filter(dni=""):
            by_name[(patient.doctor_id, _norm_name(patient))].append(patient)
        suspects = {key: group for key, group in by_name.items() if len(group) > 1}
        self.stdout.write(self.style.MIGRATE_HEADING(f"Mismo nombre sin DNI (revision manual): {len(suspects)}"))
        for (doctor_id, name), group in suspects.items():
            self.stdout.write(f"  doctor={doctor_id} '{name}': ids {[p.id for p in group]}")

        if not options["merge"]:
            self.stdout.write("Solo reporte. Use --merge para fusionar los duplicados exactos.")
            return

        merged = 0
        with transaction.atomic():
            for group in exact.values():
                keeper, *dupes = group
                for dupe in dupes:
                    self._merge(keeper, dupe)
                    merged += 1
        self.stdout.write(self.style.SUCCESS(f"Fusionados {merged} registros duplicados."))

    def _merge(self, keeper, dupe):
        Appointment.objects.filter(patient=dupe).update(patient=keeper)
        Prescription.objects.filter(patient=dupe).update(patient=keeper)
        PatientVitals.objects.filter(patient=dupe).update(patient=keeper)
        for field in ("phone", "email", "birth_date", "sex", "commercial_notes"):
            if not getattr(keeper, field) and getattr(dupe, field):
                setattr(keeper, field, getattr(dupe, field))
        keeper.save()
        # El perfil medico y el score son 1:1; se conservan los del registro principal.
        dupe.delete()
