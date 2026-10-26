import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from rest_framework import serializers

from api.models import OneTimeCode

CODE_TTL = timedelta(minutes=10)
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_ATTEMPTS = 5
# Tope de intentos fallidos acumulados por destinatario: pedir codigos nuevos no reinicia el conteo.
MAX_HOURLY_ATTEMPTS = 15

INVALID_CODE_MESSAGE = "El codigo es incorrecto o ya vencio."


def _hash_code(purpose, target, code):
    return salted_hmac("prescript.otp", f"{purpose}:{target}:{code}", secret=settings.SECRET_KEY).hexdigest()


class OneTimeCodeService:
    """Codigos de un solo uso enviados por correo. Solo se guarda el hash."""

    def issue(self, purpose, target, emails, subject, body_template):
        target = str(target)
        now = timezone.now()
        attempts_last_hour = OneTimeCode.objects.filter(
            purpose=purpose, target=target, created_at__gt=now - timedelta(hours=1)
        ).aggregate(total=Sum("attempts"))["total"] or 0
        if attempts_last_hour >= MAX_HOURLY_ATTEMPTS:
            raise serializers.ValidationError({"detail": "Demasiados intentos. Intente de nuevo mas tarde."})
        recent = OneTimeCode.objects.filter(
            purpose=purpose,
            target=target,
            consumed_at__isnull=True,
            created_at__gt=now - RESEND_COOLDOWN,
        ).exists()
        if recent:
            raise serializers.ValidationError({"detail": "Espere un minuto antes de solicitar otro codigo."})

        code = f"{secrets.randbelow(1_000_000):06d}"
        otp = OneTimeCode.objects.create(
            purpose=purpose,
            target=target,
            code_hash=_hash_code(purpose, target, code),
            expires_at=now + CODE_TTL,
        )
        minutes = int(CODE_TTL.total_seconds() // 60)
        try:
            for email in emails:
                send_mail(
                    subject,
                    body_template.format(code=code, minutes=minutes),
                    settings.DEFAULT_FROM_EMAIL,
                    [email],
                    fail_silently=False,
                )
        except Exception:
            # Un fallo de SMTP no debe consumir el codigo anterior ni iniciar el cooldown.
            otp.delete()
            raise
        OneTimeCode.objects.filter(
            purpose=purpose,
            target=target,
            consumed_at__isnull=True,
        ).exclude(pk=otp.pk).update(consumed_at=now)

    def verify(self, purpose, target, code):
        """Valida el codigo. El intento se confirma en la BD antes de lanzar el error,
        para que un rollback del llamador no reinicie el limite de intentos."""
        target = str(target)
        now = timezone.now()
        with transaction.atomic():
            otp = (
                OneTimeCode.objects.select_for_update()
                .filter(purpose=purpose, target=target, consumed_at__isnull=True, expires_at__gt=now)
                .first()
            )
            valid = False
            if otp is not None and otp.attempts < MAX_ATTEMPTS:
                otp.attempts += 1
                valid = constant_time_compare(otp.code_hash, _hash_code(purpose, target, str(code).strip()))
                if valid:
                    otp.consumed_at = now
                otp.save(update_fields=["attempts", "consumed_at"])
        if not valid:
            raise serializers.ValidationError({"code": INVALID_CODE_MESSAGE})
