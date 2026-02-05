#!/usr/bin/env python

import unittest
import subprocess
import os
import sys
import json
import re

class TestSnowChangeLifecycle(unittest.TestCase):
    """
    Integration test for ServiceNow change management CLI.
    Tests the full lifecycle: create -> update (Implement) -> update (Review) -> close (successful)
    """

    @classmethod
    def setUpClass(cls):
        """Verify required environment variables are set."""
        cls.snow_url = os.environ.get("SNOW_URL")
        cls.snow_user = os.environ.get("SNOW_USER")
        cls.snow_password = os.environ.get("SNOW_PASSWORD")
        cls.snow_standard_change = os.environ.get("SNOW_STANDARD_CHANGE")

        missing_vars = []
        for var in ["SNOW_URL", "SNOW_USER", "SNOW_PASSWORD", "SNOW_STANDARD_CHANGE"]:
            if not os.environ.get(var):
                missing_vars.append(var)

        if missing_vars:
            raise RuntimeError(f"Missing required environment variables: {', '.join(missing_vars)}")

    def setUp(self):
        """Reset state for each test."""
        self.change_sys_id = None
        self.cli_script = os.path.join(os.path.dirname(__file__), "snow_change_manager.py")

    def run_cli(self, *args):
        """
        Execute the CLI with given arguments.
        Returns (returncode, stdout, stderr).
        """
        cmd = [sys.executable, self.cli_script] + list(args)
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
        returncode, stdout, stderr = self.run_cli(
            "create",
            "--standard-change", self.snow_standard_change,
            "--short-description", "Integration Test Change"
        )

        self.assertEqual(returncode, 0, f"CLI failed: {stderr}")
        output = self.parse_cli_output(stdout)

        # Validate required fields
        self.assertIn("CHANGE_NUMBER", output, "CHANGE_NUMBER not in response")
        self.assertIn("CHANGE_SYS_ID", output, "CHANGE_SYS_ID not in response")
        self.assertIn("CHANGE_STATE", output, "CHANGE_STATE not in response")

        # Store sys_id for subsequent tests
        self.change_sys_id = output["CHANGE_SYS_ID"]
        self.__class__.change_sys_id = self.change_sys_id

        print(f"\n✓ Created change: {output['CHANGE_NUMBER']} ({self.change_sys_id})")

    def test_02_update_to_implement(self):
        """Test: Update change state to Implement."""
        change_sys_id = self.__class__.change_sys_id
        self.assertIsNotNone(change_sys_id, "change_sys_id not set from test_01_create_change")

        returncode, stdout, stderr = self.run_cli(
            "update",
            "--sys-id", change_sys_id,
            "--state", "Implement"
        )

        self.assertEqual(returncode, 0, f"CLI failed: {stderr}")
        output = self.parse_cli_output(stdout)

        self.assertIn("CHANGE_STATE", output, "CHANGE_STATE not in response")
        self.assertEqual(output["CHANGE_STATE"], "Implement", f"Expected state 'Implement', got '{output['CHANGE_STATE']}'")

        print(f"✓ Updated change to Implement")

    def test_03_update_to_review(self):
        """Test: Update change state to Review."""
        change_sys_id = self.__class__.change_sys_id
        self.assertIsNotNone(change_sys_id, "change_sys_id not set from test_01_create_change")

        returncode, stdout, stderr = self.run_cli(
            "update",
            "--sys-id", change_sys_id,
            "--state", "Review"
        )

        self.assertEqual(returncode, 0, f"CLI failed: {stderr}")
        output = self.parse_cli_output(stdout)

        self.assertIn("CHANGE_STATE", output, "CHANGE_STATE not in response")
        self.assertEqual(output["CHANGE_STATE"], "Review", f"Expected state 'Review', got '{output['CHANGE_STATE']}'")

        print(f"✓ Updated change to Review")

    def test_04_close_change_successful(self):
        """Test: Close change with result=successful."""
        change_sys_id = self.__class__.change_sys_id
        self.assertIsNotNone(change_sys_id, "change_sys_id not set from test_01_create_change")

        returncode, stdout, stderr = self.run_cli(
            "update",
            "--sys-id", change_sys_id,
            "--state", "Closed",
            "--result", "successful"
        )

        self.assertEqual(returncode, 0, f"CLI failed: {stderr}")
        output = self.parse_cli_output(stdout)

        self.assertIn("CHANGE_STATE", output, "CHANGE_STATE not in response")
        self.assertEqual(output["CHANGE_STATE"], "Closed", f"Expected state 'Closed', got '{output['CHANGE_STATE']}'")

        print(f"✓ Closed change successfully")

    def test_05_get_change_final_state(self):
        """Test: Retrieve final change state via GET."""
        change_sys_id = self.__class__.change_sys_id
        self.assertIsNotNone(change_sys_id, "change_sys_id not set from test_01_create_change")

        returncode, stdout, stderr = self.run_cli(
            "get",
            "--sys-id", change_sys_id
        )

        self.assertEqual(returncode, 0, f"CLI failed: {stderr}")
        output = self.parse_cli_output(stdout)

        self.assertIn("CHANGE_STATE", output, "CHANGE_STATE not in response")
        self.assertEqual(output["CHANGE_STATE"], "Closed", f"Expected final state 'Closed', got '{output['CHANGE_STATE']}'")

        print(f"✓ Verified final change state is Closed")


if __name__ == "__main__":
    # Run tests in order (verbosity=2 for detailed output)
    unittest.main(verbosity=2)
