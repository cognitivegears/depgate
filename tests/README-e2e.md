# E2E BDD Tests

This directory contains Behavior-Driven Development (BDD) end-to-end tests for the depgate CLI tool.

## Running Tests

### Using the Runner Script

The recommended way to run the E2E tests is using the provided runner script:

```bash
./scripts/run-e2e.sh
```

This script:
- Sets up the proper environment variables (`PYTHONPATH` and `FAKE_REGISTRY`)
- Uses `uvx` to run behave without requiring global installation
- Generates both progress output and JSON reports

### Manual Execution

You can also run the tests manually:

```bash
PYTHONPATH="src:tests/e2e_mocks" FAKE_REGISTRY=1 uvx -q behave -f progress -f json.pretty -o tests/e2e/artifacts/report.json tests/e2e/features
```

## Test Structure

- **Features**: Individual `.feature` files in `tests/e2e/features/` define test scenarios
- **Steps**: Step definitions in `tests/e2e/features/steps/steps_depgate.py` implement the test logic
- **Mocks**: Fake registry responses in `tests/e2e_mocks/` simulate external API calls

## Reports

Test results are saved to:
- **JSON Report**: `tests/e2e/artifacts/report.json` - Detailed test results in JSON format
- **Console Output**: Real-time progress during test execution

## Environment

The tests use fake registries to avoid external dependencies. Environment variables:
- `FAKE_REGISTRY=1`: Enables mock registry responses
- `PYTHONPATH=src:tests/e2e_mocks`: Includes source code and mock modules
