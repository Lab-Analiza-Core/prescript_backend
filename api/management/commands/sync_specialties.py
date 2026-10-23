from django.core.management.base import BaseCommand, CommandError

from api.services.specialty_sync_service import SpecialtySyncService


class Command(BaseCommand):
    help = "Sincroniza el catalogo de especialidades (area medica) desde Interactive Core."

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep-missing",
            action="store_true",
            help="No desactivar las especialidades que ya no vienen en Interactive Core.",
        )

    def handle(self, *args, **options):
        try:
            result = SpecialtySyncService().sync(deactivate_missing=not options["keep_missing"])
        except Exception as exc:
            raise CommandError(f"No se pudo sincronizar con Interactive Core: {exc}") from exc
        self.stdout.write(
            self.style.SUCCESS(
                "Especialidades sincronizadas: "
                f"{result['created']} nuevas, {result['updated']} actualizadas, "
                f"{result['deactivated']} desactivadas."
            )
        )
