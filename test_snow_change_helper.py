#!/usr/bin/env python

import io
import json
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import snow_change_helper


class _MockHttpResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class TestSnowChangeHelper(unittest.TestCase):
    def run_main(self, argv: list[str], env: dict[str, str]) -> str:
        stdout = io.StringIO()
        with patch.dict(os.environ, env, clear=False):
            with redirect_stdout(stdout):
                snow_change_helper.main(argv)
        return stdout.getvalue()

    def test_list_commits_writes_multiline_output_to_stdout(self):
        commits_context = [
            {
                "id": "abc123",
                "author": {"username": "alice"},
                "message": "Fix bug\nwith extra details",
            }
        ]
        env = {
            "COMMITS_CONTEXT": json.dumps(commits_context),
        }

        output = self.run_main(["--output-mode", "stdout", "list-commits"], env)

        self.assertEqual(
            output,
            "COMMITS_HTML<<EOF\n"
            "<table border='1' cellpadding='6' cellspacing='0' style='border-collapse: collapse;'>"
            "<thead><tr><th>Commit</th><th>Author</th><th>Message</th></tr></thead>"
            "<tbody><tr><td><code>abc123</code></td><td>alice</td><td>Fix bug with extra details</td></tr>\n"
            "</tbody></table>\n"
            "EOF\n",
        )

    def test_build_change_html_writes_expected_stdout_output(self):
        env = {
            "RELEASE_VERSION": "v1.2.3",
            "WORKFLOW_RUN_LINK": "https://github.com/owner/repo/actions/runs/123",
            "PR_NUMBER": "42",
            "PR_LINK": "https://github.com/owner/repo/pull/42",
            "JIRA_REFERENCE": "MBI-123",
            "JIRA_LINK": "https://nhsd-jira.digital.nhs.uk/browse/MBI-123",
            "GITHUB_SHA": "abcdef1234567890",
            "GITHUB_ACTOR": "alice",
            "COMMITS_HTML": "<table><tbody><tr><td>commit</td></tr></tbody></table>",
        }

        output = self.run_main(["--output-mode", "stdout", "build-change-html"], env)

        self.assertEqual(
            output,
            "CHANGE_HTML<<EOF\n"
            "<h2>Properties</h2>\n"
            "<table border=\"1\" cellpadding=\"6\" cellspacing=\"0\" style=\"border-collapse: collapse;\">\n"
            "  <thead><tr><th>Property</th><th>Value</th></tr></thead>\n"
            "  <tbody>\n"
            "    <tr><td>Release version</td><td><code>v1.2.3</code></td></tr>\n"
            "    <tr><td>Commit SHA</td><td><code>abcdef1234567890</code></td></tr>\n"
            "    <tr><td>Workflow run</td><td><a href=\"https://github.com/owner/repo/actions/runs/123\">Open workflow run</a></td></tr>\n"
            "    <tr><td>Triggered by</td><td>alice</td></tr>\n"
            "    <tr><td>Pull request</td><td><a href=\"https://github.com/owner/repo/pull/42\">#42</a></td></tr>\n"
            "    <tr><td>Jira ticket</td><td><a href=\"https://nhsd-jira.digital.nhs.uk/browse/MBI-123\">MBI-123</a></td></tr>\n"
            "  </tbody>\n"
            "</table>\n"
            "<h3>Commits</h3>\n"
            "<table><tbody><tr><td>commit</td></tr></tbody></table>\n"
            "EOF\n"
            "SHORT_DESCRIPTION=Release Manage breast screening version v1.2.3\n",
        )

    def test_add_create_change_summary_writes_expected_stdout_output(self):
        env = {
            "CHANGE_NUMBER": "CHG0030038",
            "CHANGE_LINK": "https://dev185914.service-now.com/now/nav/ui/classic/params/target/change_request.do?sys_id=2e94290183d88f103847c629feaad33c",
            "CHANGE_SYS_ID": "2e94290183d88f103847c629feaad33c",
            "SHORT_DESCRIPTION": "Release Manage breast screening version v1.2.3",
            "CHANGE_HTML": "<h2>Properties</h2>\n<table><tbody><tr><td>Value</td></tr></tbody></table>",
        }

        output = self.run_main(["--output-mode", "stdout", "add-create-change-summary"], env)

        self.assertEqual(
            output,
            "<h2>ServiceNow Change</h2>\n"
            "<table>\n"
            "  <thead><tr><th>Property</th><th>Value</th></tr></thead>\n"
            "  <tbody>\n"
            "    <tr><td>Change number</td><td><a href=\"https://dev185914.service-now.com/now/nav/ui/classic/params/target/change_request.do?sys_id=2e94290183d88f103847c629feaad33c\">CHG0030038</a></td></tr>\n"
            "    <tr><td>Short description</td><td>Release Manage breast screening version v1.2.3</td></tr>\n"
            "    <tr><td>Sys ID</td><td><code>2e94290183d88f103847c629feaad33c</code></td></tr>\n"
            "  </tbody>\n"
            "</table>\n"
            "<h2>Properties</h2>\n"
            "<table><tbody><tr><td>Value</td></tr></tbody></table>\n",
        )

    @patch("snow_change_helper.urllib.request.urlopen")
    def test_extract_pr_jira_uses_mocked_github_api_and_writes_stdout(self, mock_urlopen):
        mock_urlopen.return_value = _MockHttpResponse(
            {
                "body": "Release details https://nhsd-jira.digital.nhs.uk/browse/MBI-123",
            }
        )
        env = {
            "HEAD_COMMIT_MESSAGE": "Release [MBI-123] #42",
            "REPO_OWNER": "owner",
            "REPO_NAME": "repo",
            "REPO_HTML_URL": "https://github.com/owner/repo",
            "GITHUB_TOKEN": "fake-token",
        }

        output = self.run_main(["--output-mode", "stdout", "extract-pr-jira"], env)

        self.assertEqual(
            output,
            "pull_request_number=42\n"
            "pull_request_link=https://github.com/owner/repo/pull/42\n"
            "jira_reference=MBI-123\n"
            "jira_link=https://nhsd-jira.digital.nhs.uk/browse/MBI-123\n"
        )
        mock_urlopen.assert_called_once()


if __name__ == "__main__":
    unittest.main()
