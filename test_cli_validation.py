#!/usr/bin/env python

import os
import subprocess
import sys
import unittest


class TestCliEnvironmentValidation(unittest.TestCase):
    def setUp(self):
        self.cli_script = os.path.join(
            os.path.dirname(__file__),
            "snow_change_manager.py")

    def run_cli(self, args):
        result = subprocess.run(
            [sys.executable, self.cli_script] + args,
            capture_output=True,
            text=True,
        )
        return result

    def test_help_documents_command_line_arguments(self):
        result = self.run_cli(["--help"])

        self.assertEqual(result.returncode, 0)
        self.assertIn("--auth", result.stdout)
        self.assertIn("--snow-host", result.stdout)
        self.assertIn("--snow-user", result.stdout)
        self.assertIn("--snow-password", result.stdout)
        self.assertIn("--snow-client-id", result.stdout)
        self.assertIn("--snow-client-secret", result.stdout)
        self.assertIn("--snow-profile", result.stdout)
        self.assertIn("--custom", result.stdout)
        self.assertIn("--json", result.stdout)
        self.assertIn("--verbose", result.stdout)

    def test_missing_password_required_arguments_are_reported(self):
        result = self.run_cli(
            ["--auth", "password", "get-template-id", "--name", "Any Template"])

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "Missing required command line argument(s): --snow-host, --snow-user, --snow-password",
            result.stderr)

    def test_missing_oauth_required_arguments_are_reported(self):
        result = self.run_cli(
            ["--auth", "oauth", "get-template-id", "--name", "Any Template"])

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "Missing required command line argument(s): --snow-host, --snow-client-id, --snow-client-secret",
            result.stderr)

    def test_whitespace_only_argument_is_reported(self):
        result = self.run_cli(
            [
                "--auth", "password",
                "--snow-host", "example.service-now.com",
                "--snow-user", "   ",
                "--snow-password", "secret",
                "get-template-id", "--name", "Any Template"
            ],
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "Missing required command line argument(s): --snow-user",
            result.stderr)

    def test_review_state_still_requires_result(self):
        result = self.run_cli(
            [
                "--auth", "password",
                "--snow-host", "example.service-now.com",
                "--snow-user", "user",
                "--snow-password", "secret",
                "review", "--number", "CHG0030052"
            ],
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "review: error: the following arguments are required: --result",
            result.stderr)

    def test_custom_mode_requires_profile(self):
        result = self.run_cli(
            [
                "--auth", "oauth",
                "--snow-host", "example.service-now.com",
                "--snow-client-id", "id",
                "--snow-client-secret", "secret",
                "--custom",
                "get-template-id", "--name", "Any Template"
            ],
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "Missing required command line argument(s): --snow-profile",
            result.stderr)


if __name__ == "__main__":
    unittest.main()
