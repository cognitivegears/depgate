"""JSON Schema validation helpers for MCP tool input/output contracts.

This module wraps jsonschema Draft7 validation with strict and best-effort
helpers. When jsonschema is not installed, validators become no-ops so the
server can still operate in limited environments.
"""

from __future__ import annotations

from typing import Any, Dict

try:
    from jsonschema import Draft7Validator as _Draft7Validator  # type: ignore
except ImportError:  # pragma: no cover - dependency may not be present in some envs
    _Draft7Validator = None  # type: ignore


class SchemaError(ValueError):
    """Raised when data fails to validate against a provided schema."""


def validate_input(schema: Dict[str, Any], data: Dict[str, Any]) -> None:
    """Validate tool input strictly and raise on the first error.

    Args:
        schema: Draft-07 JSON Schema dict.
        data:   Input payload to validate.
    """
    if _Draft7Validator is None:
        # Soft fallback: skip validation when lib not installed
        return
    validator = _Draft7Validator(schema)
    errs = sorted(validator.iter_errors(data), key=lambda e: e.path)
    if errs:
        first = errs[0]
        path = "/".join([str(p) for p in first.path])
        msg = f"Invalid input at '{path}': {first.message}"
        raise SchemaError(msg)


def safe_validate_output(schema: Dict[str, Any], data: Dict[str, Any]) -> None:
    """Validate output best-effort; never raise to avoid breaking tool replies."""
    if _Draft7Validator is None:
        return
    validator = _Draft7Validator(schema)
    # Iterate to exercise validation; ignore errors intentionally
    _ = list(validator.iter_errors(data))


def validate_output(schema: Dict[str, Any], data: Dict[str, Any]) -> None:
    """Strictly validate output; raise SchemaError on the first problem."""
    if _Draft7Validator is None:
        return
    validator = _Draft7Validator(schema)
    errs = sorted(validator.iter_errors(data), key=lambda e: e.path)
    if errs:
        first = errs[0]
        path = "/".join([str(p) for p in first.path])
        msg = f"Invalid output at '{path}': {first.message}"
        raise SchemaError(msg)
