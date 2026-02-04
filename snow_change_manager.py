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
    params = {"short_description": short_description}
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

def update(snow_url, sys_id, user, password, debug=False, fields=None):
    """
    Update an existing change identified by sys_id.
    Not implemented yet; raise NotImplementedError so callers can handle it.
    """
    raise NotImplementedError("update not implemented yet")

def main():
    debug = os.environ.get("DEBUG") == "true"
    snow_url = os.environ.get("SNOW_URL")
    snow_standard_change = os.environ.get("SNOW_STANDARD_CHANGE")
    snow_assignment_group = os.environ.get("SNOW_ASSIGNMENT_GROUP")
    user = os.environ.get("SNOW_USER")
    password = os.environ.get("SNOW_PASSWORD")

    parser = argparse.ArgumentParser(description="Create or update ServiceNow standard changes")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--create", action="store_true", help="Create a new standard change")
    group.add_argument("--update", action="store_true", help="Update an existing change")
    parser.add_argument("--sys-id", help="sys_id of change to update (required with --update)")
    parser.add_argument("--short-description", default="abcd", help="short description for create")
    args = parser.parse_args()

    try:
        if args.update:
            if not args.sys_id:
                parser.error("--sys-id is required with --update")
            try:
                status, data = update(snow_url, args.sys_id, user, password, debug=debug)
                # If update returns a response, print something useful
                if isinstance(data, dict):
                    print("UPDATE_SYS_ID=" + str(args.sys_id))
                else:
                    print("UPDATE_RESPONSE:", data)
            except NotImplementedError as e:
                print(e, file=sys.stderr)
                sys.exit(2)
        else:
            # default to create if --create or no flags
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
