import random

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db.models import Q

NAMES = {
    "HN": (
        ["Carlos", "Marlon", "Wendy", "Karla", "Josue", "Delmy", "Oscar", "Suyapa"],
        ["Mejia", "Zelaya", "Cruz", "Flores", "Reyes", "Maradiaga", "Figueroa", "Banegas"],
    ),
    "GT": (
        ["Luis", "Andrea", "Edgar", "Mirna", "Byron", "Lucrecia", "Hugo", "Ingrid"],
        ["Morales", "Lopez", "Perez", "Giron", "Cifuentes", "Ajanel", "Barrios", "Orellana"],
    ),
}
DEFAULT_COUNTRY = "HN"


def user_country_code(user):
    access = user.prescript_country_accesses.filter(country__isnull=False).select_related("country").first()
    if access:
        return access.country.code
    for attribute in ("doctor_portal_profile", "secretary_portal_profile", "nurse_portal_profile"):
        profile = getattr(user, attribute, None)
        if profile and profile.country_id:
            return profile.country.code
    return DEFAULT_COUNTRY


class Command(BaseCommand):
    help = "Rellena con nombres de prueba (segun el pais del usuario) los usuarios sin nombre o apellido."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Guarda los cambios. Sin este flag solo muestra que haria.")

    def handle(self, *args, **options):
        rng = random.Random()
        users = get_user_model().objects.filter(
            Q(first_name="") | Q(last_name="")
        ).order_by("id")
        updated = 0
        for user in users:
            first_names, last_names = NAMES.get(user_country_code(user), NAMES[DEFAULT_COUNTRY])
            if not user.first_name:
                user.first_name = rng.choice(first_names)
            if not user.last_name:
                user.last_name = rng.choice(last_names)
            self.stdout.write(f"{user.username}: {user.first_name} {user.last_name}")
            if options["apply"]:
                user.save(update_fields=["first_name", "last_name"])
            updated += 1
        verb = "Actualizados" if options["apply"] else "Se actualizarian (usa --apply)"
        self.stdout.write(self.style.SUCCESS(f"{verb}: {updated}"))
