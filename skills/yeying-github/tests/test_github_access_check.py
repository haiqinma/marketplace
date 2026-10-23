from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import github_access_check  # noqa: E402


class GitHubAccessCheckTests(unittest.TestCase):
    def test_verifies_expected_private_fork_parent(self) -> None:
        github_access_check.verify_fork_relationship(
            "liuppx/billing",
            "yeying-community/billing",
            {
                "fork": True,
                "parent": {"full_name": "YeYing-Community/Billing"},
            },
        )

    def test_rejects_repository_outside_expected_fork_network(self) -> None:
        with self.assertRaisesRegex(SystemExit, "different fork network"):
            github_access_check.verify_fork_relationship(
                "liuppx/billing",
                "yeying-community/billing",
                {"fork": True, "parent": {"full_name": "other/billing"}},
            )

    def test_http_error_does_not_include_token(self) -> None:
        error = urllib_error(404)
        with mock.patch.object(
            github_access_check.urllib.request, "urlopen", side_effect=error
        ), self.assertRaises(SystemExit) as raised:
            github_access_check.github_json(
                "liuppx/billing", "", "super-secret", "pull_request_token"
            )
        self.assertIn("pull_request_token", str(raised.exception))
        self.assertNotIn("super-secret", str(raised.exception))


def urllib_error(code: int) -> github_access_check.urllib.error.HTTPError:
    return github_access_check.urllib.error.HTTPError(
        "https://api.github.com/repos/liuppx/billing",
        code,
        "Not Found",
        {},
        None,
    )


if __name__ == "__main__":
    unittest.main()
