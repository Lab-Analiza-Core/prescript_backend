from django.contrib.auth.models import Group
from django.utils.crypto import get_random_string


def sync_user_roles(user, roles):
    groups = []
    for role in roles:
        group, _ = Group.objects.get_or_create(name=role)
        groups.append(group)
    user.groups.set(groups)


def create_admin_user(user_model, validated_data):
    roles = validated_data.pop("roles", [])
    password = validated_data.pop("password")
    user = user_model(**validated_data)
    user.set_password(password)
    user.save()
    sync_user_roles(user, roles)
    return user


def update_admin_user(user, validated_data):
    roles = validated_data.pop("roles", None)
    password = validated_data.pop("password", "")
    for field, value in validated_data.items():
        setattr(user, field, value)
    if password:
        user.set_password(password)
    user.save()
    if roles is not None:
        sync_user_roles(user, roles)
    return user


def generate_temporary_password():
    return f"Prescript-{get_random_string(12)}1!"


def reset_user_password(user, password):
    user.set_password(password)
    user.save(update_fields=["password"])
    return password
