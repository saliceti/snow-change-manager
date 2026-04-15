#!/usr/bin/env python3

import argparse
import json
import os
import re
import subprocess
import urllib.request


def write_output(name: str, value: str) -> None:
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
        fh.write(f"{name}={value}\n")


def write_multiline_output(name: str, value: str) -> None:
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
        print(f"{name}<<EOF", file=fh)
        print(value, file=fh)
        print("EOF", file=fh)


def build_snow_args() -> list[str]:
    snow_auth = os.environ["SNOW_AUTH"]
    snow_args = [
        "--auth",
        snow_auth,
        "--snow-host",
        os.environ["SNOW_HOST"],
    ]

    if snow_auth == "password":
        snow_args.extend([
            "--snow-user",
            os.environ["SNOW_USER"],
            "--snow-password",
            os.environ["SNOW_PASSWORD"],
        ])
    elif snow_auth == "oauth":
        snow_args.extend([
            "--client-id",
            os.environ["SNOW_CLIENT_ID"],
            "--client-secret",
            os.environ["SNOW_CLIENT_SECRET"],
        ])
    else:
        raise RuntimeError(f"Unsupported SNOW_AUTH value: {snow_auth}")

    return snow_args


def run_snow_command(command_args: list[str], capture_output: bool = False) -> subprocess.CompletedProcess[str]:
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
            headers={
                "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
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
        print(f"Jira link not found. Using Jira reference {jira_reference} from PR title.")
        jira_link = f"https://nhsd-jira.digital.nhs.uk/browse/{jira_reference}"

    repo_html_url = os.environ["REPO_HTML_URL"]
    pr_link = f"{repo_html_url}/pull/{pr_number}"

    print(f"pull_request_number={pr_number}")
    print(f"pull_request_link={pr_link}")
    print(f"jira_reference={jira_reference}")
    print(f"jira_link={jira_link}")

    write_output("pull_request_number", pr_number)
    write_output("pull_request_link", pr_link)
    write_output("jira_reference", jira_reference)
    write_output("jira_link", jira_link)


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

    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
        fh.write(header + "\n")
        fh.write(change_html + "\n")


def snow_command(command_args: list[str]) -> None:
    run_snow_command(command_args)


def main() -> None:
    parser = argparse.ArgumentParser(description="Workflow data helpers")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-commits")
    subparsers.add_parser("extract-pr-jira")
    subparsers.add_parser("build-change-html")
    subparsers.add_parser("add-create-change-summary")
    subparsers.add_parser("snow-command")

    args, extra = parser.parse_known_args()

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


if __name__ == "__main__":
    main()
