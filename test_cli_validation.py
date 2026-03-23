#!/usr/bin/env python

import os
import subprocess
import sys
import unittest


class TestCliEnvironmentValidation(unittest.TestCase):
    def setUp(self):
        self.cli_script = os.path.join(os.path.dirname(__file__), "snow_change_manager.py")

    def run_cli(self, args, env_updates=None, remove_vars=None):
        env = os.environ.copy()

        if remove_vars:
            for var in remove_vars:
                env.pop(var, None)

        if env_updates:
            env.update(env_updates)

        result = subprocess.run(
            [sys.executable, self.cli_script] + args,
            capture_output=True,
            text=True,
            env=env,
        )
        return result

    def test_help_documents_required_environment_variables(self):
        result = self.run_cli(["--help"])

        self.assertEqual(result.returncode, 0)
        self.assertIn("Required environment variables", result.stdout)
        self.assertIn("SNOW_HOST", result.stdout)
        self.assertIn("SNOW_USER", result.stdout)
        self.assertIn("SNOW_PASSWORD", result.stdout)

    def test_missing_environment_variables_are_reported(self):
        result = self.run_cli(
            ["get-template-id", "--name", "Any Template"],
            remove_vars=["SNOW_HOST", "SNOW_USER", "SNOW_PASSWORD"],
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing required environment variable(s): SNOW_HOST, SNOW_USER, SNOW_PASSWORD", result.stderr)

    def test_whitespace_only_environment_variable_is_reported(self):
        result = self.run_cli(
            ["get-template-id", "--name", "Any Template"],
            env_updates={
                "SNOW_HOST": "example.service-now.com",
                "SNOW_USER": "   ",
                "SNOW_PASSWORD": "secret",
            },
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing required environment variable(s): SNOW_USER", result.stderr)

    def test_invalid_snow_host_is_reported(self):
        result = self.run_cli(
            ["get-template-id", "--name", "Any Template"],
            env_updates={
                "SNOW_HOST": "https://example.service-now.com",
                "SNOW_USER": "user",
                "SNOW_PASSWORD": "secret",
            },
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Invalid SNOW_HOST", result.stderr)
        self.assertIn("example.service-now.com", result.stderr)

    def test_closed_state_still_requires_result(self):
        result = self.run_cli(
            ["update", "--sys-id", "abc123", "--state", "Closed"],
            env_updates={
                "SNOW_HOST": "example.service-now.com",
                "SNOW_USER": "user",
                "SNOW_PASSWORD": "secret",
            },
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--result is required when --state Closed", result.stderr)


if __name__ == "__main__":
    unittest.main()
