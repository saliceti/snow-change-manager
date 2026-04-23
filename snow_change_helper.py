#!/usr/bin/env python3

import argparse
import glob
import io
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request


OUTPUT_MODE = "github"


def configure_output_mode(mode: str) -> None:
    global OUTPUT_MODE
    OUTPUT_MODE = mode


def write_output(name: str, value: str) -> None:
    if OUTPUT_MODE == "stdout":
        print(f"{name}={value}")
    else:
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
            fh.write(f"{name}={value}\n")


def write_multiline_output(name: str, value: str) -> None:
    if OUTPUT_MODE == "stdout":
        print(f"{name}<<EOF")
        print(value)
        print("EOF")
    else:
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
            print(f"{name}<<EOF", file=fh)
            print(value, file=fh)
            print("EOF", file=fh)


def write_summary(value: str) -> None:
    if OUTPUT_MODE == "stdout":
        print(value, end="")
    else:
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write(value)


def _github_headers() -> dict[str, str]:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise RuntimeError(
            "Missing GitHub token. Set GITHUB_TOKEN (or GH_TOKEN) to call GitHub API endpoints."
        )

    return {
        "Authorization": f"Bearer {token.strip()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10",
    }

# Used to stop following redirects
class _NoRedirect302(urllib.request.HTTPRedirectHandler):
    def http_error_302(self, req, fp, code, msg, headers):
        return None


def _download_url_handling_github_redirects(api_url: str) -> bytes:
    request = urllib.request.Request(api_url, headers=_github_headers())
    no_redirect_opener = urllib.request.build_opener(_NoRedirect302)

    try:
        with no_redirect_opener.open(request) as response:
            return response.read()
    # 302 redirects are caught and we expect an HTTPError
    except urllib.error.HTTPError as err:
        redirect_url = err.headers.get("Location")
        redirect_request = urllib.request.Request(redirect_url)

        with urllib.request.urlopen(redirect_request) as response:
            return response.read()


def build_snow_args() -> list[str]:
    snow_auth = os.environ["SNOW_AUTH"]
    snow_args = [
        "--auth",
        snow_auth,
        "--snow-host",
        os.environ["SNOW_HOST"],
    ]

    custom = os.environ.get("SNOW_CUSTOM")
    if custom == "true":
        snow_args.extend([
            "--custom",
            "--snow-profile",
            os.environ["SNOW_PROFILE"]
        ])

    if snow_auth == "password":
        snow_args.extend([
            "--snow-user",
            os.environ["SNOW_USER"],
            "--snow-password",
            os.environ["SNOW_PASSWORD"],
        ])
    elif snow_auth == "oauth":
        snow_args.extend([
            "--snow-client-id",
            os.environ["SNOW_CLIENT_ID"],
            "--snow-client-secret",
            os.environ["SNOW_CLIENT_SECRET"],
        ])
    else:
        raise RuntimeError(f"Unsupported SNOW_AUTH value: {snow_auth}")

    return snow_args


def run_snow_command(
        command_args: list[str],
        capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["./snow_change_manager.py", *build_snow_args(), *command_args],
        capture_output=capture_output,
        text=True,
        check=True,
    )


def list_commits() -> None:
    commit_list = json.loads(os.environ["COMMITS_CONTEXT"])
    if not commit_list:
        return

    rows = ""
    for commit in commit_list:
        commit_id = commit["id"]
        author = commit["author"]["username"]
        message = commit["message"].strip().replace("\n", " ")
        rows += f"<tr><td><code>{commit_id}</code></td><td>{author}</td><td>{message}</td></tr>\n"

    html = (
        "<table border='1' cellpadding='6' cellspacing='0' style='border-collapse: collapse;'>"
        "<thead><tr><th>Commit</th><th>Author</th><th>Message</th></tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
    )

    write_multiline_output("COMMITS_HTML", html)


def extract_pr_jira() -> None:
    message = os.environ.get("HEAD_COMMIT_MESSAGE", "")

    pr_number_match = re.search(r"#(\d+)", message)
    pr_number = pr_number_match.group(1) if pr_number_match else ""

    jira_ref_match = re.search(r"\[([A-Z][A-Z0-9]+-\d+)\]", message)
    jira_reference = jira_ref_match.group(1) if jira_ref_match else ""

    jira_link = ""

    if pr_number:
        api_url = (
            f"https://api.github.com/repos/{os.environ['REPO_OWNER']}/"
            f"{os.environ['REPO_NAME']}/pulls/{pr_number}"
        )
        request = urllib.request.Request(
            api_url,
            headers = _github_headers(),
        )
        with urllib.request.urlopen(request) as response:
            pr = json.loads(response.read())
        body = pr.get("body") or ""
        jira_link_match = re.search(
            r"https://nhsd-jira\.digital\.nhs\.uk/browse/[A-Z][A-Z0-9]+-\d+",
            body,
        )
        jira_link = jira_link_match.group(0) if jira_link_match else ""

    if jira_link == "" and jira_reference != "":
        print(
            f"Jira link not found. Using Jira reference {jira_reference} from PR title.")
        jira_link = f"https://nhsd-jira.digital.nhs.uk/browse/{jira_reference}"

    repo_html_url = os.environ["REPO_HTML_URL"]
    pr_link = f"{repo_html_url}/pull/{pr_number}"

    write_output("pull_request_number", pr_number)
    write_output("pull_request_link", pr_link)
    write_output("jira_reference", jira_reference)
    write_output("jira_link", jira_link)

def _get_job_id(run_id, job):
    api_url = (
        f"https://api.github.com/repos/{os.environ['REPO_OWNER']}/"
        f"{os.environ['REPO_NAME']}/actions/runs/{run_id}/jobs"
    )
    request = urllib.request.Request(api_url, headers=_github_headers())
    with urllib.request.urlopen(request) as response:
        jobs_string = response.read()

    jobs = json.loads(jobs_string)["jobs"]
    matching_job_ids = [j["id"] for j in jobs if j["name"] == job]
    if not matching_job_ids:
        available_jobs = ", ".join(j["name"] for j in jobs)
        raise RuntimeError(
            f"Job '{job}' not found in run {run_id}. Available jobs: {available_jobs}"
        )
    job_id = matching_job_ids[0]

    return job_id


def github_actions_logs(run_id: str, job) -> None:
    job_id = _get_job_id(run_id, job)

    api_url = (
        f"https://api.github.com/repos/{os.environ['REPO_OWNER']}/"
        f"{os.environ['REPO_NAME']}/actions/jobs/{job_id}/logs"
    )

    # The request to Github API is a redirect 302
    # If urllib follows the redirect, the second request returns 401
    # We must handle the redirect explicitly
    job_log = _download_url_handling_github_redirects(api_url).decode("utf-8")

    print(job_log)


def build_change_html() -> None:
    release_version = os.environ["RELEASE_VERSION"]
    short_description = f"Release Manage breast screening version {release_version}"

    workflow_run_link = os.environ["WORKFLOW_RUN_LINK"]
    pr_number = os.environ["PR_NUMBER"]
    pr_link = os.environ["PR_LINK"]
    jira_ref = os.environ["JIRA_REFERENCE"]
    jira_link = os.environ["JIRA_LINK"]
    sha = os.environ["GITHUB_SHA"]
    actor = os.environ["GITHUB_ACTOR"]
    commits_html = os.environ["COMMITS_HTML"]

    html = f"""<h2>Properties</h2>
<table border=\"1\" cellpadding=\"6\" cellspacing=\"0\" style=\"border-collapse: collapse;\">
  <thead><tr><th>Property</th><th>Value</th></tr></thead>
  <tbody>
    <tr><td>Release version</td><td><code>{release_version}</code></td></tr>
    <tr><td>Commit SHA</td><td><code>{sha}</code></td></tr>
    <tr><td>Workflow run</td><td><a href=\"{workflow_run_link}\">Open workflow run</a></td></tr>
    <tr><td>Triggered by</td><td>{actor}</td></tr>
    <tr><td>Pull request</td><td><a href=\"{pr_link}\">#{pr_number}</a></td></tr>
    <tr><td>Jira ticket</td><td><a href=\"{jira_link}\">{jira_ref}</a></td></tr>
  </tbody>
</table>
<h3>Commits</h3>
{commits_html}"""

    write_multiline_output("CHANGE_HTML", html)
    write_output("SHORT_DESCRIPTION", short_description)


def add_create_change_summary() -> None:
    change_number = os.environ["CHANGE_NUMBER"]
    change_link = os.environ["CHANGE_LINK"]
    change_sys_id = os.environ["CHANGE_SYS_ID"]
    change_html = os.environ["CHANGE_HTML"]
    short_description = os.environ["SHORT_DESCRIPTION"]

    header = f"""<h2>ServiceNow Change</h2>
<table>
  <thead><tr><th>Property</th><th>Value</th></tr></thead>
  <tbody>
    <tr><td>Change number</td><td><a href=\"{change_link}\">{change_number}</a></td></tr>
    <tr><td>Short description</td><td>{short_description}</td></tr>
    <tr><td>Sys ID</td><td><code>{change_sys_id}</code></td></tr>
  </tbody>
</table>"""

    write_summary(header + "\n" + change_html + "\n")


def snow_command(command_args: list[str]) -> None:
    run_snow_command(command_args)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Workflow data helpers")
    parser.add_argument(
        "--output-mode",
        choices=["github", "stdout"],
        default="github",
        help="where helper outputs are written (default: github)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-commits")
    subparsers.add_parser("extract-pr-jira")
    subparsers.add_parser("build-change-html")
    subparsers.add_parser("add-create-change-summary")
    subparsers.add_parser("snow-command")
    ga_logs = subparsers.add_parser("github-actions-logs")
    ga_logs.add_argument(
    "--run-id",
    required=True,
    help="workflow run id (required)")
    ga_logs.add_argument(
    "--job",
    required=True,
    help="job name (required)")

    args, extra = parser.parse_known_args(argv)
    configure_output_mode(args.output_mode)

    if args.command == "list-commits":
        list_commits()
    elif args.command == "extract-pr-jira":
        extract_pr_jira()
    elif args.command == "build-change-html":
        build_change_html()
    elif args.command == "add-create-change-summary":
        add_create_change_summary()
    elif args.command == "snow-command":
        snow_command(extra)
    elif args.command == "github-actions-logs":
        github_actions_logs(args.run_id, args.job)


if __name__ == "__main__":
    main(sys.argv[1:])
