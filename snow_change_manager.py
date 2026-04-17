#!/usr/bin/env python

import base64
import json
import urllib.parse
import urllib.request
import urllib.error
import sys
import argparse
from datetime import datetime, timedelta

ARGS_DESCRIPTION = """
Create or update ServiceNow standard changes

General usage:
    ./snow_change_manager.py <global arguments> <command> <command arguments>
Example:
    ./snow_change_manager.py --auth oauth --client-id abcd123 --client-secret abc234 \\
        create --standard-change abc345 --short-description "Deploy version 123"

For help with commands:
    ./snow_change_manager.py <command> --help
Example:
    ./snow_change_manager.py create --help
"""

DEFAULT_ROUTES = {
    "create": {
        "method": "POST",
        "path": "/api/sn_chg_rest/change/standard/{template_id}"},
    "get_by_number": {
        "method": "GET",
        "path": "/api/sn_chg_rest/change"},
    "get_template_id": {
        "method": "GET",
        "path": "/api/sn_chg_rest/change/standard/template"},
    "post_comment": {
        "method": "PATCH",
        "path": "/api/now/table/change_request/{sys_id}"},
    "update": {
        "method": "PATCH",
        "path": "/api/sn_chg_rest/change/{sys_id}"},
}

CUSTOM_ROUTES = {
    "create": {
        "method": "POST",
        "path": "/api/x_nhsd_intstation/nhs_integration/std_change/{profile}/createStdChange/{template_id}"},
    "get_by_number": {
        "method": "GET",
        "path": "/api/x_nhsd_intstation/nhs_integration/record/{profile}/getChangeRequest/{number}"},
    "get_template_id": {
        "method": "GET",
        "path": "/api/x_nhsd_intstation/nhs_integration/record/{profile}/getStandardChgTemplateID"},
    "post_comment": {
        "method": "PUT",
        "path": "/api/x_nhsd_intstation/nhs_integration/{profile}/updateStdChange/{number}"},
    "update": {
        "method": "PUT",
        "path": "/api/x_nhsd_intstation/nhs_integration/{profile}/updateStdChange/{number}"},
}

# See
# https://www.servicenow.com/docs/r/it-service-management/change-management/c_ChangeStateModel.html
SNOW_STATES = {
    "New": -5,
    "Scheduled": -2,
    "Implement": -1,
    "Review": 0,
    "Closed": 3
}


def resolve_endpoint(custom, function_name, **params):
    """
    Resolve API endpoint to accomodate the standard ServiceNow API and the NHS custom API endpoints.
    Returns HTTP verb and path.
    """

    routes = CUSTOM_ROUTES if custom else DEFAULT_ROUTES
    route = routes[function_name]
    return route["method"], route["path"].format(**params)


def get_basic_auth_header(user, password):
    """
    Create the Authentication header value for HTTP basic auth
    Requires ServiceNow username and password
    """

    creds = f"{user}:{password}".encode("utf-8")
    return "Basic " + base64.b64encode(creds).decode("ascii")


def validate_cli_arguments(parser, args):
    """
    Validate the combinations of command line arguments for the ones not directly covered by the parser.
    """

    missing = []

    if not args.snow_host:
        missing.append("--snow-host")

    if args.auth == "password":
        if not args.snow_user:
            missing.append("--snow-user")
        if not args.snow_password:
            missing.append("--snow-password")

    if args.auth == "oauth":
        if not args.client_id:
            missing.append("--client-id")
        if not args.client_secret:
            missing.append("--client-secret")

    if args.custom and not args.profile:
        missing.append("--profile")

    if missing:
        parser.error(
            "Missing required command line argument(s): " +
            ", ".join(missing))


def get_oauth_bearer_token(snow_url, client_id, client_secret):
    """
    When using oauth authentication, request the bearer token. It is then used in any API request in the Authentication header.
    It is valid for 30 min.
    Requires API client id and secret.

    See: https://nhsdigitallive.service-now.com/nhs_digital?id=kb_article_view&sys_kb_id=cbaafe453b7cfe1067201da985e45a75
    """

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

    req = urllib.request.Request(
        url,
        data=payload,
        headers=headers,
        method="POST")
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

    headers = {"Accept": "application/json",
               "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    headers["Authorization"] = auth_header

    if isinstance(payload, dict):
        data = json.dumps(payload).encode("utf-8")
    else:
        data = payload  # bytes or None

    req = urllib.request.Request(
        url, data=data, headers=headers, method=method)
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
    """
    Generates the date/time string minutes into the future
    """
    
    delta = timedelta(minutes=minutes)
    datetime_now = datetime.now()
    datetime_plus_delta = datetime_now + delta
    return datetime_plus_delta.strftime("%Y-%m-%d %H:%M:%S")


def get_sys_id_if_required(snow_url, number, auth_header, custom, profile):
    """
    Use the change number to retrieve the change sys_id.
    Required for the standard API endpoints.
    The NHS custom API takes the change number as argument. In this case sys_is empty and ignored.
    """

    sys_id = ""
    if not custom:
        status, data = get_by_number(
            snow_url=snow_url, number=number, auth_header=auth_header, custom=custom, profile=profile)
        if status != 200:
            print(f"Error: Unexpected status code - {status}")
            sys.exit(1)
        sys_id = data["result"][0]["sys_id"]["value"]
    return sys_id


def create(
        snow_url,
        snow_standard_change,
        auth_header,
        short_description,
        custom,
        profile):
    """
    Create a standard change from a template with a customised short description.
    It is scheduled immediately.

    Standard ServiceNow API:
        https://www.servicenow.com/docs/r/api-reference/rest-apis/change-management-api.html
    Endpoint:
        POST /api/sn_chg_rest/change/standard/{template_id}

    NHS custom API:
        https://nhsdigitallive.service-now.com/nhs_digital?id=kb_article_view&sys_kb_id=9611a0a2c30c4310f56ef73d0501318d
    Endpoint:
        POST /api/x_nhsd_intstation/nhs_integration/std_change/{profile}/createStdChange/{template_id}
    The parameters are sent in the request body as opposed to the query string in the standard API.

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


def implement(snow_url, number, auth_header, custom, profile):
    """
    Update an existing change identified by the change number. Update the state to "Implement".

    Standard ServiceNow API:
        https://www.servicenow.com/docs/r/api-reference/rest-apis/change-management-api.html
    Endpoint:
        PATCH /api/sn_chg_rest/change/{sys_id}
    Uses get_sys_id_if_required() and the change number to get sys_id.

    NHS custom API:
        https://nhsdigitallive.service-now.com/nhs_digital?id=kb_article_view&sys_kb_id=f3783a8d3b3cfe1067201da985e45ab3
    Endpoint:
        PUT /api/x_nhsd_intstation/nhs_integration/{profile}/updateStdChange/{change number}

    Returns (status, data) where data is parsed JSON (or raw body on parse error).
    """

    sys_id = get_sys_id_if_required(
        snow_url, number, auth_header, custom, profile)
    method, path = resolve_endpoint(
        custom, "update", number=number, sys_id=sys_id, profile=profile)
    url = f"{snow_url}{path}"
    fields = {"state": SNOW_STATES["Implement"]}
    return send_request(url, method, auth_header, payload=fields)


def review(snow_url, number, auth_header, result, custom, profile):
    """
    Update an existing change state to review and set the closure information.

    Standard ServiceNow API:
        https://www.servicenow.com/docs/r/api-reference/rest-apis/change-management-api.html
    Endpoint:
      PATCH /api/sn_chg_rest/change/{sys_id}
    Uses get_sys_id_if_required() and the change number to get sys_id.

    NHS custom API:
        https://nhsdigitallive.service-now.com/nhs_digital?id=kb_article_view&sys_kb_id=f3783a8d3b3cfe1067201da985e45ab3
    Endpoint:
        PUT /api/x_nhsd_intstation/nhs_integration/{profile}/updateStdChange/{change number}

    Returns (status, data) where data is parsed JSON (or raw body on parse error).
    """

    if result not in ("successful", "unsuccessful"):
        raise ValueError("result must be one of: successful, unsuccessful")

    if result == "successful":
        close_code = "successful"
        close_notes = "Change completed successfully"
    else:
        close_code = "unsuccessful"
        close_notes = "Change did not complete successfully"

    sys_id = get_sys_id_if_required(
        snow_url, number, auth_header, custom, profile)
    method, path = resolve_endpoint(
        custom, "update", number=number, sys_id=sys_id, profile=profile)
    url = f"{snow_url}{path}"
    fields = {
        "state": SNOW_STATES["Review"],
        "close_code": close_code,
        "close_notes": close_notes}

    return send_request(url, method, auth_header, payload=fields)


def get_by_number(snow_url, number, auth_header, custom, profile):
    """
    Retrieve an existing change identified by number.

    Standard ServiceNow API:
        https://www.servicenow.com/docs/r/api-reference/rest-apis/change-management-api.html
    Endpoint:
        GET /api/sn_chg_rest/change?sysparm_query=...

    NHS custom API:
        Doc TBC
    Endpoint:
        /api/x_nhsd_intstation/nhs_integration/record/{profile}/getChangeRequest/{change number}

    Returns (status, data) where data is parsed JSON (or raw body on parse error).
    """

    method, path = resolve_endpoint(
        custom, "get_by_number", profile=profile, number=number)
    base_url = f"{snow_url}{path}"
    query = f"number={urllib.parse.quote(number)}"
    url = base_url + "?" + urllib.parse.urlencode({"sysparm_query": query})
    if custom:
        return send_request(base_url, method, auth_header)
    else:
        return send_request(url, method, auth_header)


def get_template_id(snow_url, auth_header, name, custom, profile):
    """
    Retrieve a standard change template id by name.

    Standard ServiceNow API:
        https://www.servicenow.com/docs/r/api-reference/rest-apis/change-management-api.html
    Endpoint:
        GET /api/sn_chg_rest/change/standard/template?sysparm_query=active=true^name={name}

    NHS custom API:
        https://nhsdigitallive.service-now.com/nhs_digital?id=kb_article_view&sys_kb_id=b42ab2053b7cfe1067201da985e45af3
    Endpoint:
        GET /api/x_nhsd_intstation/nhs_integration/record/{profile}/getStandardChgTemplateID

    Returns (status, data) where data is parsed JSON (or raw body on parse error).
    """

    method, path = resolve_endpoint(custom, "get_template_id", profile=profile)
    base_url = f"{snow_url}{path}"
    query = f"active=true^name={name}"
    url = base_url + "?" + urllib.parse.urlencode({"sysparm_query": query})
    return send_request(url, method, auth_header)


def post_comment(snow_url, number, auth_header, comment, custom, profile):
    """
    Post a work note to a change. The work note is a non publicly visible comment.
    The change displays all works notes with their author, ordered by date.

    Standard ServiceNow API:
        https://www.servicenow.com/docs/r/api-reference/rest-apis/c_TableAPI.html
    Endpoint:
      PATCH /api/now/table/change_request/{sys_id}
    Uses get_sys_id_if_required() and the change number to get sys_id.

    NHS custom API:
        https://nhsdigitallive.service-now.com/nhs_digital?id=kb_article_view&sys_kb_id=f3783a8d3b3cfe1067201da985e45ab3
    Endpoint:
        PUT /api/x_nhsd_intstation/nhs_integration/{profile}/updateStdChange/{change number}

    Returns (status, data) where data is parsed JSON (or raw body on parse error).
    """

    sys_id = get_sys_id_if_required(
        snow_url, number, auth_header, custom, profile)
    method, path = resolve_endpoint(
        custom, "post_comment", profile=profile, number=number, sys_id=sys_id)
    url = f"{snow_url}{path}"
    payload = {"work_notes": comment}
    return send_request(url, method, auth_header, payload=payload)


def main():
    parser = argparse.ArgumentParser(
        description=ARGS_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--auth", choices=["password", "oauth"], required=True,
                        help="authentication mode (required)")
    parser.add_argument(
        "--snow-host",
        help="ServiceNow instance host (required)")
    parser.add_argument(
        "--snow-user",
        help="ServiceNow username (required with --auth password)")
    parser.add_argument(
        "--snow-password",
        help="ServiceNow password (required with --auth password)")
    parser.add_argument(
        "--client-id",
        help="OAuth client ID (required with --auth oauth)")
    parser.add_argument(
        "--client-secret",
        help="OAuth client secret (required with --auth oauth)")
    parser.add_argument(
        "--custom",
        action="store_true",
        help="use custom API endpoint mappings")
    parser.add_argument(
        "--profile",
        help="profile ID (required with --custom)")
    parser.add_argument(
        "--json",
        action="store_true",
        help="output API response as formatted JSON")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="print progress messages")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create subcommand
    sp_create = subparsers.add_parser(
        "create", help="Create a new standard change")
    sp_create.add_argument(
        "--standard-change",
        required=True,
        help="standard change sys_id (required)")
    sp_create.add_argument(
        "--short-description",
        required=True,
        help="short description for create (required)")

    # implement subcommand
    sp_implement = subparsers.add_parser(
        "implement", help="Update change state to Implement")
    sp_implement.add_argument(
        "--number",
        required=True,
        help="Change number e.g. CHG0030052 (required)")

    # review subcommand
    sp_review = subparsers.add_parser(
        "review", help="Update change state to Review")
    sp_review.add_argument(
        "--number",
        required=True,
        help="Change number e.g CHG0030052 (required)")
    sp_review.add_argument(
        "--result",
        choices=[
            "successful",
            "unsuccessful"],
        required=True,
        help="result for close (required)")

    # get subcommand: retrieve a change
    sp_get = subparsers.add_parser(
        "get",
        help="Get an existing change by sys_id (only for standard API) or number")
    sp_get.add_argument(
        "--number",
        required=True,
        help="Change number e.g. CHG0030052 (required)")

    # get-template-id subcommand: retrieve template ID by name
    sp_get_template = subparsers.add_parser(
        "get-template-id",
        help="Get a standard change template ID by name")
    sp_get_template.add_argument(
        "--name",
        required=True,
        help="template name (required)")

    # post-comment subcommand: post a comment to a change
    sp_post_comment = subparsers.add_parser(
        "post-comment", help="Post a comment to a change request")
    sp_post_comment.add_argument(
        "--number",
        required=True,
        help="Change number on e.g CHG0030052 (required)")
    sp_post_comment.add_argument(
        "--comment",
        required=True,
        help="comment text (required)")

    args = parser.parse_args()
    validate_cli_arguments(parser, args)
    snow_url = f"https://{args.snow_host.strip()}"

    try:
        if args.auth == "password":
            user = args.snow_user.strip()
            password = args.snow_password.strip()
            auth_header = get_basic_auth_header(user, password)
        else:
            auth_header = get_oauth_bearer_token(
                snow_url, args.client_id, args.client_secret)

        match args.command:
            case "create":
                if args.verbose: print(f"Creating change from template {args.standard_change}...")
                status, data = create(snow_url, args.standard_change,
                                      auth_header, short_description=args.short_description, custom=args.custom, profile=args.profile)
                result_type = "single_change"
            case "implement":
                if args.verbose: print(f"Updating change {args.number} state to Implement...")
                status, data = implement(snow_url, args.number, auth_header, custom=args.custom, profile=args.profile)
                result_type = "single_change"
            case "review":
                if args.verbose:
                    print(
                        f"Updating change {
                            args.number} state to Review with result {
                            args.result}...")
                status, data = review(snow_url, args.number, auth_header,
                                      result=args.result, custom=args.custom, profile=args.profile)
                result_type = "single_change"
            case "get":
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
                print(data)
            case _:
                parser.error("unknown command")

    except urllib.error.HTTPError as e:
        print(e.code, e.read().decode("utf-8"), file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print("Request failed:", e.reason, file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    if status != 200:
        print(f"Error: Unexpected status code - {status}")
        sys.exit(1)

    if args.verbose: print("The request was successful")

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        match result_type:
            case "single_change":
                change_number = data["result"]["number"] if args.custom else data["result"]["number"]["value"]
                change_sys_id = data["result"]["sys_id"] if args.custom else data["result"]["sys_id"]["value"]
                change_state = data["result"]["state"] if args.custom else data["result"]["state"]["display_value"]
                print("CHANGE_NUMBER=" + change_number)
                print("CHANGE_SYS_ID=" + change_sys_id)
                print("CHANGE_STATE=" + change_state)
                print(
                    f"CHANGE_LINK={snow_url}/now/nav/ui/classic/params/target/change_request.do?sys_id={change_sys_id}")
            case "change_list":
                print("CHANGE_NUMBER=" + data["result"][0]["number"]["value"])
                print("CHANGE_SYS_ID=" + data["result"][0]["sys_id"]["value"])
                print(
                    "CHANGE_STATE=" +
                    data["result"][0]["state"]["display_value"])
                print(
                    f"CHANGE_LINK={snow_url}/now/nav/ui/classic/params/target/change_request.do?sys_id={
                        data['result'][0]['sys_id']['value']}")
            case "template_list":
                template_id = data["result"][0].get(
                    "sys_id") if args.custom else data["result"][0]["sys_id"]["value"]
                print("TEMPLATE_ID=" + data["result"][0]["sys_id"]["value"])
                print("TEMPLATE_NAME=\"" + args.name + "\"")
                print(
                    f"TEMPLATE_LINK={snow_url}/now/nav/ui/classic/params/target/std_change_record_producer.do?sys_id={template_id}")
            case "table_item":
                print("CHANGE_NUMBER=" + data["result"]["number"])
                print("CHANGE_SYS_ID=" + data["result"]["sys_id"])
                print("CHANGE_STATE=" + data["result"]["state"])
                print(
                    f"CHANGE_LINK={snow_url}/now/nav/ui/classic/params/target/change_request.do?sys_id={
                        data['result']['sys_id']}")


if __name__ == "__main__":
    main()
