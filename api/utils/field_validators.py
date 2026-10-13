import re

from rest_framework import serializers


COUNTRY_FIELD_FORMATS = {
    "HN": {
        "dni_mask": "9999-9999-99999",
        "phone_mask": "9999-9999",
        "phone_code": "504",
    },
    "GT": {
        "dni_mask": "9999-99999-9999",
        "phone_mask": "9999-9999",
        "phone_code": "502",
    },
    "CR": {
        "dni_mask": "9-9999-9999",
        "phone_mask": "9999-9999",
        "phone_code": "506",
    },
    "SV": {
        "dni_mask": "",
        "phone_mask": "9999-9999",
        "phone_code": "503",
    },
}


def get_country_format(country):
    if country and hasattr(country, "code"):
        return {
            "dni_mask": getattr(country, "dni_mask", "") or "",
            "phone_mask": getattr(country, "phone_mask", "") or "",
            "phone_code": digits_only(getattr(country, "phone_code", "")),
        }
    country_code = str(country or "HN").strip().upper()
    return COUNTRY_FIELD_FORMATS.get(country_code, COUNTRY_FIELD_FORMATS["HN"])


def digits_only(value):
    return re.sub(r"\D", "", str(value or ""))


def count_mask_digits(mask):
    return len(re.findall(r"[9xX#]", mask or ""))


def apply_numeric_mask(value, mask):
    if not mask:
        return digits_only(value)

    digits = digits_only(value)
    result = []
    digit_index = 0

    for character in mask:
        if character in {"9", "#"} or character.lower() == "x":
            if digit_index >= len(digits):
                break
            result.append(digits[digit_index])
            digit_index += 1
        elif digit_index > 0 and digit_index < len(digits):
            result.append(character)

    return "".join(result)


def strip_phone_country_code(value, country):
    digits = digits_only(value)
    phone_code = get_country_format(country).get("phone_code", "")
    if phone_code and digits.startswith(phone_code):
        return digits[len(phone_code) :]
    return digits


def validate_and_format_dni(value, country="HN", required=False):
    if value in {None, ""}:
        if required:
            raise serializers.ValidationError("El DNI es requerido.")
        return None

    config = get_country_format(country)
    mask = config["dni_mask"]
    digits = digits_only(value)
    required_digits = count_mask_digits(mask)

    if required_digits and len(digits) != required_digits:
        raise serializers.ValidationError(f"El DNI debe seguir el formato {mask}.")
    if not required_digits and len(digits) < 6:
        raise serializers.ValidationError("Ingrese un DNI valido.")

    return apply_numeric_mask(digits, mask)


def validate_and_format_phone(value, country="HN", required=False):
    if value in {None, ""}:
        if required:
            raise serializers.ValidationError("El telefono es requerido.")
        return None

    config = get_country_format(country)
    mask = config["phone_mask"]
    digits = strip_phone_country_code(value, country)
    required_digits = count_mask_digits(mask)

    if len(digits) != required_digits:
        raise serializers.ValidationError(f"El telefono debe seguir el formato {mask}.")

    return apply_numeric_mask(digits, mask)
