DOCTOR_TITLE_BY_SEX = {
    "F": "Dra.",
    "M": "Dr.",
}


def normalize_sex(value):
    normalized = str(value or "").strip().upper()
    if normalized in {"F", "FEMALE", "FEMENINO", "MUJER"}:
        return "F"
    if normalized in {"M", "MALE", "MASCULINO", "HOMBRE"}:
        return "M"
    if normalized in {"O", "OTHER", "OTRO"}:
        return "O"
    return None


def get_doctor_title(sex):
    return DOCTOR_TITLE_BY_SEX.get(normalize_sex(sex), "Dr.")


def format_doctor_display_name(full_name, sex=None):
    name = str(full_name or "").strip()
    if not name:
        return ""

    normalized_name = name.lower()
    if normalized_name.startswith(("dr. ", "dra. ", "doctor ", "doctora ")):
        return name

    return f"{get_doctor_title(sex)} {name}"


def get_doctor_sex_from_profile_data(profile_data):
    for key in ("sex", "gender", "genero", "sexo"):
        sex = normalize_sex(profile_data.get(key))
        if sex:
            return sex
    return None
