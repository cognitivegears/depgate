from __future__ import annotations

from typing import Any, Dict

try:
    from jsonschema import Draft7Validator
except Exception:  # pragma: no cover - dependency may not be present in some envs
    Draft7Validator = None  # type: ignore


class SchemaError(ValueError):
    pass


def validate_input(schema: Dict[str, Any], data: Dict[str, Any]) -> None:
    if Draft7Validator is None:
        # Soft fallback: skip validation when lib not installed
        return
    v = Draft7Validator(schema)
    errs = sorted(v.iter_errors(data), key=lambda e: e.path)
    if errs:
        first = errs[0]
        path = "/".join([str(p) for p in first.path])
        msg = f"Invalid input at '{path}': {first.message}"
        raise SchemaError(msg)


def safe_validate_output(schema: Dict[str, Any], data: Dict[str, Any]) -> None:
    """Validate output; never raise, only best-effort to avoid breaking tool replies."""
    try:
        if Draft7Validator is None:
            return
        v = Draft7Validator(schema)
        # Trigger validation by checking for errors; ignore them intentionally
        next(v.iter_errors(data), None)
    except Exception:
        return


def validate_output(schema: Dict[str, Any], data: Dict[str, Any]) -> None:
    """Strict output validation; raise on first error."""
    if Draft7Validator is None:
        return
    v = Draft7Validator(schema)
    errs = sorted(v.iter_errors(data), key=lambda e: e.path)
    if errs:
        first = errs[0]
        path = "/".join([str(p) for p in first.path])
        msg = f"Invalid output at '{path}': {first.message}"
        raise SchemaError(msg)
