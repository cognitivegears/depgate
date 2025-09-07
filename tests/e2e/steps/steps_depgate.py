from behave import given, when, then, step
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ENTRY = PROJECT_ROOT / "src" / "depgate.py"
ARTIFACTS = PROJECT_ROOT / "tests" / "e2e" / "artifacts"
MOCKS_DIR = PROJECT_ROOT / "tests" / "e2e_mocks"

def _ensure_artifacts():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    return ARTIFACTS

def _unique_name(prefix, ext):
    return f"{prefix}-{uuid.uuid4().hex[:8]}.{ext}"

def _resolve_placeholder(val, context):
    # Map placeholders to generated paths
    if val == "<json_path>":
        context.json_path = str(_ensure_artifacts() / _unique_name("out", "json"))
        return context.json_path
    if val == "<csv_path>":
        context.csv_path = str(_ensure_artifacts() / _unique_name("out", "csv"))
        return context.csv_path
    if val == "<tmp_dir>":
        return getattr(context, "tmp_dir")
    if val == "<list_file>":
        return getattr(context, "list_file")
    return val

@given("fake registries are enabled")
def step_enable_fakes(context):
    context.fake_enabled = True

@given(fake
