"""Exceptions for versioning operations."""


class ParseError(Exception):
    """Raised when a token cannot be parsed under rightmost-colon and ecosystem rules."""


class ResolutionError(Exception):
    """Reserved for resolution layer; defined here for import stability."""
