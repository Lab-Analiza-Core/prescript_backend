from django.contrib.auth.models import Group
from django.utils.crypto import get_random_string

from api.models import Country, UserCountryAccess
from api.roles import PRESCRIPT_ROLE_ADMIN


def sync_user_roles(user, roles, country=None):
    groups = []
    for role in roles:
        group_name = f"ADMIN_{country.code}" if role == PRESCRIPT_ROLE_ADMIN and country else role
        group, _ = Group.objects.get_or_create(name=group_name)
        groups.append(group)
    user.groups.set(groups)
    UserCountryAccess.objects.filter(user=user).delete()
    UserCountryAccess.objects.bulk_create(
        [
            UserCountryAccess(
                user=user,
                role_code=role,
                country=None if role == PRESCRIPT_ROLE_ADMIN and country is None else country,
            )
            for role in roles
        ]
    )


def create_admin_user(user_model, validated_data):
    roles = validated_data.pop("roles", [])
    country_code = validated_data.pop("country_code", "")
    password = validated_data.pop("password")
    user = user_model(**validated_data)
    user.set_password(password)
    user.save()
    country = Country.objects.filter(code=country_code).first() if country_code else None
    sync_user_roles(user, roles, country)
    return user


def update_admin_user(user, validated_data):
    roles = validated_data.pop("roles", None)
    country_code = validated_data.pop("country_code", None)
    password = validated_data.pop("password", "")
    for field, value in validated_data.items():
        setattr(user, field, value)
    if password:
        user.set_password(password)
    user.save()
    if roles is not None:
        if country_code is None:
            existing_access = user.prescript_country_accesses.filter(country__isnull=False).select_related("country").first()
            country = existing_access.country if existing_access else None
        else:
            country = Country.objects.filter(code=country_code).first() if country_code else None
        sync_user_roles(user, roles, country)
    return user


def generate_temporary_password():
    return f"Prescript-{get_random_string(12)}1!"


def reset_user_password(user, password):
    user.set_password(password)
    user.save(update_fields=["password"])
    return password
