#!/usr/bin/env python

import os
import base64
import json
import urllib.parse
import urllib.request
import urllib.error
import getpass
import sys
import argparse

def create(snow_url, snow_standard_change, assignment_group, user, password,
           short_description="abcd", debug=False):
    """
    Construct and POST a standard change using the provided parameters.
    Returns (status, data) where data is parsed JSON (or raw body on parse error).
    """
    base_url = f"{snow_url}/api/sn_chg_rest/change/standard/{snow_standard_change}"
    params = {"short_description": short_description, "state": "Scheduled"}
    if assignment_group:
        params["assignment_group"] = assignment_group
    url = base_url + "?" + urllib.parse.urlencode(params)

    creds = f"{user}:{password}".encode("utf-8")
    auth_header = "Basic " + base64.b64encode(creds).decode("ascii")

    headers = {
        "Accept": "application/json",
        "Authorization": auth_header,
        "Content-Type": "application/json"
    }

    # Provide empty bytes to force POST with urllib
    req = urllib.request.Request(url, data=b"", headers=headers, method="POST")

    with urllib.request.urlopen(req) as resp:
        status = resp.getcode()
        body = resp.read().decode("utf-8")
        try:
            data = json.loads(body) if body else None
        except json.JSONDecodeError:
            data = body
        if debug:
            print(status)
            print(json.dumps(data, indent=2) if isinstance(data, (dict, list)) else data)
        return status, data

def update(snow_url, sys_id, user, password, state, debug=False):
    """
    Update an existing change identified by sys_id via a PATCH request.
    state: required string, one of "Implement", "Review", "Closed".
    Returns (status, data) where data is parsed JSON (or raw body on parse error).
    """
    if state not in ("Implement", "Review", "Closed"):
        raise ValueError("state must be one of: Implement, Review, Closed")

    fields = {"state": state}

    url = f"{snow_url}/api/sn_chg_rest/change/{sys_id}"

    creds = f"{user}:{password}".encode("utf-8")
    auth_header = "Basic " + base64.b64encode(creds).decode("ascii")

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": auth_header
    }

    payload = json.dumps(fields).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers=headers, method="PATCH")

    with urllib.request.urlopen(req) as resp:
        status = resp.getcode()
        body = resp.read().decode("utf-8")
        try:
            data = json.loads(body) if body else None
        except json.JSONDecodeError:
            data = body
        if debug:
            print(status)
            print(json.dumps(data, indent=2) if isinstance(data, (dict, list)) else data)
        return status, data

def close(snow_url, sys_id, user, password, result, debug=False):
    """
    Close an existing change identified by sys_id via a PATCH request.
    result: "successful" or "unsuccessful" - determines close_code and close_notes.
    Sends state="Closed" plus close_code and close_notes.
    Returns (status, data).
    """
    if result not in ("successful", "unsuccessful"):
        raise ValueError("result must be one of: successful, unsuccessful")

    if result == "successful":
        close_code = "successful"
        close_notes = "Change completed successfully"
    else:
        close_code = "unsuccessful"
        close_notes = "Change did not complete successfully"

    fields = {"state": "Closed", "close_code": close_code, "close_notes": close_notes}
    url = f"{snow_url}/api/sn_chg_rest/change/{sys_id}"

    creds = f"{user}:{password}".encode("utf-8")
    auth_header = "Basic " + base64.b64encode(creds).decode("ascii")

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": auth_header
    }

    payload = json.dumps(fields).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers=headers, method="PATCH")

    with urllib.request.urlopen(req) as resp:
        status = resp.getcode()
        body = resp.read().decode("utf-8")
        try:
            data = json.loads(body) if body else None
        except json.JSONDecodeError:
            data = body
        if debug:
            print(status)
            print(json.dumps(data, indent=2) if isinstance(data, (dict, list)) else data)
        return status, data

def main():
    debug = os.environ.get("DEBUG") == "true"
    snow_url = os.environ.get("SNOW_URL")
    user = os.environ.get("SNOW_USER")
    password = os.environ.get("SNOW_PASSWORD")

    parser = argparse.ArgumentParser(description="Create or update ServiceNow standard changes")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--create", action="store_true", help="Create a new standard change")
    group.add_argument("--update", action="store_true", help="Update an existing change")
    group.add_argument("--close", action="store_true", help="Close an existing change")
    parser.add_argument("--sys-id", help="sys_id of change to update/close (required with --update or --close)")
    parser.add_argument("--short-description", default="abcd", help="short description for create")

    # New CLI options for standard change and assignment group.
    parser.add_argument("--standard-change", help="standard change sys_id (required with --create)")
    parser.add_argument("--assignment-group", help="assignment group sys_id (required with --create)")

    # New --state argument for update; restrict allowed values
    parser.add_argument("--state", choices=["Implement", "Review", "Closed"],
                        help="state to set when updating (one of Implement, Review, Closed)")

    # New --result for close
    parser.add_argument("--result", choices=["successful", "unsuccessful"],
                        help="result for close (required with --close)")

    args = parser.parse_args()

    try:
        if args.update:
            if not args.sys_id:
                parser.error("--sys-id is required with --update")
            # require --state when updating
            if not args.state:
                parser.error("--state is required with --update")

            # If state is Closed require --result and call close()
            if args.state == "Closed":
                if not args.result:
                    parser.error("--result is required when --state Closed")
                status, data = close(snow_url, args.sys_id, user, password, result=args.result, debug=debug)
                if isinstance(data, dict):
                    print("UPDATE_SYS_ID=" + str(args.sys_id))
                    print("UPDATE_STATE=Closed")
                    print("UPDATE_RESULT=" + args.result)
                else:
                    print("UPDATE_RESPONSE:", data)
            else:
                try:
                    # pass selected state into update()
                    status, data = update(snow_url, args.sys_id, user, password, state=args.state, debug=debug)
                    # If update returns a response, print something useful
                    if isinstance(data, dict):
                        print("UPDATE_SYS_ID=" + str(args.sys_id))
                        print("UPDATE_STATE=" + args.state)
                    else:
                        print("UPDATE_RESPONSE:", data)
                except NotImplementedError as e:
                    print(e, file=sys.stderr)
                    sys.exit(2)
        elif args.close:
            # require sys-id and result when closing
            if not args.sys_id:
                parser.error("--sys-id is required with --close")
            if not args.result:
                parser.error("--result is required with --close")
            status, data = close(snow_url, args.sys_id, user, password, result=args.result, debug=debug)
            if isinstance(data, dict):
                print("CLOSE_SYS_ID=" + str(args.sys_id))
                print("CLOSE_RESULT=" + args.result)
            else:
                print("CLOSE_RESPONSE:", data)
        else:
            # default to create if --create or no flags
            # require CLI args (no environment fallback)
            snow_standard_change = args.standard_change
            snow_assignment_group = args.assignment_group

            # required when creating
            if not snow_standard_change:
                parser.error("--standard-change is required with --create")
            if not snow_assignment_group:
                parser.error("--assignment-group is required with --create")

            status, data = create(snow_url, snow_standard_change, snow_assignment_group,
                                  user, password, short_description=args.short_description, debug=debug)
            print("CHANGE_NUMBER=" + data["result"]["number"]["value"])
            print("CHANGE_SYS_ID=" + data["result"]["sys_id"]["value"])
    except urllib.error.HTTPError as e:
        print(e.code, e.read().decode("utf-8"), file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print("Request failed:", e.reason, file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
