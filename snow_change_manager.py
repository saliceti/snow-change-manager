#!/usr/bin/env python

import base64
import json
import urllib.parse
import urllib.request
import urllib.error
import sys
import argparse
from datetime import datetime,timedelta


DEFAULT_ROUTES = {
    "create": {"method": "POST", "path": "/api/sn_chg_rest/change/standard/{template_id}"},
    "update": {"method": "PATCH", "path": "/api/sn_chg_rest/change/{sys_id}"},
    "close": {"method": "PATCH", "path": "/api/sn_chg_rest/change/{sys_id}"},
    "get_by_sys_id": {"method": "GET", "path": "/api/sn_chg_rest/change/{sys_id}"},
    "get_by_number": {"method": "GET", "path": "/api/sn_chg_rest/change"},
    "get_template_id": {"method": "GET", "path": "/api/sn_chg_rest/v1/change/standard/template"},
    "post_comment": {"method": "PATCH", "path": "/api/now/table/change_request/{sys_id}"},
}

CUSTOM_ROUTES = {
    "create": { "method": "POST", "path": "/api/x_nhsd_intstation/nhs_integration/std_change/{profile}/createStdChange/{template_id}"},
    "update": { "method": "PUT", "path": "/api/x_nhsd_intstation/nhs_integration/{profile}/updateStdChange/{number}"},
    "close": { "method": "PUT", "path": "/api/x_nhsd_intstation/nhs_integration/{profile}/updateStdChange/{number}"},
    "get_by_sys_id": { "method": "GET", "path": "/api/x_nhsd_intstation/nhs_integration/record/{profile}/getChangeRequest/{sys_id}"},
    "get_template_id": { "method": "GET", "path": "/api/x_nhsd_intstation/nhs_integration/record/{profile}/getStandardChgTemplateID"},
    "post_comment": { "method": "PUT", "path": "/api/x_nhsd_intstation/nhs_integration/{profile}/updateStdChange/{number}"},
    "get_by_number": { "method": "GET", "path": "/api/x_nhsd_intstation/nhs_integration/record/{profile}/getChangeRequest/{number}"}
}

# See https://www.servicenow.com/docs/r/it-service-management/change-management/c_ChangeStateModel.html
SNOW_STATES = {
    "New": -5,
    "Scheduled": -2,
    "Implement": -1,
    "Review": 0,
    "Closed": 3
}


def resolve_endpoint(custom, function_name, **params):
    routes = CUSTOM_ROUTES if custom else DEFAULT_ROUTES
    route = routes[function_name]
    return route["method"], route["path"].format(**params)

def get_basic_auth_header(user, password):
    creds = f"{user}:{password}".encode("utf-8")
    return "Basic " + base64.b64encode(creds).decode("ascii")

def validate_cli_arguments(parser, args):
    missing = []

    if not args.snow_host or not args.snow_host.strip():
        missing.append("--snow-host")

    if args.auth == "password":
        if not args.snow_user or not args.snow_user.strip():
            missing.append("--snow-user")
        if not args.snow_password or not args.snow_password.strip():
            missing.append("--snow-password")

    if args.auth == "oauth":
        if not args.client_id:
            missing.append("--client-id")
        if not args.client_secret:
            missing.append("--client-secret")

    if args.custom and (not args.profile or not args.profile.strip()):
        missing.append("--profile")

    if missing:
        parser.error("Missing required command line argument(s): " + ", ".join(missing))

def get_oauth_bearer_token(snow_url, client_id, client_secret):
    url = f"{snow_url}/oauth_token.do"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    payload = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    with urllib.request.urlopen(req) as resp:
        body = resp.read().decode("utf-8")
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError as exc:
            raise ValueError("OAuth token response is not valid JSON") from exc

    access_token = data.get("access_token") if isinstance(data, dict) else None
    if not access_token:
        raise ValueError("OAuth token response did not include access_token")

    return f"Bearer {access_token}"

def send_request(url, method, auth_header, payload=None, extra_headers=None):
    """
    Generic request helper. payload can be a dict (will be JSON-encoded), bytes or None.
    Returns (status, data) where data is parsed JSON when possible.
    """
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    headers["Authorization"] = auth_header

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


def extract_api_value(field, preferred_key="value"):
    if isinstance(field, dict):
        if preferred_key in field:
            return field.get(preferred_key)
        if "value" in field:
            return field.get("value")
        if "display_value" in field:
            return field.get("display_value")
    return field

def create(snow_url, snow_standard_change, auth_header, short_description, custom, profile):
    """
    Construct and POST a standard change using the provided parameters.

    Uses the ServiceNow "Standard Change" REST endpoint:
      POST /api/sn_chg_rest/change/standard/{template_id}

    See ServiceNow Change Management API docs for details:
    https://www.servicenow.com/docs/r/api-reference/rest-apis/change-management-api.html

    Returns (status, data) where data is parsed JSON (or raw body on parse error).
    """
    method, path = resolve_endpoint(
        custom,
        "create",
        template_id=snow_standard_change,
        profile=profile,
    )
    base_url = f"{snow_url}{path}"
    params = {
        "short_description": short_description,
        "state": SNOW_STATES["Scheduled"],
        # "state": "Scheduled",
        "start_date": get_datetime(),
        "end_date": get_datetime(60)
    }

    if custom:
        # Send data in the request body
        return send_request(base_url, method, auth_header, payload=params)
    else:
        url = base_url + "?" + urllib.parse.urlencode(params)
        # Send data in the request query string
        return send_request(url, method, auth_header)

def update(snow_url, number, auth_header, state, custom, profile):
    """
    Update an existing change identified by sys_id via a PATCH request.

    Uses the Change REST endpoint:
      PATCH /api/sn_chg_rest/change/{sys_id}
    to set the 'state' field.

    See ServiceNow Change Management API docs for details:
    https://www.servicenow.com/docs/r/api-reference/rest-apis/change-management-api.html

    Returns (status, data) where data is parsed JSON (or raw body on parse error).
    """

    method, path = resolve_endpoint(custom, "update", number=number, profile=profile)
    url = f"{snow_url}{path}"
    fields = {"state": SNOW_STATES[state]}
    return send_request(url, method, auth_header, payload=fields)

def review(snow_url, number, auth_header, result, custom, profile):
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

    method, path = resolve_endpoint(custom, "close", number=number, profile=profile)
    url = f"{snow_url}{path}"
    fields = {"state": SNOW_STATES["Review"], "close_code": close_code, "close_notes": close_notes}

    return send_request(url, method, auth_header, payload=fields)

def get_by_sys_id(snow_url, sys_id, auth_header, custom, profile):
    """
    Retrieve an existing change identified by sys_id. Only in Standard API.

    Uses:
      GET /api/sn_chg_rest/change/{sys_id}

    See ServiceNow Change Management API docs for details:
    https://www.servicenow.com/docs/r/api-reference/rest-apis/change-management-api.html

    Returns (status, data).
    """
    method, path = resolve_endpoint(custom, "get_by_sys_id", sys_id=sys_id, profile=profile)
    url = f"{snow_url}{path}"
    return send_request(url, method, auth_header)

def get_by_number(snow_url, number, auth_header, custom, profile):
    """
    Retrieve an existing change identified by number.

    Uses:
      GET /api/sn_chg_rest/change?sysparm_query=...

    Filters for the change matching the provided number (e.g., CHG0030052).

    See ServiceNow Change Management API docs for details:
    https://www.servicenow.com/docs/r/api-reference/rest-apis/change-management-api.html

    Returns (status, data).
    """
    method, path = resolve_endpoint(custom, "get_by_number", profile=profile, number=number)
    base_url = f"{snow_url}{path}"
    # query = f"number={urllib.parse.quote(number)}"
    # url = base_url + "?" + urllib.parse.urlencode({"sysparm_query": query})
    return send_request(base_url, method, auth_header)

def get_template_id(snow_url, auth_header, name, custom, profile):
    """
    Retrieve a standard change template by name.

    Uses:
      GET /api/sn_chg_rest/v1/change/standard/template?sysparm_query=...

    Filters for active templates matching the provided name.

    See ServiceNow Change Management API docs for details:
    https://www.servicenow.com/docs/r/api-reference/rest-apis/change-management-api.html

    Returns (status, data).
    """
    method, path = resolve_endpoint(custom, "get_template_id", profile=profile)
    base_url = f"{snow_url}{path}"
    query = f"active=true^name={name}"
    url = base_url + "?" + urllib.parse.urlencode({"sysparm_query": query})
    print(url)
    return send_request(url, method, auth_header)

def post_comment(snow_url, number, auth_header, comment, custom, profile):
    """
    Post a comment to a change request using the Table API.

    Uses:
      PATCH /api/now/table/change_request/{sys_id}

    See ServiceNow Table API docs for details:
    https://www.servicenow.com/docs/r/api-reference/rest-apis/c_TableAPI.html

    Returns (status, data).
    """
    method, path = resolve_endpoint(custom, "post_comment", profile=profile, number=number)
    url = f"{snow_url}{path}"
    payload = {"work_notes": comment}
    return send_request(url, method, auth_header, payload=payload)

def main():
    parser = argparse.ArgumentParser(
        description="Create or update ServiceNow standard changes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--auth", choices=["password", "oauth"], required=True,
                        help="authentication mode")
    parser.add_argument("--snow-host", help="ServiceNow instance host (required)")
    parser.add_argument("--snow-user", help="ServiceNow username (required with --auth password)")
    parser.add_argument("--snow-password", help="ServiceNow password (required with --auth password)")
    parser.add_argument("--client-id", help="OAuth client ID (required with --auth oauth)")
    parser.add_argument("--client-secret", help="OAuth client secret (required with --auth oauth)")
    parser.add_argument("--custom", action="store_true", help="use custom API endpoint mappings")
    parser.add_argument("--profile", help="profile ID (required with --custom)")
    parser.add_argument("--json", action="store_true", help="output API response as formatted JSON")
    parser.add_argument("--verbose", action="store_true", help="print progress messages")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create subcommand
    sp_create = subparsers.add_parser("create", help="Create a new standard change")
    sp_create.add_argument("--standard-change", required=True, help="standard change sys_id (required)")
    sp_create.add_argument("--short-description", required=True, help="short description for create")

    # update subcommand
    sp_update = subparsers.add_parser("update", help="Update an existing change")
    sp_update.add_argument("--sys-id", help="sys_id of change to update (required for standard SeviceNow API)")
    sp_update.add_argument("--number", help="number of change to retrieve e.g. CHG0030052 (required for NHS custom API)")
    sp_update.add_argument("--state", choices=["Implement"], required=True,
                           help="state to set when updating (one of Implement)")
    sp_update.add_argument("--result", choices=["successful", "unsuccessful"],
                           help="result for close (required when state is Closed)")

    # review subcommand
    sp_review = subparsers.add_parser("review", help="Progress an existing change to Review")
    sp_review.add_argument("--number", required=True, help="Number of change to review e.g CHG0030052 (required)")
    sp_review.add_argument("--result", choices=["successful", "unsuccessful"], required=True,
                          help="result for close (required)")

    # get subcommand: retrieve a change
    sp_get = subparsers.add_parser("get", help="Get an existing change by sys_id (only for standard API) or number")
    group = sp_get.add_mutually_exclusive_group(required=True)
    group.add_argument("--sys-id", help="sys_id of change to retrieve")
    group.add_argument("--number", help="number of change to retrieve (e.g., CHG0030052)")

    # get-template-id subcommand: retrieve template ID by name
    sp_get_template = subparsers.add_parser("get-template-id", help="Get a standard change template ID by name")
    sp_get_template.add_argument("--name", required=True, help="template name (required)")

    # post-comment subcommand: post a comment to a change
    sp_post_comment = subparsers.add_parser("post-comment", help="Post a comment to a change request")
    sp_post_comment.add_argument("--number", required=True, help="Number of change to comment on e.g CHG0030052 (required)")
    sp_post_comment.add_argument("--comment", required=True, help="comment text (required)")

    args = parser.parse_args()
    validate_cli_arguments(parser, args)
    snow_url = f"https://{args.snow_host.strip()}"

    try:
        if args.auth == "password":
            user = args.snow_user.strip()
            password = args.snow_password.strip()
            auth_header = get_basic_auth_header(user, password)
        else:
            auth_header = get_oauth_bearer_token(snow_url, args.client_id, args.client_secret)

        match args.command:
            case "create":
                if args.verbose: print(f"Creating change from template {args.standard_change}...")
                status, data = create(snow_url, args.standard_change,
                                      auth_header, short_description=args.short_description, custom=args.custom, profile=args.profile)
                result_type = "single_change"
            case "update":
                # The NHS custom API looks up a change by number
                if args.custom and not args.number:
                    parser.error("--number is required when using --custom")
                # The ServiceNow standard API looks up a change by sys_id
                if not args.custom and not args.sys_id:
                    parser.error("--sys-id is required when not using --custom")
                if args.verbose: print(f"Updating change {args.sys_id} with state {args.state}...")
                status, data = update(snow_url, args.number, auth_header, state=args.state, custom=args.custom, profile=args.profile)
                result_type = "single_change"
            case "review":
                if args.verbose: print(f"Progressing change {args.number} to Review with result {args.result}...")
                status, data = review(snow_url, args.number, auth_header, result=args.result, custom=args.custom, profile=args.profile)
                result_type = "single_change"
            case "get":
                if args.custom and not args.number:
                    parser.error("--number is required when using --custom")
                if args.custom and args.sys_id:
                    parser.error("--sys-id cannot be used when using --custom, use --number only")
                if args.sys_id:
                    if args.verbose: print(f"Retrieving change with sys_id {args.sys_id}...")
                    status, data = get_by_sys_id(snow_url, args.sys_id, auth_header, custom=args.custom, profile=args.profile)
                    result_type = "single_change"
                else:
                    if args.verbose: print(f"Retrieving change with number {args.number}...")
                    status, data = get_by_number(snow_url, args.number, auth_header, profile=args.profile, custom=args.custom)
                    if args.custom:
                        result_type = "single_change"
                    else:
                        result_type = "change_list"
            case "get-template-id":
                if args.verbose: print(f"Retrieving template \"{args.name}\"...")
                status, data = get_template_id(
                    snow_url,
                    auth_header,
                    name=args.name,
                    custom=args.custom,
                    profile=args.profile,
                )
                result_type = "template_list"
            case "post-comment":
                if args.verbose: print(f"Posting comment...")
                status, data = post_comment(snow_url, args.number, auth_header, comment=args.comment, custom=args.custom, profile=args.profile)
                result_type = "table_item"
            case _:
                parser.error("unknown command")

        if status != 200:
            print(f"Error: Unexpected status code - {status}")
            sys.exit(1)
        else:
            if args.verbose: print("The request was successful")

        if args.json:
            print(json.dumps(data, indent=2))
        else:
            match result_type:
                case "single_change":
                    change_number = extract_api_value(data["result"].get("number"))
                    change_sys_id = extract_api_value(data["result"].get("sys_id"))
                    change_state = extract_api_value(data["result"].get("state"), preferred_key="display_value")
                    print("CHANGE_NUMBER=" + str(change_number))
                    print("CHANGE_SYS_ID=" + str(change_sys_id))
                    print("CHANGE_STATE=" + str(change_state))
                    print(f"CHANGE_LINK={snow_url}/now/nav/ui/classic/params/target/change_request.do?sys_id={change_sys_id}")
                case "change_list":
                    print("CHANGE_NUMBER=" + data["result"][0]["number"]["value"])
                    print("CHANGE_SYS_ID=" + data["result"][0]["sys_id"]["value"])
                    print("CHANGE_STATE=" + data["result"][0]["state"]["display_value"])
                    print(f"CHANGE_LINK={snow_url}/now/nav/ui/classic/params/target/change_request.do?sys_id={data['result'][0]['sys_id']['value']}")
                case "template_list":
                    template_id = extract_api_value(data["result"][0].get("sys_id"))
                    print("TEMPLATE_ID=" + str(template_id))
                    print("TEMPLATE_NAME=\"" + args.name + "\"")
                    print(f"TEMPLATE_LINK={snow_url}/now/nav/ui/classic/params/target/std_change_record_producer.do?sys_id={template_id}")
                case "table_item":
                    print("CHANGE_NUMBER=" + data["result"]["number"])
                    print("CHANGE_SYS_ID=" + data["result"]["sys_id"])
                    print("CHANGE_STATE=" + data["result"]["state"])
                    print(f"CHANGE_LINK={snow_url}/now/nav/ui/classic/params/target/change_request.do?sys_id={data['result']['sys_id']}")

    except urllib.error.HTTPError as e:
        print(e.code, e.read().decode("utf-8"), file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print("Request failed:", e.reason, file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()


# TEST123
