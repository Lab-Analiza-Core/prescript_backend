from django.test import SimpleTestCase


class CorsPreflightTests(SimpleTestCase):
    def test_country_header_is_allowed_for_the_frontend_origin(self):
        response = self.client.options(
            "/api/v1/patients",
            HTTP_ORIGIN="http://localhost:5173",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization,x-prescript-country",
        )
        self.assertEqual(response.status_code, 200)
        allowed = response["Access-Control-Allow-Headers"].lower()
        self.assertIn("x-prescript-country", allowed)
        self.assertIn("authorization", allowed)
