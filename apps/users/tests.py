"""
Auth contract smoke tests.

The Nuxt frontend logs in against dj-rest-auth and reads `access_token` from
the response, then calls the session endpoint with that token. These tests pin
that contract so upgrading allauth / dj-rest-auth can't silently break login.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

User = get_user_model()


class AuthContractTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.username = "operator"
        self.password = "s3cret-pass-123"
        self.user = User.objects.create_user(
            username=self.username,
            password=self.password,
            email="operator@example.com",
            first_name="المشغل",
        )

    def test_login_returns_access_token(self):
        resp = self.client.post(
            "/api/authentication/login/",
            {"username": self.username, "password": self.password},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIn("access_token", resp.json())

    def test_session_endpoint_requires_auth(self):
        # Unauthenticated request to the user/session endpoint must be rejected.
        resp = self.client.get("/api/authentication/user/")
        self.assertIn(resp.status_code, (401, 403), resp.content)

    def test_authenticated_session_returns_user(self):
        self.client.force_authenticate(self.user)
        resp = self.client.get("/api/authentication/user/")
        self.assertEqual(resp.status_code, 200, resp.content)
