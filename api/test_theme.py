import base64
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from api.models import Country, Organization, OrganizationAdminProfile, PatientPortalProfile, ThemeSetting
from api.services import theme_service
from api.test_factories import create_doctor, create_user

ADMIN_PERMISSION = "api.permissions.admin_permissions.user_is_interactive_core_admin"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
DARK = {"sidebar_bg": "#000000"}


def is_admin_group(user):
    return user.groups.filter(name__in=["ADMIN", "ADMIN_HN", "ADMIN_GT"]).exists()


class ThemeBase(TestCase):
    def setUp(self):
        patcher = mock.patch(ADMIN_PERMISSION, side_effect=is_admin_group)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = APIClient(HTTP_HOST="localhost")
        self.hn = Country.objects.get(code="HN")
        self.gt = Country.objects.get(code="GT")
        self.org_hn_b = Organization.objects.create(name="Beta HN", country=self.hn)
        self.org_hn_a = Organization.objects.create(name="Alfa HN", country=self.hn)
        self.org_gt = Organization.objects.create(name="Clinica GT", country=self.gt)
        self.root = create_user("root@test.local", roles=["ADMIN"])
        self.admin_hn = create_user("admin-hn@test.local", roles=["ADMIN_HN"])
        self.org_admin = self.make_org_admin("org-admin@test.local", self.org_hn_a)

    def make_org_admin(self, username, organization, status_value="active"):
        user = create_user(username, roles=["ORG_ADMIN"])
        OrganizationAdminProfile.objects.create(
            user=user, organization=organization, full_name=username, email=username,
            country=organization.country, status=status_value,
        )
        return user

    def as_user(self, user):
        self.client.force_authenticate(user)
        return self.client

    def put_colors(self, user, url, colors, **extra):
        return self.as_user(user).put(url, {"colors": colors, **extra}, format="json")

    def org_url(self, organization, suffix=""):
        return f"/api/v1/admin/organizations/{organization.id}/theme{suffix}"


class ThemeServiceTests(TestCase):
    def test_factory_colors_meet_contrast(self):
        for foreground, background in theme_service.CONTRAST_PAIRS:
            ratio = theme_service.contrast_ratio(
                theme_service.DEFAULT_COLORS[foreground], theme_service.DEFAULT_COLORS[background]
            )
            self.assertGreaterEqual(ratio, theme_service.MIN_CONTRAST, f"{foreground}/{background}")

    def test_contrast_ratio_extremes(self):
        self.assertAlmostEqual(theme_service.contrast_ratio("#000000", "#FFFFFF"), 21.0, places=1)

    def test_short_hex_is_expanded_and_uppercased(self):
        self.assertEqual(theme_service.normalize_hex("#abc"), "#AABBCC")
        self.assertIsNone(theme_service.normalize_hex("rojo"))


class GlobalThemeTests(ThemeBase):
    def test_global_admin_sets_and_resets_global_theme(self):
        response = self.put_colors(self.root, "/api/v1/admin/theme", {"primary": "#063", "primary_hover": "#042"})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["colors"]["primary"], "#006633")
        self.assertTrue(response.data["customized"])

        response = self.as_user(self.root).delete("/api/v1/admin/theme")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["customized"])
        self.assertEqual(response.data["colors"]["primary"], theme_service.DEFAULT_COLORS["primary"])
        self.assertFalse(ThemeSetting.objects.exists())

    def test_only_global_admin_can_edit_global_theme(self):
        for user in (self.admin_hn, self.org_admin, create_user("doc@test.local", roles=["DOCTOR"])):
            response = self.put_colors(user, "/api/v1/admin/theme", DARK)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, user.email)
        self.assertEqual(self.as_user(self.admin_hn).get("/api/v1/admin/theme").status_code, 403)

    def test_global_row_is_unique(self):
        from django.db import IntegrityError, transaction

        ThemeSetting.objects.create(colors={"primary": "#000000"})
        with self.assertRaises(IntegrityError), transaction.atomic():
            ThemeSetting.objects.create(colors={"primary": "#111111"})

    def test_low_contrast_is_rejected_with_the_offending_token(self):
        response = self.put_colors(self.root, "/api/v1/admin/theme", {"text": "#EEEEEE"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("text", response.data["colors"])
        self.assertFalse(ThemeSetting.objects.exists())

    def test_invalid_input_is_rejected(self):
        client = self.as_user(self.root)
        self.assertEqual(client.put("/api/v1/admin/theme", {"colors": {"primary": "verde"}}, format="json").status_code, 400)
        self.assertEqual(client.put("/api/v1/admin/theme", {"colors": {"nope": "#000000"}}, format="json").status_code, 400)
        self.assertEqual(client.put("/api/v1/admin/theme", {"font": "comic-sans"}, format="json").status_code, 400)
        self.assertEqual(client.put("/api/v1/admin/theme", {}, format="json").status_code, 400)

    def test_font_can_be_set(self):
        response = self.as_user(self.root).put("/api/v1/admin/theme", {"font": "inter"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["font"], "inter")


class OrganizationThemeScopeTests(ThemeBase):
    def test_global_admin_edits_any_organization(self):
        for organization in (self.org_hn_a, self.org_gt):
            response = self.put_colors(self.root, self.org_url(organization), DARK)
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_org_admin_edits_only_own_organization(self):
        self.assertEqual(self.put_colors(self.org_admin, self.org_url(self.org_hn_a), DARK).status_code, 200)
        self.assertEqual(self.put_colors(self.org_admin, self.org_url(self.org_hn_b), DARK).status_code, 404)
        self.assertEqual(self.as_user(self.org_admin).get(self.org_url(self.org_gt)).status_code, 404)

    def test_pending_or_suspended_org_admin_cannot_edit(self):
        pending = self.make_org_admin("pending@test.local", self.org_hn_b, status_value="pending")
        self.assertEqual(self.put_colors(pending, self.org_url(self.org_hn_b), DARK).status_code, 403)
        self.org_hn_a.status = "suspended"
        self.org_hn_a.save()
        self.assertEqual(self.put_colors(self.org_admin, self.org_url(self.org_hn_a), DARK).status_code, 404)

    def test_country_admin_edits_organizations_of_their_country_only(self):
        self.assertEqual(self.put_colors(self.admin_hn, self.org_url(self.org_hn_b), DARK).status_code, 200)
        self.assertEqual(self.put_colors(self.admin_hn, self.org_url(self.org_gt), DARK).status_code, 404)

    def test_non_admin_roles_cannot_use_admin_endpoints(self):
        doctor = create_user("doc@test.local", roles=["DOCTOR"])
        self.assertEqual(self.put_colors(doctor, self.org_url(self.org_hn_a), DARK).status_code, 403)
        self.assertEqual(self.as_user(doctor).get("/api/v1/admin/theme/organizations").status_code, 403)

    def test_organization_list_is_scoped_and_ordered(self):
        names = lambda user: [  # noqa: E731
            (row["country"]["code"], row["name"])
            for row in self.as_user(user).get("/api/v1/admin/theme/organizations").data
        ]
        root_rows = names(self.root)
        self.assertEqual(root_rows, sorted(root_rows, key=lambda item: (self._country_name(item[0]), item[1])))
        self.assertIn(("GT", "Clinica GT"), root_rows)
        self.assertEqual(
            [name for code, name in names(self.admin_hn) if name.endswith("HN")], ["Alfa HN", "Beta HN"]
        )
        self.assertNotIn(("GT", "Clinica GT"), names(self.admin_hn))
        self.assertEqual(names(self.org_admin), [("HN", "Alfa HN")])

    def _country_name(self, code):
        return Country.objects.get(code=code).name

    def test_organization_list_flags_customized_and_filters_by_search(self):
        self.put_colors(self.root, self.org_url(self.org_hn_b), DARK)
        rows = self.as_user(self.root).get("/api/v1/admin/theme/organizations?search=hn").data
        flags = {row["name"]: row["customized"] for row in rows}
        self.assertEqual(flags, {"Alfa HN": False, "Beta HN": True})


class InheritanceTests(ThemeBase):
    def test_organization_inherits_global_and_overrides_on_top(self):
        self.put_colors(self.root, "/api/v1/admin/theme", {"primary": "#0A5522", "primary_hover": "#064418"})
        response = self.put_colors(self.org_admin, self.org_url(self.org_hn_a), {"accent": "#223388"})
        self.assertEqual(response.status_code, 200, response.data)
        colors = response.data["colors"]
        self.assertEqual(colors["primary"], "#0A5522")
        self.assertEqual(colors["accent"], "#223388")
        self.assertEqual(response.data["own"]["colors"], {"accent": "#223388"})
        self.assertEqual(response.data["inherited"]["primary"], "#0A5522")
        self.assertEqual(response.data["inherited"]["accent"], theme_service.DEFAULT_COLORS["accent"])

    def test_contrast_is_checked_against_inherited_values(self):
        dark_global = {
            "background": "#101010", "surface": "#101010", "text": "#FFFFFF", "text_secondary": "#CCCCCC",
            "primary": "#7FD8D0", "success": "#6FD08C", "warning": "#E0B050", "error": "#FF8A80",
        }
        self.assertEqual(self.put_colors(self.root, "/api/v1/admin/theme", dark_global).status_code, 200)
        # El org admin aclara el fondo: el texto blanco heredado deja de contrastar.
        response = self.put_colors(self.org_admin, self.org_url(self.org_hn_a), {"background": "#FFFFFF"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("text", response.data["colors"])

    def test_reset_organization_returns_to_global(self):
        self.put_colors(self.root, "/api/v1/admin/theme", {"primary": "#0A5522", "primary_hover": "#064418"})
        self.put_colors(self.org_admin, self.org_url(self.org_hn_a), {"primary": "#001122"})
        response = self.as_user(self.org_admin).delete(self.org_url(self.org_hn_a))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["customized"])
        self.assertEqual(response.data["colors"]["primary"], "#0A5522")

    def test_org_admin_cannot_reach_other_organization_reset(self):
        self.assertEqual(self.as_user(self.org_admin).delete(self.org_url(self.org_hn_b)).status_code, 404)


class EffectiveThemeTests(ThemeBase):
    def effective(self, user):
        response = self.as_user(user).get("/api/v1/theme")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data

    def test_requires_authentication(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/v1/theme").status_code, 401)

    def test_defaults_to_system_colors(self):
        data = self.effective(self.org_admin)
        self.assertEqual(data["source"], "system")
        self.assertEqual(data["colors"], theme_service.DEFAULT_COLORS)

    def test_member_sees_organization_theme_and_others_see_global(self):
        self.put_colors(self.root, "/api/v1/admin/theme", {"accent": "#223388"})
        self.put_colors(self.root, self.org_url(self.org_hn_a), {"primary": "#001122", "primary_hover": "#000000"})
        doctor = create_doctor(
            interactive_core_doctor_id=None, organization=self.org_hn_a, origin="self_registered",
            user=create_user("doc-a@test.local", roles=["DOCTOR"]),
        )
        member = self.effective(doctor.user)
        self.assertEqual(member["source"], "organization")
        self.assertEqual(member["colors"]["primary"], "#001122")
        self.assertEqual(member["colors"]["accent"], "#223388")

        other = create_doctor(
            interactive_core_doctor_id=None, organization=self.org_hn_b, origin="self_registered",
            user=create_user("doc-b@test.local", roles=["DOCTOR"]),
        )
        data = self.effective(other.user)
        self.assertEqual(data["source"], "global")
        self.assertEqual(data["colors"]["primary"], theme_service.DEFAULT_COLORS["primary"])

    def test_interactive_core_and_admin_users_use_global(self):
        self.put_colors(self.root, "/api/v1/admin/theme", {"accent": "#223388"})
        ic_org = Organization.objects.get(country=self.hn, is_interactive_core=True)
        self.put_colors(self.root, self.org_url(ic_org), {"accent": "#115599"})
        ic_doctor = create_doctor(interactive_core_doctor_id=9001, organization=ic_org)
        self.assertEqual(self.effective(ic_doctor.user)["colors"]["accent"], "#223388")
        self.assertEqual(self.effective(self.root)["colors"]["accent"], "#223388")

    def test_patient_sees_organization_theme(self):
        self.put_colors(self.root, self.org_url(self.org_hn_a), {"accent": "#223388"})
        user = create_user("patient@test.local", roles=["PATIENT"])
        PatientPortalProfile.objects.create(user=user, organization=self.org_hn_a, country=self.hn)
        self.assertEqual(self.effective(user)["colors"]["accent"], "#223388")

    def test_suspended_organization_falls_back_to_global(self):
        self.put_colors(self.root, self.org_url(self.org_hn_a), {"accent": "#223388"})
        self.org_hn_a.status = "suspended"
        self.org_hn_a.save()
        doctor = create_doctor(
            interactive_core_doctor_id=None, organization=self.org_hn_a, origin="self_registered",
            user=create_user("doc-a@test.local", roles=["DOCTOR"]),
        )
        self.assertEqual(self.effective(doctor.user)["source"], "system")


class LogoTests(ThemeBase):
    def upload(self, user, url, content, name="logo.png"):
        return self.as_user(user).post(url, {"logo": SimpleUploadedFile(name, content)}, format="multipart")

    def test_png_logo_is_stored_and_inherited_by_organizations(self):
        response = self.upload(self.root, "/api/v1/admin/theme/logo", PNG)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["logo"], "data:image/png;base64," + base64.b64encode(PNG).decode())
        org_view = self.as_user(self.org_admin).get(self.org_url(self.org_hn_a))
        self.assertEqual(org_view.data["logo"], response.data["logo"])
        self.assertFalse(org_view.data["own"]["has_logo"])

    def test_organization_logo_overrides_and_can_be_removed(self):
        self.upload(self.root, "/api/v1/admin/theme/logo", PNG)
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>'
        response = self.upload(self.org_admin, self.org_url(self.org_hn_a, "/logo"), svg, "logo.svg")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["logo"].startswith("data:image/svg+xml;base64,"))
        response = self.as_user(self.org_admin).delete(self.org_url(self.org_hn_a, "/logo"))
        self.assertTrue(response.data["logo"].startswith("data:image/png;base64,"))
        self.assertFalse(ThemeSetting.objects.filter(organization=self.org_hn_a).exists())

    def test_rejects_unsafe_oversized_or_unknown_files(self):
        url = "/api/v1/admin/theme/logo"
        evil = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        self.assertEqual(self.upload(self.root, url, evil, "x.svg").status_code, 400)
        handler = b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"></svg>'
        self.assertEqual(self.upload(self.root, url, handler, "x.svg").status_code, 400)
        self.assertEqual(self.upload(self.root, url, b"MZ not an image").status_code, 400)
        self.assertEqual(self.upload(self.root, url, PNG + b"\x00" * theme_service.MAX_LOGO_BYTES).status_code, 400)
        self.assertEqual(self.as_user(self.root).post(url, {}, format="multipart").status_code, 400)
        self.assertFalse(ThemeSetting.objects.exists())

    def test_logo_permissions_follow_theme_scope(self):
        self.assertEqual(self.upload(self.org_admin, "/api/v1/admin/theme/logo", PNG).status_code, 403)
        self.assertEqual(self.upload(self.org_admin, self.org_url(self.org_hn_b, "/logo"), PNG).status_code, 404)
        self.assertEqual(self.upload(self.admin_hn, self.org_url(self.org_gt, "/logo"), PNG).status_code, 404)
        self.assertEqual(self.upload(self.admin_hn, self.org_url(self.org_hn_b, "/logo"), PNG).status_code, 200)


class OptionsTests(ThemeBase):
    def test_options_describe_tokens_and_fonts(self):
        data = self.as_user(self.org_admin).get("/api/v1/admin/theme/options").data
        self.assertEqual({token["key"] for token in data["tokens"]}, set(theme_service.TOKENS))
        self.assertEqual(data["min_contrast"], 4.5)
        self.assertIn("inter", {font["key"] for font in data["fonts"]})
