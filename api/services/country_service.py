from api.models import Country


COUNTRY_DEFAULTS = {
    "CR": {
        "name": "Costa Rica",
        "currency": "CRC",
        "phone_code": "+506",
        "dni_mask": "9-9999-9999",
        "phone_mask": "9999-9999",
        "timezone": "America/Costa_Rica",
    },
    "GT": {
        "name": "Guatemala",
        "currency": "GTQ",
        "phone_code": "+502",
        "dni_mask": "9999-99999-9999",
        "phone_mask": "9999-9999",
        "timezone": "America/Guatemala",
    },
    "HN": {
        "name": "Honduras",
        "currency": "HNL",
        "phone_code": "+504",
        "dni_mask": "9999-9999-99999",
        "phone_mask": "9999-9999",
        "timezone": "America/Tegucigalpa",
    },
    "SV": {
        "name": "El Salvador",
        "currency": "USD",
        "phone_code": "+503",
        "dni_mask": "",
        "phone_mask": "9999-9999",
        "timezone": "America/El_Salvador",
    },
}

COUNTRY_NAME_TO_CODE = {
    values["name"].casefold(): code for code, values in COUNTRY_DEFAULTS.items()
}


def normalize_country_code(value):
    if isinstance(value, Country):
        return value.code
    if isinstance(value, dict):
        value = value.get("code") or value.get("country_code") or value.get("name")
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    upper_value = normalized.upper()
    if upper_value in COUNTRY_DEFAULTS:
        return upper_value
    return COUNTRY_NAME_TO_CODE.get(normalized.casefold(), "")


def get_or_create_country(profile_data):
    country_value = profile_data.get("country")
    code = (
        profile_data.get("country_code")
        or (country_value.get("code") if isinstance(country_value, dict) else None)
        or normalize_country_code(country_value)
    )
    code = normalize_country_code(code)
    if not code:
        return None

    defaults = dict(COUNTRY_DEFAULTS.get(code, {}))
    if isinstance(country_value, dict):
        for field in ("name", "currency", "phone_code", "dni_mask", "phone_mask", "timezone"):
            if country_value.get(field) is not None:
                defaults[field] = country_value[field]
    elif country_value and not defaults.get("name"):
        defaults["name"] = str(country_value)

    defaults["name"] = profile_data.get("country_name") or defaults.get("name") or code
    interactive_core_id = profile_data.get("country_id")
    if interactive_core_id:
        defaults["interactive_core_id"] = interactive_core_id
    defaults["is_active"] = True
    country, _ = Country.objects.update_or_create(code=code, defaults=defaults)
    return country


def serialize_country(country):
    if not country:
        return None
    return {
        "id": country.id,
        "interactive_core_id": country.interactive_core_id,
        "code": country.code,
        "name": country.name,
        "currency": country.currency,
        "phone_code": country.phone_code,
        "dni_mask": country.dni_mask,
        "phone_mask": country.phone_mask,
        "timezone": country.timezone,
    }
