# Running Integration Tests

## Prerequisites

The integration tests require:
- A ServiceNow instance (dev/test environment recommended, NOT production)
- Valid ServiceNow credentials
- A standard change template sys_id. The template must have an assignment group set.

## Environment Variables

Set the following environment variables before running tests:

```bash
export SNOW_URL="https://your-instance.service-now.com"
export SNOW_USER="your-username"
export SNOW_PASSWORD="your-password"
export SNOW_STANDARD_CHANGE="standard-change-sys-id"
export DEBUG="true"  # Optional: set to "true" for verbose output
```

## Run the Integration Test

From the script directory:

```bash
cd /Users/colinsaliceti/Documents/boulot/nhs/snow
python test_integration.py
```

Or with verbose output:

```bash
python test_integration.py -v
```

## What the Test Does

The integration test runs the complete change lifecycle in sequence:

1. **test_01_create_change**: Creates a new standard change
   - Validates CHANGE_NUMBER, CHANGE_SYS_ID, CHANGE_STATE in response
   - Stores sys_id for use in subsequent tests

2. **test_02_update_to_implement**: Updates change state to "Implement"
   - Validates state change in API response

3. **test_03_update_to_review**: Updates change state to "Review"
   - Validates state change in API response

4. **test_04_close_change_successful**: Closes change with result="successful"
   - Sets state to "Closed" and close_code="successful"
   - Validates state change in API response

5. **test_05_get_change_final_state**: Retrieves final change via GET
   - Validates final state is "Closed"
   - Confirms persistence of changes

## Example Output

```
test_01_create_change (test_integration.TestSnowChangeLifecycle) ...
✓ Created change: CHG0030020 (39da29ee533eb210065e78e0a0490e59)
ok
test_02_update_to_implement (test_integration.TestSnowChangeLifecycle) ...
✓ Updated change to Implement
ok
test_03_update_to_review (test_integration.TestSnowChangeLifecycle) ...
✓ Updated change to Review
ok
test_04_close_change_successful (test_integration.TestSnowChangeLifecycle) ...
✓ Closed change successfully
ok
test_05_get_change_final_state (test_integration.TestSnowChangeLifecycle) ...
✓ Verified final change state is Closed
ok

----------------------------------------------------------------------
Ran 5 tests in 12.345s

OK
```

## Troubleshooting

### Missing Environment Variables
If you see: `RuntimeError: Missing required environment variables: ...`

**Solution**: Ensure all 5 required env vars are set:
```bash
echo $SNOW_URL $SNOW_USER $SNOW_PASSWORD $SNOW_STANDARD_CHANGE
```

### Authentication Failed (401/403)
If the CLI returns `401 Unauthorized`:
- Verify SNOW_USER and SNOW_PASSWORD are correct
- Check that the user has API access in ServiceNow
- Verify Basic auth is enabled in your ServiceNow instance

### Change Template Not Found (404)
If the CLI returns `404 Not Found`:
- Verify SNOW_STANDARD_CHANGE sys_id is correct
- Ensure the template exists in your ServiceNow instance
- Check that the user has permission to access it

### State Transitions Invalid
If an update step fails with state validation error:
- ServiceNow may restrict state transitions based on workflow
- The test assumes a standard change workflow (Scheduled → Implement → Review → Closed)
- Verify your instance allows these transitions

# Test 123
