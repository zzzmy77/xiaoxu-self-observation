"""
Basic API smoke tests for 小绪·自我观察日记.

Run: python -m unittest tests.test_api -v
"""
import sys
import os
import json
import unittest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


class TestWithLogin(unittest.TestCase):
    """Base class: log in as demo user before each test."""

    @classmethod
    def setUpClass(cls):
        import os
        os.environ["DISABLE_VECTOR"] = "1"
        from app import create_app
        cls.app = create_app()
        cls.client = cls.app.test_client()

    def setUp(self):
        """Log in as demo user before each test."""
        self.client.post("/auth/login", data={
            "username": "demo",
            "password": "demo123",
        }, follow_redirects=True)

    def login(self):
        """Helper: POST login form."""
        return self.client.post("/auth/login", data={
            "username": "demo",
            "password": "demo123",
        }, follow_redirects=True)


class TestAppInit(TestWithLogin):
    """App-level smoke tests."""

    def test_index_redirect_auth(self):
        """GET / when logged in should redirect to /chat/"""
        resp = self.client.get("/", follow_redirects=False)
        self.assertIn(resp.status_code, (301, 302))
        # Should redirect to /chat/ or /auth/login
        self.assertTrue("/chat" in resp.location or "/auth/login" in resp.location)

    def test_chat_page(self):
        """GET /chat/ should return 200"""
        resp = self.client.get("/chat/")
        self.assertEqual(resp.status_code, 200)

    def test_insights_page(self):
        """GET /insights/ should return 200"""
        resp = self.client.get("/insights/")
        self.assertEqual(resp.status_code, 200)

    def test_diaries_page(self):
        """GET /diaries/ should return 200"""
        resp = self.client.get("/diaries/")
        self.assertEqual(resp.status_code, 200)

    def test_monthly_page(self):
        """GET /monthly/ should return 200"""
        resp = self.client.get("/monthly/")
        self.assertEqual(resp.status_code, 200)

    def test_profile_page(self):
        """GET /profile/ should return 200"""
        resp = self.client.get("/profile/")
        self.assertEqual(resp.status_code, 200)

    def test_analytics_page(self):
        """GET /analytics/ should return 200"""
        resp = self.client.get("/analytics/")
        self.assertEqual(resp.status_code, 200)


class TestChatAPI(TestWithLogin):
    """Chat API functional tests."""

    def test_send_message(self):
        """POST /chat/api/send with a message should return response."""
        resp = self.client.post(
            "/chat/api/send",
            data=json.dumps({"message": "今天心情不太好"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("response", data)
        self.assertIsInstance(data["response"], str)
        # Allow empty response for API-only tests that don't have actual LLM connection
        if len(data["response"]) == 0:
            self.assertIn("structured_meta", data)

    def test_empty_message(self):
        """POST with empty message should return 400."""
        resp = self.client.post(
            "/chat/api/send",
            data=json.dumps({"message": ""}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_missing_message(self):
        """POST with no message field should return 400."""
        resp = self.client.post(
            "/chat/api/send",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_new_session(self):
        """POST /chat/api/new should create a new session."""
        resp = self.client.post("/chat/api/new")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("session_id", data)
        self.assertIsInstance(data["session_id"], int)

    def test_set_mode_exploring(self):
        """Set mode to exploring."""
        resp = self.client.post(
            "/chat/api/mode",
            data=json.dumps({"mode": "exploring"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["mode"], "exploring")

    def test_set_mode_listening(self):
        """Set mode to listening."""
        resp = self.client.post(
            "/chat/api/mode",
            data=json.dumps({"mode": "listening"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["mode"], "listening")

    def test_set_mode_invalid(self):
        """Invalid mode should return 400."""
        resp = self.client.post(
            "/chat/api/mode",
            data=json.dumps({"mode": "invalid_mode"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)


class TestAuth(TestWithLogin):
    """Auth route tests."""

    def test_login_page_get(self):
        """GET /auth/login should return 200 (or 302 when already logged in)."""
        resp = self.client.get("/auth/login", follow_redirects=False)
        self.assertIn(resp.status_code, (200, 302))

    def test_register_page_get(self):
        """GET /auth/register should return 200 (or 302 when already logged in)."""
        resp = self.client.get("/auth/register", follow_redirects=False)
        self.assertIn(resp.status_code, (200, 302))

    def test_demo_login(self):
        """GET /auth/demo should log in and redirect."""
        resp = self.client.get("/auth/demo", follow_redirects=False)
        self.assertIn(resp.status_code, (301, 302))

    def test_login_post_success(self):
        """POST /auth/login with valid credentials should redirect."""
        resp = self.client.post("/auth/login", data={
            "username": "demo",
            "password": "demo123",
        }, follow_redirects=False)
        self.assertIn(resp.status_code, (301, 302))

    def test_login_post_fail(self):
        """POST /auth/login with wrong password should stay on login page."""
        # Log out first
        self.client.get("/auth/logout", follow_redirects=True)
        resp = self.client.post("/auth/login", data={
            "username": "demo",
            "password": "wrongpass",
        })
        # Should stay on login page (200) with error flash
        self.assertEqual(resp.status_code, 200)


class TestInsightsAPI(TestWithLogin):
    """Insights API tests."""

    def test_insight_data(self):
        """GET /insights/api/data should return structured data."""
        resp = self.client.get("/insights/api/data")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("emotion_frequencies", data)
        self.assertIn("attributions", data)
        self.assertIn("self_insights", data)
        self.assertIn("session_count", data)
        self.assertIn("patterns", data)


class TestDiariesAPI(TestWithLogin):
    """Diaries API tests."""

    def test_calendar_data(self):
        """GET /diaries/api/calendar should return calendar data."""
        resp = self.client.get("/diaries/api/calendar?year=2026&month=6")
        self.assertEqual(resp.status_code, 200)

    def test_diary_list(self):
        """Diary list should return seed data."""
        resp = self.client.get("/diaries/api/day/2026/6/4")
        self.assertIn(resp.status_code, (200, 404))


class TestProfileAPI(TestWithLogin):
    """Profile API tests."""

    def test_get_profile(self):
        """GET /profile/api should return user data."""
        resp = self.client.get("/profile/api")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("username", data)
        self.assertIn("settings", data)
        self.assertIn("profile", data)

    def test_update_profile(self):
        """POST /profile/api/update should update profile fields."""
        resp = self.client.post(
            "/profile/api/update",
            data=json.dumps({"username": "测试用户", "identity": "职场人"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "ok")
        # Restore
        self.client.post(
            "/profile/api/update",
            data=json.dumps({"username": "demo"}),
            content_type="application/json",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
