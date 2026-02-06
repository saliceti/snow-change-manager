#!/usr/bin/env python

import os
import base64
import json
import urllib.parse
import urllib.request
import urllib.error
import sys
import argparse
from datetime import datetime,timedelta

def _auth_header(user, password):
    creds = f"{user}:{password}".encode("utf-8")
    return "Basic " + base64.b64encode(creds).decode("ascii")

def send_request(url, method, user, password, payload=None, extra_headers=None, debug=False):
    """
    Generic request helper. payload can be a dict (will be JSON-encoded), bytes or None.
    Returns (status, data) where data is parsed JSON when possible.
    """
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    headers["Authorization"] = _auth_header(user, password)

    if isinstance(payload, dict):
        data = json.dumps(payload).encode("utf-8")
    else:
        data = payload  # bytes or None

    # For POST with empty body data should be b"" to enforce POST
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        status = resp.getcode()
        body = resp.read().decode("utf-8")
        try:
            data = json.loads(body) if body else None

            if debug:
                print(f"RESPONSE_STATUS={status}")
                print("RESPONSE=" + json.dumps(data, indent=2))
        except json.JSONDecodeError:
            print("Error decoding JSON response:" + body)
            sys.exit(1)
        return status, data

def get_datetime(minutes=0):
    delta = timedelta(minutes=minutes)
    datetime_now = datetime.now()
    datetime_plus_delta = datetime_now + delta
    return datetime_plus_delta.strftime("%Y-%m-%d %H:%M:%S")

def create(snow_url, snow_standard_change, user, password,
           short_description="abcd", debug=False):
    """
    Construct and POST a standard change using the provided parameters.

    Uses the ServiceNow "Standard Change" REST endpoint:
      POST /api/sn_chg_rest/change/standard/{standard_change_sys_id}

    See ServiceNow Change Management API docs for details:
    https://www.servicenow.com/docs/r/api-reference/rest-apis/change-management-api.html

    Returns (status, data) where data is parsed JSON (or raw body on parse error).
    """
    base_url = f"{snow_url}/api/sn_chg_rest/change/standard/{snow_standard_change}"
    params = {
        "short_description": short_description,
        "state": "Scheduled",
        "start_date": get_datetime(),
        "end_date": get_datetime(60)
    }
    url = base_url + "?" + urllib.parse.urlencode(params)

    # Provide empty payload to force POST
    return send_request(url, "POST", user, password, debug=debug)

def update(snow_url, sys_id, user, password, state, debug=False):
    """
    Update an existing change identified by sys_id via a PATCH request.

    Uses the Change REST endpoint:
      PATCH /api/sn_chg_rest/change/{sys_id}
    to set the 'state' field.

    See ServiceNow Change Management API docs for details:
    https://www.servicenow.com/docs/r/api-reference/rest-apis/change-management-api.html

    Returns (status, data) where data is parsed JSON (or raw body on parse error).
    """
    if state not in ("Implement", "Review", "Closed"):
        raise ValueError("state must be one of: Implement, Review, Closed")

    url = f"{snow_url}/api/sn_chg_rest/change/{sys_id}"
    fields = {"state": state}
    return send_request(url, "PATCH", user, password, payload=fields, debug=debug)

def close(snow_url, sys_id, user, password, result, debug=False):
    """
    Close an existing change identified by sys_id via a PATCH request.

    Sends state="Closed" plus close_code and close_notes to:
      PATCH /api/sn_chg_rest/change/{sys_id}

    See ServiceNow Change Management API docs for details:
    https://www.servicenow.com/docs/r/api-reference/rest-apis/change-management-api.html

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

    url = f"{snow_url}/api/sn_chg_rest/change/{sys_id}"
    fields = {"state": "Closed", "close_code": close_code, "close_notes": close_notes}
    return send_request(url, "PATCH", user, password, payload=fields, debug=debug)

def get_by_sys_id(snow_url, sys_id, user, password, debug=False):
    """
    Retrieve an existing change identified by sys_id.

    Uses:
      GET /api/sn_chg_rest/change/{sys_id}

    See ServiceNow Change Management API docs for details:
    https://www.servicenow.com/docs/r/api-reference/rest-apis/change-management-api.html

    Returns (status, data).
    """
    url = f"{snow_url}/api/sn_chg_rest/change/{sys_id}"
    return send_request(url, "GET", user, password, debug=debug)

def get_by_number(snow_url, number, user, password, debug=False):
    """
    Retrieve an existing change identified by number.

    Uses:
      GET /api/sn_chg_rest/change?sysparm_query=...

    Filters for the change matching the provided number (e.g., CHG0030052).

    See ServiceNow Change Management API docs for details:
    https://www.servicenow.com/docs/r/api-reference/rest-apis/change-management-api.html

    Returns (status, data).
    """
    base_url = f"{snow_url}/api/sn_chg_rest/change"
    query = f"number={urllib.parse.quote(number)}"
    url = base_url + "?" + urllib.parse.urlencode({"sysparm_query": query})
    return send_request(url, "GET", user, password, debug=debug)

def get_template_id(snow_url, user, password, name, debug=False):
    """
    Retrieve a standard change template by name.

    Uses:
      GET /api/sn_chg_rest/v1/change/standard/template?sysparm_query=...

    Filters for active templates matching the provided name.

    See ServiceNow Change Management API docs for details:
    https://www.servicenow.com/docs/r/api-reference/rest-apis/change-management-api.html

    Returns (status, data).
    """
    base_url = f"{snow_url}/api/sn_chg_rest/v1/change/standard/template"
    query = f"active=true^name={name}"
    url = base_url + "?" + urllib.parse.urlencode({"sysparm_query": query})
    return send_request(url, "GET", user, password, debug=debug)

def main():
    debug = os.environ.get("DEBUG") == "true"
    snow_url = os.environ.get("SNOW_URL")
    user = os.environ.get("SNOW_USER")
    password = os.environ.get("SNOW_PASSWORD")

    parser = argparse.ArgumentParser(description="Create or update ServiceNow standard changes")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create subcommand
    sp_create = subparsers.add_parser("create", help="Create a new standard change")
    sp_create.add_argument("--standard-change", required=True, help="standard change sys_id (required)")
    sp_create.add_argument("--short-description", required=True, help="short description for create")

    # update subcommand
    sp_update = subparsers.add_parser("update", help="Update an existing change")
    sp_update.add_argument("--sys-id", required=True, help="sys_id of change to update (required)")
    sp_update.add_argument("--state", choices=["Implement", "Review", "Closed"], required=True,
                           help="state to set when updating (one of Implement, Review, Closed)")
    sp_update.add_argument("--result", choices=["successful", "unsuccessful"],
                           help="result for close (required when state is Closed)")

    # close subcommand
    sp_close = subparsers.add_parser("close", help="Close an existing change")
    sp_close.add_argument("--sys-id", required=True, help="sys_id of change to close (required)")
    sp_close.add_argument("--result", choices=["successful", "unsuccessful"], required=True,
                          help="result for close (required)")

    # get subcommand: retrieve a change
    sp_get = subparsers.add_parser("get", help="Get an existing change by sys_id or number")
    group = sp_get.add_mutually_exclusive_group(required=True)
    group.add_argument("--sys-id", help="sys_id of change to retrieve")
    group.add_argument("--number", help="number of change to retrieve (e.g., CHG0030052)")

    # get-template-id subcommand: retrieve template ID by name
    sp_get_template = subparsers.add_parser("get-template-id", help="Get a standard change template ID by name")
    sp_get_template.add_argument("--name", required=True, help="template name (required)")

    args = parser.parse_args()

    try:
        match args.command:
            case "create":
                status, data = create(snow_url, args.standard_change,
                                      user, password, short_description=args.short_description, debug=debug)
            case "update":
                if args.state == "Closed":
                    if not args.result:
                        parser.error("--result is required when --state Closed")
                    status, data = close(snow_url, args.sys_id, user, password, result=args.result, debug=debug)
                else:
                    status, data = update(snow_url, args.sys_id, user, password, state=args.state, debug=debug)
            case "close":
                status, data = close(snow_url, args.sys_id, user, password, result=args.result, debug=debug)
            case "get":
                if args.sys_id:
                    status, data = get_by_sys_id(snow_url, args.sys_id, user, password, debug=debug)
                else:
                    status, data = get_by_number(snow_url, args.number, user, password, debug=debug)
            case "get-template-id":
                status, data = get_template_id(snow_url, user, password, name=args.name, debug=debug)
            case _:
                parser.error("unknown command")

        if status != 200:
            print(f"Error: Unexpected status code - {status}")
            sys.exit(1)

        if args.command == "get-template-id":
            print("TEMPLATE_ID=" + data["result"][0]["sys_id"]["value"])
            print("TEMPLATE_NAME=\"" + args.name + "\"")
        else:
            if isinstance(data["result"], list):
                # get() has a filter in the query and return a list of 1 single change
                change_data = data["result"][0]
            else:
                # post and patch actions return the single change
                change_data = data["result"]
            print("CHANGE_NUMBER=" + change_data["number"]["value"])
            print("CHANGE_SYS_ID=" + change_data["sys_id"]["value"])
            print("CHANGE_STATE=" + change_data["state"]["display_value"])
            print("CHANGE_SYS_UPDATED_ON=\"" + change_data["sys_updated_on"]["value"] + "\"")

    except urllib.error.HTTPError as e:
        print(e.code, e.read().decode("utf-8"), file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print("Request failed:", e.reason, file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
