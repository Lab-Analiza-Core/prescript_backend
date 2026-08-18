from django.test import SimpleTestCase

from api.roles import get_primary_prescript_role, normalize_prescript_roles



class PrescriptRoleTests(SimpleTestCase):
    def test_normalizes_spanish_and_legacy_roles_to_interactive_core_codes(self):
        roles = normalize_prescript_roles(["Gerente", "COUNTRY_MANAGER", "Secretaria", "Enfermera"])

        self.assertEqual(roles, ["COUNTRY_MANAGER", "SECRETARY", "NURSE"])
        self.assertEqual(get_primary_prescript_role(roles), "COUNTRY_MANAGER")


