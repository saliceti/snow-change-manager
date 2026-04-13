#!/usr/bin/env python

import os
import subprocess
import sys
import unittest


class TestCliEnvironmentValidation(unittest.TestCase):
    def setUp(self):
        self.cli_script = os.path.join(os.path.dirname(__file__), "snow_change_manager.py")

    def run_cli(self, args):
        result = subprocess.run(
            [sys.executable, self.cli_script] + args,
            capture_output=True,
            text=True,
        )
        return result

    def test_help_documents_required_command_line_arguments(self):
        result = self.run_cli(["--help"])

        self.assertEqual(result.returncode, 0)
        self.assertIn("Required command line arguments", result.stdout)
        self.assertIn("--snow-host", result.stdout)
        self.assertIn("--snow-user", result.stdout)
        self.assertIn("--snow-password", result.stdout)
        self.assertIn("--custom", result.stdout)
        self.assertIn("--profile", result.stdout)

    def test_missing_required_arguments_are_reported(self):
        result = self.run_cli(["--auth", "password", "get-template-id", "--name", "Any Template"])

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing required command line argument(s): --snow-host, --snow-user, --snow-password", result.stderr)

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
        self.assertIn("Missing required command line argument(s): --snow-user", result.stderr)

    def test_closed_state_still_requires_result(self):
        result = self.run_cli(
            [
                "--auth", "password",
                "--snow-host", "example.service-now.com",
                "--snow-user", "user",
                "--snow-password", "secret",
                "update", "--sys-id", "abc123", "--state", "Closed"
            ],
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--result is required when --state Closed", result.stderr)

    def test_custom_mode_requires_profile(self):
        result = self.run_cli(
            [
                "--auth", "oauth",
                "--snow-host", "example.service-now.com",
                "--client-id", "id",
                "--client-secret", "secret",
                "--custom",
                "get-template-id", "--name", "Any Template"
            ],
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing required command line argument(s): --profile", result.stderr)


if __name__ == "__main__":
    unittest.main()
