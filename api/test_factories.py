from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from api.models import Appointment, Country, DoctorPortalProfile, NursePortalProfile, Patient, PatientVitals, SecretaryPortalProfile


DEFAULT_PASSWORD = "Doctor1234!"


def get_country(value="HN"):
    if isinstance(value, Country):
        return value
    return Country.objects.get(code=str(value or "HN").upper())


def create_user(username, email=None, password=DEFAULT_PASSWORD, roles=None, **extra_fields):
    email = email or username
    user = get_user_model().objects.create_user(
        username=username,
        email=email,
        password=password,
        **extra_fields,
    )
    for role in roles or []:
        Group.objects.get_or_create(name=role)[0].user_set.add(user)
    return user


def create_doctor(user=None, interactive_core_doctor_id=200, **overrides):
    user = user or create_user(
        f"doctor-{interactive_core_doctor_id}@test.local",
        roles=["DOCTOR"],
    )
    defaults = {
        "user": user,
        "interactive_core_doctor_id": interactive_core_doctor_id,
        "full_name": "Dra. Prescript",
        "status": "active",
        "country": get_country(overrides.pop("country", "HN")),
    }
    defaults.update(overrides)
    return DoctorPortalProfile.objects.create(**defaults)


def create_secretary(user=None, secretaria_interactivecore_id=700, **overrides):
    user = user or create_user(
        f"secretary-{secretaria_interactivecore_id}@test.local",
        roles=["SECRETARY"],
    )
    defaults = {
        "user": user,
        "secretaria_interactivecore_id": secretaria_interactivecore_id,
        "full_name": "Secretaria Prescript",
        "email": user.email,
        "status": "active",
        "country": get_country(overrides.pop("country", "HN")),
    }
    defaults.update(overrides)
    return SecretaryPortalProfile.objects.create(**defaults)


def create_nurse(user=None, interactive_core_user_id=700, interactive_core_employee_id=1700, **overrides):
    user = user or create_user(
        f"nurse-{interactive_core_user_id}@test.local",
        roles=["NURSE"],
    )
    defaults = {
        "user": user,
        "interactive_core_user_id": interactive_core_user_id,
        "interactive_core_employee_id": interactive_core_employee_id,
        "full_name": "Enfermera Prescript",
        "email": user.email,
        "status": "active",
        "country": get_country(overrides.pop("country", "HN")),
    }
    defaults.update(overrides)
    return NursePortalProfile.objects.create(**defaults)


def create_patient(doctor, first_name="Paciente", last_name="Prueba", **overrides):
    defaults = {
        "doctor": doctor,
        "first_name": first_name,
        "last_name": last_name,
    }
    defaults.update(overrides)
    return Patient.objects.create(**defaults)


def create_appointment(doctor, patient, scheduled_at, **overrides):
    defaults = {
        "doctor": doctor,
        "patient": patient,
        "scheduled_at": scheduled_at,
    }
    defaults.update(overrides)
    return Appointment.objects.create(**defaults)


def create_vitals(patient, appointment=None, **overrides):
    defaults = {
        "patient": patient,
        "appointment": appointment,
    }
    defaults.update(overrides)
    return PatientVitals.objects.create(**defaults)
