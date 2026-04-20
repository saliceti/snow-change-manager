#!/usr/bin/env python

import unittest
import subprocess
import os
import sys
from datetime import datetime
import json


class TestSnowChangeLifecycle(unittest.TestCase):
    """
    Integration test for ServiceNow change management CLI.
    Tests the full lifecycle: create -> update (Implement) -> update (Review) -> close (successful)
    """

    @classmethod
    def setUpClass(cls):
        """Verify required test inputs are set."""
        cls.snow_host = os.environ.get("SNOW_HOST")
        cls.snow_user = os.environ.get("SNOW_USER")
        cls.snow_password = os.environ.get("SNOW_PASSWORD")
        cls.snow_standard_change = os.environ.get("SNOW_STANDARD_CHANGE")
        cls.change_number = None

        missing_vars = []
        for var in [
            "SNOW_HOST",
            "SNOW_USER",
            "SNOW_PASSWORD",
                "SNOW_STANDARD_CHANGE"]:
            if not os.environ.get(var):
                missing_vars.append(var)

        if missing_vars:
            raise RuntimeError(
                f"Missing required environment variables: {
                    ', '.join(missing_vars)}")

    def setUp(self):
        """Reset state for each test."""
        self.change_number = None
        self.cli_script = os.path.join(
            os.path.dirname(__file__),
            "snow_change_manager.py")

    def run_cli(self, *args):
        """
        Execute the CLI with given arguments.
        Returns (returncode, stdout, stderr).
        """
        cmd = [
            sys.executable,
            self.cli_script,
            "--auth", "password",
            "--snow-host", self.snow_host,
            "--snow-user", self.snow_user,
            "--snow-password", self.snow_password,
        ] + list(args)
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode, result.stdout, result.stderr

    def parse_cli_output(self, output):
        """Parse key=value output from CLI."""
        result = {}
        for line in output.strip().split('\n'):
            if '=' in line:
                key, val = line.split('=', 1)
                result[key] = val
        return result

    def test_01_create_change(self):
        """Test: Create a new standard change."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        returncode, stdout, stderr = self.run_cli(
            "create",
            "--standard-change", self.snow_standard_change,
            "--short-description", f"Integration Test Change on {now}"
        )

        self.assertEqual(
            returncode,
            0,
            f"CLI failed: {stderr}\nOutput:\n{stdout}")
        output = self.parse_cli_output(stdout)

        # Store change number for subsequent tests
        self.change_number = output["CHANGE_NUMBER"]
        self.__class__.change_number = self.change_number

        # Verify via GET with --json
        returncode, stdout, stderr = self.run_cli(
            "--json",
            "get",
            "--number", self.change_number,
        )
        self.assertEqual(returncode, 0, f"GET verification failed: {stderr}")
        data = json.loads(stdout)

        self.assertEqual(
            data["result"][0]["sys_id"]["value"],
            output["CHANGE_SYS_ID"])
        self.assertEqual(
            data["result"][0]["number"]["value"],
            output['CHANGE_NUMBER'])
        self.assertEqual(data["result"][0]["state"]
                         ["display_value"], "Scheduled")

        print(
            f"\n✓ Created change: {
                output['CHANGE_NUMBER']} ({
                self.change_number}) with state: Scheduled")

    def test_02_update_to_implement(self):
        """Test: Update change state to Implement."""
        change_number = self.__class__.change_number

        self.assertIsNotNone(
            change_number,
            "change_number not set from test_01_create_change")

        returncode, stdout, stderr = self.run_cli(
            "implement",
            "--number", change_number
        )

        self.assertEqual(returncode, 0, f"CLI failed: {stderr}")

        # Verify via GET with --json
        returncode, stdout, stderr = self.run_cli(
            "--json",
            "get",
            "--number", change_number,
        )
        self.assertEqual(returncode, 0, f"GET verification failed: {stderr}")
        data = json.loads(stdout)
        self.assertEqual(data["result"][0]["number"]["value"], change_number)
        self.assertEqual(data["result"][0]["state"]
                         ["display_value"], "Implement")

        print(f"✓ Updated change to Implement")

    def test_03_update_to_review(self):
        """Test: Update change state to Review."""
        change_number = self.__class__.change_number
        self.assertIsNotNone(
            change_number,
            "change_number not set from test_01_create_change")

        returncode, stdout, stderr = self.run_cli(
            "review",
            "--number", change_number,
            "--result", "successful"
        )

        self.assertEqual(returncode, 0, f"CLI failed: {stderr}")

        # Verify via GET with --json
        returncode, stdout, stderr = self.run_cli(
            "--json",
            "get",
            "--number", change_number,
        )
        self.assertEqual(returncode, 0, f"GET verification failed: {stderr}")
        data = json.loads(stdout)
        self.assertEqual(data["result"][0]["number"]["value"], change_number)
        self.assertEqual(data["result"][0]["state"]["display_value"], "Review")

        print(f"✓ Updated change to Review")

    def test_04_post_work_note(self):
        """Test: Post work note to change."""
        change_number = self.__class__.change_number
        self.assertIsNotNone(
            change_number,
            "change_number not set from test_01_create_change")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        returncode, stdout, stderr = self.run_cli(
            "post-work-note",
            "--number", change_number,
            "--text", f"Test new work note on {now}"
        )

        self.assertEqual(returncode, 0, f"CLI failed: {stderr}")

        # Verify via GET with --json
        returncode, stdout, stderr = self.run_cli(
            "--json",
            "get",
            "--number", change_number,
        )
        self.assertEqual(returncode, 0, f"GET verification failed: {stderr}")
        data = json.loads(stdout)
        self.assertEqual(data["result"][0]["number"]["value"], change_number)
        self.assertIn(
            f"Test new work note on {now}",
            data["result"][0]["comments_and_work_notes"]['display_value'])

        print(f"✓ Posted work note")


if __name__ == "__main__":
    # Create a test suite with tests in order, stopping on first failure
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add tests in specific order
    suite.addTest(TestSnowChangeLifecycle('test_01_create_change'))
    suite.addTest(TestSnowChangeLifecycle('test_02_update_to_implement'))
    suite.addTest(TestSnowChangeLifecycle('test_03_update_to_review'))
    suite.addTest(TestSnowChangeLifecycle('test_04_post_work_note'))

    # Run with stop on first failure
    runner = unittest.TextTestRunner(verbosity=2, failfast=True)
    result = runner.run(suite)

    # Exit with appropriate code
    sys.exit(0 if result.wasSuccessful() else 1)
