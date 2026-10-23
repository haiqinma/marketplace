from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import github_app_login  # noqa: E402


class GitHubAppLoginTests(unittest.TestCase):
    def test_device_flow_requests_offline_access_and_waits_for_user(self) -> None:
        responses = [
            {
                "device_code": "device-secret",
                "user_code": "ABCD-EFGH",
                "verification_uri": "https://github.com/login/device",
                "expires_in": 900,
                "interval": 5,
            },
            {"error": "authorization_pending"},
            {
                "access_token": "user-secret",
                "refresh_token": "refresh-secret",
                "expires_in": 28800,
            },
        ]
        with mock.patch.object(
            github_app_login, "post", side_effect=responses
        ) as post, mock.patch.object(
            github_app_login.time, "sleep"
        ), mock.patch.object(
            github_app_login.time, "monotonic", side_effect=[0, 1, 2]
        ), mock.patch("builtins.print") as printed:
            result = github_app_login.login("Iv1.test")
        self.assertEqual(result["access_token"], "user-secret")
        self.assertEqual(post.call_args_list[0].args[1]["scope"], "offline_access")
        output = " ".join(str(call.args[0]) for call in printed.call_args_list)
        self.assertIn("ABCD-EFGH", output)
        self.assertNotIn("device-secret", output)
        self.assertNotIn("user-secret", output)


if __name__ == "__main__":
    unittest.main()
