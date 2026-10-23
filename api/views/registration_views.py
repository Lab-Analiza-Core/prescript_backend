from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from api.models import Appointment, OneTimeCode, Prescription
from api.serializers.registration_serializers import (
    ExternalRegistrationSerializer,
    InvitationValidationSerializer,
    PatientHistoryVerifySerializer,
    find_patient_records,
)
from api.services.doctor_display import format_doctor_display_name
from api.services.otp_service import OneTimeCodeService
from api.services.registration_service import ExternalRegistrationService


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (forwarded.split(",")[0].strip() or request.META.get("REMOTE_ADDR")) or None


class InvitationValidationView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "invitation_validate"

    def post(self, request):
        serializer = InvitationValidationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.to_representation(serializer.validated_data))


class ExternalRegistrationView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "register"

    def post(self, request):
        serializer = ExternalRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = ExternalRegistrationService().register(serializer.validated_data, ip_address=_client_ip(request))
        return Response(payload, status=status.HTTP_201_CREATED)


def _patient_profile(user):
    profile = getattr(user, "patient_portal_profile", None)
    if profile is None:
        raise PermissionDenied("Solo las cuentas de paciente pueden vincular historial.")
    return profile


class PatientHistoryRequestView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "otp"

    def post(self, request):
        profile = _patient_profile(request.user)
        # Solo se envia a los correos que ya constan en la ficha clinica, nunca al de la cuenta nueva.
        emails = sorted(
            {record.email.strip().lower() for record in find_patient_records(profile) if (record.email or "").strip()}
        )
        if emails:
            OneTimeCodeService().issue(
                OneTimeCode.PURPOSE_PATIENT_HISTORY,
                request.user.id,
                emails,
                subject="Codigo para vincular su historial en Prescript",
                body_template=(
                    "Su codigo de verificacion es {code}. Vence en {minutes} minutos.\n"
                    "Si no lo solicito, ignore este mensaje."
                ),
            )
        # Misma respuesta exista o no historial, para no revelar si un documento esta registrado.
        return Response(
            {"detail": "Si existe historial asociado a su documento, enviamos un codigo al correo registrado en la ficha."}
        )


class PatientHistoryVerifyView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "otp"

    def post(self, request):
        profile = _patient_profile(request.user)
        serializer = PatientHistoryVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        OneTimeCodeService().verify(
            OneTimeCode.PURPOSE_PATIENT_HISTORY, request.user.id, serializer.validated_data["code"]
        )
        profile.history_verified_at = timezone.now()
        profile.save(update_fields=["history_verified_at", "updated_at"])
        return Response({"verified": True, "records": find_patient_records(profile).count()})


class PatientHistoryView(APIView):
    """Historial propio del paciente, solo despues de verificar su documento por OTP.

    Lista blanca de campos: no se exponen notas comerciales ni datos internos del doctor.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = _patient_profile(request.user)
        if profile.history_verified_at is None:
            raise PermissionDenied("Verifique su documento para ver su historial.")

        records = list(find_patient_records(profile).select_related("doctor__organization"))
        patient_ids = [record.id for record in records]
        appointments = (
            Appointment.objects.filter(patient_id__in=patient_ids).select_related("doctor").order_by("-scheduled_at")
        )
        prescriptions = (
            Prescription.objects.filter(patient_id__in=patient_ids)
            .select_related("doctor")
            .prefetch_related("items__medicine")
            .order_by("-created_at")
        )
        return Response(
            {
                "records": [
                    {
                        "id": record.id,
                        "first_name": record.first_name,
                        "last_name": record.last_name,
                        "doctor_name": format_doctor_display_name(record.doctor.full_name, record.doctor.sex),
                        "organization": record.doctor.organization.name if record.doctor.organization else None,
                    }
                    for record in records
                ],
                "appointments": [
                    {
                        "id": appointment.id,
                        "scheduled_at": appointment.scheduled_at,
                        "reason": appointment.reason,
                        "status": appointment.status,
                        "doctor_name": format_doctor_display_name(appointment.doctor.full_name, appointment.doctor.sex),
                    }
                    for appointment in appointments
                ],
                "prescriptions": [
                    {
                        "id": prescription.id,
                        "created_at": prescription.created_at,
                        "diagnosis": prescription.diagnosis,
                        "doctor_name": format_doctor_display_name(prescription.doctor.full_name, prescription.doctor.sex),
                        "items": [
                            {
                                "medicine": item.medicine.name,
                                "dosage": item.dosage,
                                "frequency": item.frequency,
                                "duration": item.duration,
                                "instructions": item.instructions,
                            }
                            for item in prescription.items.all()
                        ],
                    }
                    for prescription in prescriptions
                ],
            }
        )
