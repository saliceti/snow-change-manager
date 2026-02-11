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

def send_request(url, method, user, password, payload=None, extra_headers=None):
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
        except json.JSONDecodeError:
            print("Error decoding JSON response:" + body)
            sys.exit(1)
        return status, data

def get_datetime(minutes=0):
    delta = timedelta(minutes=minutes)
    datetime_now = datetime.now()
    datetime_plus_delta = datetime_now + delta
    return datetime_plus_delta.strftime("%Y-%m-%d %H:%M:%S")

def create(snow_url, snow_standard_change, user, password, short_description):
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
    return send_request(url, "POST", user, password)

def update(snow_url, sys_id, user, password, state):
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
    return send_request(url, "PATCH", user, password, payload=fields)

def close(snow_url, sys_id, user, password, result):
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
    return send_request(url, "PATCH", user, password, payload=fields)

def get_by_sys_id(snow_url, sys_id, user, password):
    """
    Retrieve an existing change identified by sys_id.

    Uses:
      GET /api/sn_chg_rest/change/{sys_id}

    See ServiceNow Change Management API docs for details:
    https://www.servicenow.com/docs/r/api-reference/rest-apis/change-management-api.html

    Returns (status, data).
    """
    url = f"{snow_url}/api/sn_chg_rest/change/{sys_id}"
    return send_request(url, "GET", user, password)

def get_by_number(snow_url, number, user, password):
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
    return send_request(url, "GET", user, password)

def get_template_id(snow_url, user, password, name):
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
    return send_request(url, "GET", user, password)

def post_comment(snow_url, sys_id, user, password, comment):
    """
    Post a comment to a change request using the Table API.

    Uses:
      PATCH /api/now/table/change_request/{sys_id}

    See ServiceNow Table API docs for details:
    https://www.servicenow.com/docs/r/api-reference/rest-apis/c_TableAPI.html

    Returns (status, data).
    """
    url = f"{snow_url}/api/now/table/change_request/{sys_id}"
    payload = {"comments": comment}
    return send_request(url, "PATCH", user, password, payload=payload)

def main():
    snow_url = os.environ.get("SNOW_URL")
    user = os.environ.get("SNOW_USER")
    password = os.environ.get("SNOW_PASSWORD")

    parser = argparse.ArgumentParser(description="Create or update ServiceNow standard changes")
    parser.add_argument("--json", action="store_true", help="output API response as formatted JSON")
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

    # post-comment subcommand: post a comment to a change
    sp_post_comment = subparsers.add_parser("post-comment", help="Post a comment to a change request")
    sp_post_comment.add_argument("--sys-id", required=True, help="sys_id of change to comment on (required)")
    sp_post_comment.add_argument("--comment", required=True, help="comment text (required)")

    args = parser.parse_args()

    try:
        match args.command:
            case "create":
                if not args.json: print(f"Creating change from template {args.standard_change}...")
                status, data = create(snow_url, args.standard_change,
                                      user, password, short_description=args.short_description)
                result_type = "single_change"
            case "update":
                if not args.json: print(f"Updating change {args.sys_id} with state {args.state}...")
                if args.state == "Closed":
                    if not args.result:
                        parser.error("--result is required when --state Closed")
                    status, data = close(snow_url, args.sys_id, user, password, result=args.result)
                else:
                    status, data = update(snow_url, args.sys_id, user, password, state=args.state)
                result_type = "single_change"
            case "close":
                if not args.json: print(f"Closing change {args.sys_id} with result {args.result}...")
                status, data = close(snow_url, args.sys_id, user, password, result=args.result)
                result_type = "single_change"
            case "get":
                if args.sys_id:
                    if not args.json: print(f"Retrieving change with sys_id {args.sys_id}...")
                    status, data = get_by_sys_id(snow_url, args.sys_id, user, password)
                    result_type = "single_change"
                else:
                    if not args.json: print(f"Retrieving change with number {args.number}...")
                    status, data = get_by_number(snow_url, args.number, user, password)
                    result_type = "change_list"
            case "get-template-id":
                print(f"Retrieving template \"{args.name}\"...")
                status, data = get_template_id(snow_url, user, password, name=args.name)
                result_type = "template_list"
            case "post-comment":
                print(f"Posting comment...")
                status, data = post_comment(snow_url, args.sys_id, user, password, comment=args.comment)
                result_type = "table_item"
            case _:
                parser.error("unknown command")

        if status != 200:
            print(f"Error: Unexpected status code - {status}")
            sys.exit(1)
        else:
            if not args.json: print("The request was successful")

        if args.json:
            print(json.dumps(data, indent=2))
        else:
            match result_type:
                case "single_change":
                    print("CHANGE_NUMBER=" + data["result"]["number"]["value"])
                    print("CHANGE_SYS_ID=" + data["result"]["sys_id"]["value"])
                    print("CHANGE_STATE=" + data["result"]["state"]["display_value"])
                    print("CHANGE_SYS_UPDATED_ON=\"" + data["result"]["sys_updated_on"]["value"] + "\"")
                    print(f"CHANGE_LINK={snow_url}/now/nav/ui/classic/params/target/change_request.do?sys_id={data["result"]["sys_id"]["value"]}")
                case "change_list":
                    print("CHANGE_NUMBER=" + data["result"][0]["number"]["value"])
                    print("CHANGE_SYS_ID=" + data["result"][0]["sys_id"]["value"])
                    print("CHANGE_STATE=" + data["result"][0]["state"]["display_value"])
                    print("CHANGE_SYS_UPDATED_ON=\"" + data["result"][0]["sys_updated_on"]["value"] + "\"")
                    print(f"CHANGE_LINK={snow_url}/now/nav/ui/classic/params/target/change_request.do?sys_id={data["result"][0]["sys_id"]["value"]}")
                case "template_list":
                    print("TEMPLATE_ID=" + data["result"][0]["sys_id"]["value"])
                    print("TEMPLATE_NAME=\"" + args.name + "\"")
                    print(f"TEMPLATE_LINK={snow_url}/now/nav/ui/classic/params/target/std_change_record_producer.do?sys_id={data["result"][0]["sys_id"]["value"]}")
                case "table_item":
                    print("CHANGE_NUMBER=" + data["result"]["number"])
                    print("CHANGE_SYS_ID=" + data["result"]["sys_id"])
                    print("CHANGE_STATE=" + data["result"]["state"])
                    print("CHANGE_SYS_UPDATED_ON=\"" + data["result"]["sys_updated_on"] + "\"")
                    print(f"CHANGE_LINK={snow_url}/now/nav/ui/classic/params/target/change_request.do?sys_id={data["result"]["sys_id"]}")

    except urllib.error.HTTPError as e:
        print(e.code, e.read().decode("utf-8"), file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print("Request failed:", e.reason, file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()


# TEST1
