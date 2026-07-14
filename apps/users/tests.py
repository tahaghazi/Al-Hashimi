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


class StaffAndAuditTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.boss = User.objects.create_user(
            username="boss", password="x", is_staff=True, is_superuser=True,
            first_name="المدير", role="super_admin",
        )
        self.client.force_authenticate(self.boss)

    def test_super_admin_creates_staff_with_credentials(self):
        resp = self.client.post("/api/staff/", {"first_name": "موظف واحد", "phone": "0100"}, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        body = resp.json()
        self.assertIn("username", body)
        self.assertIn("password", body)
        u = User.objects.get(username=body["username"])
        self.assertTrue(u.is_staff)
        self.assertEqual(u.role, "staff")
        self.assertTrue(u.check_password(body["password"]))

    def test_duplicate_staff_name_rejected(self):
        self.client.post("/api/staff/", {"first_name": "مكرر", "phone": "1"}, format="json")
        resp = self.client.post("/api/staff/", {"first_name": "مكرر", "phone": "2"}, format="json")
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_non_super_admin_cannot_create_staff(self):
        staff = User.objects.create_user(username="s1", password="x", is_staff=True,
                                         first_name="عادي", role="staff")
        c = APIClient()
        c.force_authenticate(staff)
        resp = c.post("/api/staff/", {"first_name": "x", "phone": "0"}, format="json")
        self.assertEqual(resp.status_code, 403, resp.content)

    def test_customer_create_is_audited(self):
        resp = self.client.post("/api/users/", {"first_name": "عميل جديد", "phone": "012"}, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        logs = self.client.get("/api/audit/?action=create").json()
        self.assertGreaterEqual(logs["count"], 1)
        self.assertTrue(any(l["actor_username"] == "boss" and l["entity"] == "Customer"
                            for l in logs["results"]))

    def test_audit_requires_super_admin(self):
        staff = User.objects.create_user(username="s2", password="x", is_staff=True,
                                         first_name="عادي2", role="staff")
        c = APIClient()
        c.force_authenticate(staff)
        self.assertEqual(c.get("/api/audit/").status_code, 403)

    def test_financial_export_super_admin(self):
        resp = self.client.get("/api/export/financial/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("spreadsheet", resp["Content-Type"])
        self.assertTrue(resp.content[:2] == b"PK")  # xlsx is a zip

    def test_financial_export_forbidden_for_staff(self):
        staff = User.objects.create_user(username="s3", password="x", is_staff=True,
                                         first_name="عادي3", role="staff")
        c = APIClient()
        c.force_authenticate(staff)
        self.assertEqual(c.get("/api/export/financial/").status_code, 403)
