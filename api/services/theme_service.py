import base64
import re

from rest_framework.exceptions import ValidationError

from api.models import Organization, ThemeSetting
from api.services.country_scope import get_allowed_country_ids, is_global_admin_user

HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
MIN_CONTRAST = 4.5

# (token, etiqueta, grupo, valor de fabrica). Los valores de fabrica replican index.css del frontend.
TOKEN_DEFINITIONS = (
    ("primary", "Color principal", "brand", "#0F6B64"),
    ("primary_hover", "Principal al pasar el raton", "brand", "#093F43"),
    ("accent", "Color de acento", "brand", "#365C9D"),
    ("background", "Fondo de la aplicacion", "surface", "#EDF2EE"),
    ("surface", "Tarjetas y paneles", "surface", "#FFFEFA"),
    ("text", "Texto principal", "surface", "#14242A"),
    ("text_secondary", "Texto secundario", "surface", "#4F5D59"),
    ("border", "Bordes", "surface", "#CBD8D2"),
    ("sidebar_bg", "Fondo del menu", "sidebar", "#132B2E"),
    ("sidebar_text", "Texto del menu", "sidebar", "#EDF7F3"),
    ("sidebar_active_bg", "Opcion activa del menu", "sidebar", "#F4FAF7"),
    ("sidebar_active_text", "Texto de la opcion activa", "sidebar", "#093F43"),
    ("button_primary_bg", "Boton principal", "buttons", "#0F6B64"),
    ("button_primary_text", "Texto del boton principal", "buttons", "#FFFFFF"),
    ("button_secondary_bg", "Boton secundario", "buttons", "#FFFEFA"),
    ("button_secondary_text", "Texto del boton secundario", "buttons", "#14242A"),
    ("button_danger_bg", "Boton de peligro", "buttons", "#A7352B"),
    ("button_danger_text", "Texto del boton de peligro", "buttons", "#FFFFFF"),
    ("success", "Exito", "states", "#166534"),
    ("warning", "Advertencia", "states", "#7A4F12"),
    ("error", "Error", "states", "#A7352B"),
)
TOKENS = tuple(token for token, *_ in TOKEN_DEFINITIONS)
DEFAULT_COLORS = {token: default for token, _, _, default in TOKEN_DEFINITIONS}

# (texto, fondo): cada par debe cumplir el contraste minimo.
CONTRAST_PAIRS = (
    ("text", "background"),
    ("text", "surface"),
    ("text_secondary", "background"),
    ("text_secondary", "surface"),
    ("primary", "surface"),
    ("sidebar_text", "sidebar_bg"),
    ("sidebar_active_text", "sidebar_active_bg"),
    ("button_primary_text", "button_primary_bg"),
    ("button_primary_text", "primary_hover"),
    ("button_secondary_text", "button_secondary_bg"),
    ("button_danger_text", "button_danger_bg"),
    ("success", "surface"),
    ("warning", "surface"),
    ("error", "surface"),
)

FONT_CHOICES = {
    "system": "Sistema (Aptos / Segoe UI)",
    "inter": "Inter",
    "plus-jakarta-sans": "Plus Jakarta Sans",
    "poppins": "Poppins",
    "lato": "Lato",
    "merriweather": "Merriweather",
}

MAX_LOGO_BYTES = 512 * 1024
LOGO_SIGNATURES = (
    ("image/png", lambda raw: raw.startswith(b"\x89PNG\r\n\x1a\n")),
    ("image/jpeg", lambda raw: raw.startswith(b"\xff\xd8\xff")),
    ("image/webp", lambda raw: raw[:4] == b"RIFF" and raw[8:12] == b"WEBP"),
)
UNSAFE_SVG = re.compile(r"<\s*(script|foreignObject|iframe|object|embed)|\son\w+\s*=|javascript:|data:text/html", re.I)

PROFILE_ATTRIBUTES = (
    "org_admin_profile",
    "doctor_portal_profile",
    "secretary_portal_profile",
    "nurse_portal_profile",
    "patient_portal_profile",
)


def normalize_hex(value):
    if not isinstance(value, str) or not HEX_COLOR.match(value.strip()):
        return None
    value = value.strip().lstrip("#").upper()
    if len(value) == 3:
        value = "".join(char * 2 for char in value)
    return f"#{value}"


def _channel(value):
    value /= 255
    return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4


def _luminance(color):
    red, green, blue = (int(color[index:index + 2], 16) for index in (1, 3, 5))
    return 0.2126 * _channel(red) + 0.7152 * _channel(green) + 0.0722 * _channel(blue)


def contrast_ratio(foreground, background):
    lighter, darker = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def validate_colors(raw_colors, inherited):
    """Normaliza los colores propios y valida el contraste sobre el resultado final (herencia incluida)."""
    if not isinstance(raw_colors, dict):
        raise ValidationError({"colors": "Envie un objeto con los colores."})
    errors, colors = {}, {}
    for token, value in raw_colors.items():
        if token not in TOKENS:
            errors[token] = "Color desconocido."
            continue
        normalized = normalize_hex(value)
        if normalized is None:
            errors[token] = "Use un color hexadecimal como #0F6B64."
        else:
            colors[token] = normalized
    if errors:
        raise ValidationError({"colors": errors})

    merged = {**inherited, **colors}
    for foreground, background in CONTRAST_PAIRS:
        ratio = contrast_ratio(merged[foreground], merged[background])
        if ratio < MIN_CONTRAST:
            errors[foreground] = f"Contraste {ratio:.1f}:1 contra '{background}'; el minimo es {MIN_CONTRAST}:1."
    if errors:
        raise ValidationError({"colors": errors})
    return colors


def validate_font(value):
    value = (value or "").strip()
    if value and value not in FONT_CHOICES:
        raise ValidationError({"font": "Fuente no disponible."})
    return value


def build_logo_data_url(uploaded):
    raw = uploaded.read(MAX_LOGO_BYTES + 1)
    if not raw:
        raise ValidationError({"logo": "El archivo esta vacio."})
    if len(raw) > MAX_LOGO_BYTES:
        raise ValidationError({"logo": f"El logo no puede superar {MAX_LOGO_BYTES // 1024} KB."})
    content_type = next((kind for kind, matches in LOGO_SIGNATURES if matches(raw)), None)
    if content_type is None and b"<svg" in raw[:2048].lower():
        try:
            decoded = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise ValidationError({"logo": "El SVG debe estar codificado en UTF-8."})
        if UNSAFE_SVG.search(decoded):
            raise ValidationError({"logo": "El SVG contiene elementos no permitidos."})
        content_type = "image/svg+xml"
    if content_type is None:
        raise ValidationError({"logo": "Formato no permitido. Use PNG, JPEG, WebP o SVG."})
    return f"data:{content_type};base64,{base64.b64encode(raw).decode('ascii')}"


def get_global_row():
    return ThemeSetting.objects.filter(organization__isnull=True).first()


def inherited_colors(organization):
    """Colores que se veran si el ambito no define los suyos (fabrica, mas el global para organizaciones)."""
    colors = dict(DEFAULT_COLORS)
    if organization is not None:
        row = get_global_row()
        if row:
            colors.update(row.colors)
    return colors


def _payload(row, organization, parent_row):
    own_colors = row.colors if row else {}
    return {
        "scope": "organization" if organization else "global",
        "organization": {"id": organization.id, "name": organization.name} if organization else None,
        "customized": bool(row and not row.is_empty),
        "own": {"colors": own_colors, "font": row.font if row else "", "has_logo": bool(row and row.logo)},
        "inherited": inherited_colors(organization),
        "colors": {**inherited_colors(organization), **own_colors},
        "font": (row.font if row else "") or (parent_row.font if parent_row else ""),
        "logo": (row.logo if row else "") or (parent_row.logo if parent_row else "") or None,
        "updated_at": row.updated_at if row else None,
        "updated_by": (row.updated_by.email or row.updated_by.get_username()) if row and row.updated_by else None,
    }


def serialize_theme(organization=None):
    """Tema editable de un ambito, con lo heredado ya resuelto."""
    if organization is None:
        return _payload(get_global_row(), None, None)
    row = ThemeSetting.objects.filter(organization=organization).select_related("updated_by").first()
    return _payload(row, organization, get_global_row())


def get_row_for_update(organization, user):
    row = ThemeSetting.objects.filter(organization=organization).first() or ThemeSetting(organization=organization)
    row.updated_by = user
    return row


def reset_theme(organization):
    ThemeSetting.objects.filter(organization=organization).delete()


def save_row(row):
    """Una fila sin personalizacion se elimina: el ambito vuelve a heredar."""
    if row.is_empty:
        if row.pk:
            row.delete()
    else:
        row.save()


def user_organization(user):
    """Organizacion externa activa del usuario; administradores globales y personal de Interactive Core usan el global."""
    if is_global_admin_user(user):
        return None
    for attribute in PROFILE_ATTRIBUTES:
        profile = getattr(user, attribute, None)
        organization = getattr(profile, "organization", None) if profile else None
        if organization is not None and not organization.is_interactive_core and organization.status == "active":
            return organization
    return None


def resolve_effective_theme(user):
    """Tema que ve un usuario: el de su organizacion o, si no hay, el global o el de fabrica."""
    payload = serialize_theme(user_organization(user))
    global_row = get_global_row()
    if payload["customized"] and payload["scope"] == "organization":
        source = "organization"
    elif global_row and not global_row.is_empty:
        source = "global"
    else:
        source = "system"
    return {"source": source, "colors": payload["colors"], "font": payload["font"], "logo": payload["logo"]}


def manageable_theme_organizations(user):
    """Organizaciones cuyo tema puede editar el usuario, ordenadas por pais y nombre."""
    queryset = Organization.objects.select_related("country", "theme")
    if not is_global_admin_user(user):
        org_admin = getattr(user, "org_admin_profile", None)
        if org_admin and org_admin.status == "active":
            if org_admin.organization.status != "active":
                return queryset.none()
            queryset = queryset.filter(id=org_admin.organization_id)
        else:
            queryset = queryset.filter(country_id__in=get_allowed_country_ids(user))
    return queryset.order_by("country__name", "name")


def options_payload():
    return {
        "tokens": [
            {"key": token, "label": label, "group": group, "default": default}
            for token, label, group, default in TOKEN_DEFINITIONS
        ],
        "contrast_pairs": [{"text": text, "background": background} for text, background in CONTRAST_PAIRS],
        "min_contrast": MIN_CONTRAST,
        "fonts": [{"key": key, "label": label} for key, label in FONT_CHOICES.items()],
        "max_logo_bytes": MAX_LOGO_BYTES,
    }
