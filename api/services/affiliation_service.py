import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMessage, send_mail
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers

from api.models import (
    AffiliationRequest,
    DoctorPortalProfile,
    NursePortalProfile,
    OneTimeCode,
    SecretaryPortalProfile,
)
from api.roles import PRESCRIPT_ROLE_DOCTOR, PRESCRIPT_ROLE_NURSE, PRESCRIPT_ROLE_SECRETARY
from api.services.access_activation_service import AccessActivationService
from api.services.country_service import get_or_create_country
from api.services.interactive_core import InteractiveCoreAccessService, InteractiveCoreDoctorService
from api.services.otp_service import OneTimeCodeService
from api.services.registration_service import record_terms_acceptance

logger = logging.getLogger(__name__)

MIN_QUERY_LENGTH = 3
UNAVAILABLE_MESSAGE = "No es posible afiliar esta ficha. Verifique sus datos o contacte a soporte."
EMAIL_REQUIRED_MESSAGE = (
    "Su ficha no tiene un correo registrado en Interactive Core. Indique su correo: "
    "lo verificaremos y un administrador revisara su solicitud."
)
ALREADY_LINKED_MESSAGE = "Esta ficha ya tiene una cuenta en Prescript. Inicie sesion o contacte a soporte."
EMAIL_IN_USE_MESSAGE = "Ya existe una cuenta con este correo."

MODE_VERIFIED = "verified"
MODE_MANUAL_REVIEW = "manual_review"

AFFILIATION_ROLES = (PRESCRIPT_ROLE_DOCTOR, PRESCRIPT_ROLE_SECRETARY, PRESCRIPT_ROLE_NURSE)
ROLE_LABELS = {
    PRESCRIPT_ROLE_DOCTOR: "Doctor",
    PRESCRIPT_ROLE_SECRETARY: "Secretaria",
    PRESCRIPT_ROLE_NURSE: "Enfermera",
}
# Lo que identifica a la persona en su ficha: colegiacion en doctores, documento en el resto.
IDENTIFIER_LABELS = {
    PRESCRIPT_ROLE_DOCTOR: "Colegiacion",
    PRESCRIPT_ROLE_SECRETARY: "Documento",
    PRESCRIPT_ROLE_NURSE: "Documento",
}


def mask_email(email):
    local, _, domain = str(email or "").partition("@")
    return f"{local[:1]}***@{domain}" if local and domain else ""


def mask_code(value):
    value = str(value or "")
    return f"***{value[-3:]}" if len(value) > 3 else ""


def affiliation_target(role, profile_id, email=None):
    # En revision manual el codigo queda atado a la ficha Y al correo, para que no sirva con otro.
    base = f"{role.lower()}:{profile_id}"
    return base if email is None else f"{base}:{email.lower()}"


def _clean(value):
    return str(value or "").strip()


# --- Diferencias entre roles: todas las fichas viven en Interactive Core pero con otra forma ---------


def _search_rows(role, query):
    if role == PRESCRIPT_ROLE_DOCTOR:
        rows = InteractiveCoreDoctorService().search_doctors(query)
        return [{**row, "identifier": row.get("colegiation_code")} for row in rows]
    access = InteractiveCoreAccessService()
    return access.search_secretaries(query) if role == PRESCRIPT_ROLE_SECRETARY else access.search_nurses(query)


def _fetch_record(role, profile_id):
    if role == PRESCRIPT_ROLE_DOCTOR:
        return InteractiveCoreDoctorService().get_doctor_for_activation(profile_id)
    access = InteractiveCoreAccessService()
    return access.get_secretary(profile_id) if role == PRESCRIPT_ROLE_SECRETARY else access.get_nurse(profile_id)


def _is_eligible(role, record):
    if not record:
        return False
    if role == PRESCRIPT_ROLE_DOCTOR:
        return record.get("status") == "active" and bool(record.get("has_doctor_role"))
    # Secretarias y enfermeras no tienen estado en Interactive Core: existir (y tener el rol) basta.
    return bool(record.get("has_prescript_access"))


def _identifier(role, record):
    return _clean(record.get("colegiation_code") if role == PRESCRIPT_ROLE_DOCTOR else record.get("dni"))


def _existing_profile_user_ids(role, interactive_core_id):
    """Usuarios que ya tienen el perfil de esa ficha de Interactive Core."""
    if role == PRESCRIPT_ROLE_DOCTOR:
        queryset = DoctorPortalProfile.objects.filter(interactive_core_doctor_id=interactive_core_id)
    elif role == PRESCRIPT_ROLE_SECRETARY:
        queryset = SecretaryPortalProfile.objects.filter(secretaria_interactivecore_id=interactive_core_id)
    else:
        queryset = NursePortalProfile.objects.filter(interactive_core_user_id=interactive_core_id)
    return list(queryset.values_list("user_id", flat=True))


def _link_profile(role, user, record, email, source):
    activation = AccessActivationService()
    if role == PRESCRIPT_ROLE_DOCTOR:
        activation.link_doctor(user, record, email, source=source)
    else:
        activation.link_portal_profile(user, role, record, email)


def _activate_verified(role, record, email, password):
    activation = AccessActivationService()
    if role == PRESCRIPT_ROLE_DOCTOR:
        return activation.activate_doctor(doctor_data=record, email=email, password=password)
    return activation.activate_portal_access(role, record, email, password)


class AffiliationService:
    """Afiliacion de personal de Interactive Core (doctor, secretaria o enfermera).

    Elegir una ficha de la lista no prueba que la persona sea esa. Por eso:
    - Si la ficha tiene correo, el codigo llega solo a ese correo y con el se crea la cuenta.
    - Si no lo tiene, la persona indica el suyo, verifica el codigo, y su cuenta queda inactiva
      hasta que un administrador apruebe el vinculo con la ficha.
    """

    def search(self, role, query):
        query = _clean(query)
        if len(query) < MIN_QUERY_LENGTH:
            return []
        # Solo datos minimos para distinguir homonimos: nunca correo, telefono ni documento completo.
        return [
            {
                "id": row["id"],
                "full_name": row["full_name"],
                "country_code": row.get("country_code"),
                "identifier_label": IDENTIFIER_LABELS[role],
                "identifier_hint": mask_code(row.get("identifier")),
                "has_email": row.get("has_email"),
            }
            for row in _search_rows(role, query)
        ]

    def get_eligible_record(self, role, profile_id):
        record = _fetch_record(role, profile_id)
        if not _is_eligible(role, record):
            raise serializers.ValidationError({"profile_id": UNAVAILABLE_MESSAGE})
        return record

    def _check_manual_review_allowed(self, role, record, email):
        if _existing_profile_user_ids(role, record["id"]):
            raise serializers.ValidationError({"profile_id": ALREADY_LINKED_MESSAGE})
        user_model = get_user_model()
        if (
            user_model.objects.filter(email__iexact=email).exists()
            or user_model.objects.filter(username__iexact=email).exists()
        ):
            raise serializers.ValidationError({"email": EMAIL_IN_USE_MESSAGE})

    def _resolve_mode(self, role, profile_id, email):
        """Devuelve (ficha, modo, correo al que se envia el codigo)."""
        record = self.get_eligible_record(role, profile_id)
        record_email = _clean(record.get("email"))
        if record_email:
            return record, MODE_VERIFIED, record_email
        email = _clean(email)
        if not email:
            raise serializers.ValidationError({"email": EMAIL_REQUIRED_MESSAGE, "requires_own_email": True})
        self._check_manual_review_allowed(role, record, email)
        return record, MODE_MANUAL_REVIEW, email

    def request_code(self, role, profile_id, email=None):
        record, mode, destination = self._resolve_mode(role, profile_id, email)
        target = affiliation_target(role, record["id"], destination if mode == MODE_MANUAL_REVIEW else None)
        OneTimeCodeService().issue(
            OneTimeCode.PURPOSE_IC_AFFILIATION,
            target,
            [destination],
            subject="Codigo para activar su cuenta en Prescript",
            body_template=(
                "Su codigo de verificacion es {code}. Vence en {minutes} minutos.\n"
                "Si usted no solicito activar una cuenta en Prescript, ignore este mensaje."
            ),
        )
        return {"mode": mode, "email_hint": mask_email(destination)}

    def activate(self, role, profile_id, code, password, terms, ip_address=None, email=None, phone=None):
        record, mode, destination = self._resolve_mode(role, profile_id, email)
        target = affiliation_target(role, record["id"], destination if mode == MODE_MANUAL_REVIEW else None)
        # La verificacion confirma el intento en su propia transaccion, antes de crear nada.
        OneTimeCodeService().verify(OneTimeCode.PURPOSE_IC_AFFILIATION, target, code)

        if mode == MODE_MANUAL_REVIEW:
            return self._submit_for_review(role, record, destination, password, terms, ip_address, phone)

        with transaction.atomic():
            payload = _activate_verified(role, record, destination, password)
            user = get_user_model().objects.get(username=destination.lower())
            record_terms_acceptance(user, terms, ip_address)
        return {**payload, "mode": MODE_VERIFIED}

    def _submit_for_review(self, role, record, email, password, terms, ip_address, phone):
        try:
            with transaction.atomic():
                user = get_user_model().objects.create_user(
                    username=email.lower(),
                    email=email,
                    password=password,
                    first_name=_clean(record.get("full_name"))[:150],
                    # Sin acceso hasta que un administrador apruebe el vinculo con la ficha.
                    is_active=False,
                )
                request = AffiliationRequest.objects.create(
                    user=user,
                    role=role,
                    interactive_core_id=record["id"],
                    full_name=_clean(record.get("full_name")),
                    identifier=_identifier(role, record) or None,
                    country=get_or_create_country(record),
                    email=email,
                    contact_phone=_clean(phone) or None,
                )
                record_terms_acceptance(user, terms, ip_address)
        except IntegrityError as exc:
            raise serializers.ValidationError({"email": EMAIL_IN_USE_MESSAGE}) from exc
        _notify_reviewers(request)
        return {"mode": MODE_MANUAL_REVIEW, "pending_review": True, "request_id": request.id}


def _reviewer_emails(country):
    """Administradores que pueden decidir: globales y, si hay pais, los de ese pais."""
    groups = ["ADMIN"]
    if country is not None:
        groups.append(f"ADMIN_{country.code}")
    users = (
        get_user_model()
        .objects.filter(is_active=True)
        .exclude(email="")
        .filter(Q(is_superuser=True) | Q(groups__name__in=groups))
        .distinct()
    )
    return sorted({user.email for user in users})


def _notify_reviewers(request):
    """Avisa a los administradores de una solicitud nueva; un fallo no debe afectar al solicitante."""
    recipients = _reviewer_emails(request.country)
    if not recipients:
        return
    lines = [
        "Hay una solicitud de afiliacion pendiente de revision.",
        "",
        f"{ROLE_LABELS[request.role]}: {request.full_name}",
        f"{IDENTIFIER_LABELS[request.role]}: {request.identifier or 'sin dato'}",
        f"Correo verificado: {request.email}",
        f"Telefono de contacto: {request.contact_phone or 'sin dato'}",
        "",
        "Revisela en Prescript, seccion Afiliaciones, y confirme la identidad antes de aprobar.",
    ]
    try:
        # Copia oculta: los administradores no deben ver las direcciones de los demas.
        EmailMessage(
            subject="Nueva solicitud de afiliacion en Prescript",
            body="\n".join(lines),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[settings.DEFAULT_FROM_EMAIL],
            bcc=recipients,
        ).send(fail_silently=False)
    except Exception:
        logger.warning("No se pudo avisar a los administradores de una solicitud de afiliacion.", exc_info=True)


def _notify_decision(request, approved):
    """Avisa al solicitante; un fallo del correo no debe deshacer la decision."""
    if approved:
        subject = "Su cuenta de Prescript fue aprobada"
        body = (
            f"Hola {request.full_name},\n\nSu solicitud de afiliacion fue aprobada. "
            "Ya puede iniciar sesion en Prescript con el correo y la contrasena que registro."
        )
    else:
        subject = "Su solicitud de afiliacion no fue aprobada"
        body = (
            f"Hola {request.full_name},\n\nNo pudimos validar su solicitud de afiliacion. "
            "Comuniquese con su administrador de Interactive Core si cree que es un error."
        )
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [request.email], fail_silently=False)
    except Exception:
        logger.warning("No se pudo enviar la notificacion de afiliacion.", exc_info=True)


class AffiliationReviewService:
    """Decision del administrador sobre una solicitud de afiliacion pendiente."""

    def approve(self, request_id, admin):
        with transaction.atomic():
            request = AffiliationRequest.objects.select_for_update().select_related("user").get(pk=request_id)
            if request.status != "pending":
                raise serializers.ValidationError({"detail": "La solicitud ya fue resuelta."})

            record = _fetch_record(request.role, request.interactive_core_id)
            if not _is_eligible(request.role, record):
                raise serializers.ValidationError({"detail": "La ficha ya no esta disponible en Interactive Core."})
            # Nunca reasignar una ficha que ya pertenece a otra cuenta.
            owners = _existing_profile_user_ids(request.role, request.interactive_core_id)
            if any(owner != request.user_id for owner in owners):
                raise serializers.ValidationError({"detail": "La ficha ya esta vinculada a otro usuario."})

            request.user.is_active = True
            request.user.save(update_fields=["is_active"])
            _link_profile(request.role, request.user, record, request.email, source="affiliation_review")
            self._decide(request, "approved", admin)

            # Solo una cuenta puede quedarse con la ficha: las demas solicitudes se rechazan.
            competing = list(
                AffiliationRequest.objects.select_for_update()
                .filter(role=request.role, interactive_core_id=request.interactive_core_id, status="pending")
                .exclude(pk=request.pk)
            )
            for other in competing:
                self._decide(other, "rejected", admin)

        _notify_decision(request, approved=True)
        for other in competing:
            _notify_decision(other, approved=False)
        return request

    def reject(self, request_id, admin):
        with transaction.atomic():
            request = AffiliationRequest.objects.select_for_update().get(pk=request_id)
            if request.status != "pending":
                raise serializers.ValidationError({"detail": "La solicitud ya fue resuelta."})
            self._decide(request, "rejected", admin)
        _notify_decision(request, approved=False)
        return request

    @staticmethod
    def _decide(request, status, admin):
        request.status = status
        request.decided_by = admin
        request.decided_at = timezone.now()
        request.save(update_fields=["status", "decided_by", "decided_at"])
