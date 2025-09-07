#!/bin/bash

# E2E Test Runner using uv run behave
# This script runs the BDD E2E tests with proper environment setup

set -e

# Set environment variables for mocks and fake registries
export PYTHONPATH="src:tests/e2e_mocks:$PYTHONPATH"
export FAKE_REGISTRY=1

# Run behave with progress and JSON output
uv run python -m behave -f progress -f json.pretty -o tests/e2e/artifacts/report.json tests/e2e/features
