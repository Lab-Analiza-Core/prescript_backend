from dataclasses import dataclass

from rest_framework.exceptions import PermissionDenied

from api.models import Country, UserCountryAccess
from api.roles import (
    COUNTRY_ADMIN_ROLE_PREFIX,
    PRESCRIPT_ROLE_ADMIN,
    get_primary_prescript_role,
)
from api.services.country_service import normalize_country_code, serialize_country


COUNTRY_HEADER = "HTTP_X_PRESCRIPT_COUNTRY"
NO_COUNTRY_ERROR = "Tu usuario no tiene un pais asignado. Contacta al administrador."


def _profile_country(user):
    for attribute in (
        "doctor_portal_profile",
        "secretary_portal_profile",
        "nurse_portal_profile",
        "org_admin_profile",
        "patient_portal_profile",
    ):
        profile = getattr(user, attribute, None)
        if profile and profile.country_id:
            return profile.country
    return None


def _group_names(user):
    return list(user.groups.values_list("name", flat=True))


def is_global_admin_user(user):
    if user.is_superuser:
        return True
    # El grupo local ADMIN no es una fuente de autoridad. Puede asignarse desde
    # Django Admin o desde el modulo local de usuarios y, por si solo, no debe
    # abrir el alcance clinico global. Los accesos globales confiables son los
    # sincronizados desde Interactive Core.
    return UserCountryAccess.objects.filter(
        user=user,
        role_code=PRESCRIPT_ROLE_ADMIN,
        country__isnull=True,
        is_active=True,
        source="interactive_core",
    ).exists()


def _allowed_countries(user):
    country_ids = set(
        UserCountryAccess.objects.filter(user=user, is_active=True, country__isnull=False)
        .values_list("country_id", flat=True)
    )
    group_names = _group_names(user)
    group_country_codes = [
        name.upper().removeprefix(COUNTRY_ADMIN_ROLE_PREFIX)
        for name in group_names
        if name.upper().startswith(COUNTRY_ADMIN_ROLE_PREFIX)
    ]
    if group_country_codes:
        country_ids.update(
            Country.objects.filter(code__in=group_country_codes, is_active=True).values_list("id", flat=True)
        )
    profile_country = _profile_country(user)
    if profile_country:
        country_ids.add(profile_country.id)
    return Country.objects.filter(id__in=country_ids, is_active=True).order_by("name")


def get_allowed_country_ids(user):
    """Paises activos a los que tiene acceso un administrador por pais."""
    return list(_allowed_countries(user).values_list("id", flat=True))


@dataclass(frozen=True)
class CountryScope:
    unrestricted: bool = False
    country: Country | None = None
    error: str | None = None

    @property
    def country_id(self):
        return self.country.id if self.country else None

    @property
    def is_valid(self):
        return self.error is None and (self.unrestricted or self.country is not None)

    def allows(self, country_id):
        if self.unrestricted:
            return True
        return bool(self.country_id and country_id and int(self.country_id) == int(country_id))

    def filter(self, queryset, field="country_id"):
        if self.unrestricted:
            return queryset
        if not self.is_valid:
            return queryset.none()
        return queryset.filter(**{field: self.country_id})

    def require_valid(self):
        if not self.is_valid:
            raise PermissionDenied(self.error or NO_COUNTRY_ERROR)
        return self


def get_country_scope_for_user(user, requested_country_code=""):
    requested_code = normalize_country_code(requested_country_code)
    global_admin = is_global_admin_user(user)

    if global_admin:
        if requested_country_code and not requested_code:
            return CountryScope(error="El pais seleccionado no es valido.")
        if requested_code:
            country = Country.objects.filter(code=requested_code, is_active=True).first()
            if not country:
                return CountryScope(error="El pais seleccionado no esta activo.")
            return CountryScope(country=country)
        return CountryScope(unrestricted=True)

    allowed = list(_allowed_countries(user))
    if requested_country_code:
        country = next((item for item in allowed if item.code == requested_code), None)
        if not country:
            return CountryScope(error="No tienes acceso al pais seleccionado.")
        return CountryScope(country=country)
    if len(allowed) == 1:
        return CountryScope(country=allowed[0])
    if len(allowed) > 1:
        return CountryScope(error="Selecciona uno de tus paises para continuar.")
    return CountryScope(error=NO_COUNTRY_ERROR)


def get_country_scope(request):
    cached = getattr(request, "_prescript_country_scope", None)
    if cached is not None:
        return cached
    scope = get_country_scope_for_user(
        request.user,
        request.META.get(COUNTRY_HEADER, ""),
    )
    request._prescript_country_scope = scope
    return scope


def get_country_context(user, requested_country_code=""):
    global_admin = is_global_admin_user(user)
    countries = Country.objects.filter(is_active=True).order_by("name") if global_admin else _allowed_countries(user)
    scope = get_country_scope_for_user(user, requested_country_code)
    return {
        "available_countries": [serialize_country(country) for country in countries],
        "selected_country": serialize_country(scope.country),
        "is_global_admin": global_admin,
        "is_unrestricted": scope.unrestricted,
        "requires_country_selection": not scope.is_valid and countries.exists(),
    }


def get_effective_role(user):
    return get_primary_prescript_role(_group_names(user))
