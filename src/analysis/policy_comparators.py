"""Policy comparators for evaluating rule constraints."""

from typing import Any, Union
import logging

logger = logging.getLogger(__name__)


class Comparator:
    """Base class for value comparators."""

    def compare(self, actual: Any, expected: Any) -> bool:
        """Compare actual value against expected value.

        Args:
            actual: The actual value to compare.
            expected: The expected value to compare against.

        Returns:
            True if comparison passes, False otherwise.
        """
        raise NotImplementedError


class MinComparator(Comparator):
    """Minimum value comparator (>=)."""

    def compare(self, actual: Any, expected: Any) -> bool:
        """Check if actual >= expected."""
        try:
            return self._normalize_value(actual) >= self._normalize_value(expected)
        except (TypeError, ValueError):
            return False

    def _normalize_value(self, value: Any) -> Union[int, float]:
        """Normalize value to numeric type.

        Raises:
            ValueError/TypeError when value cannot be coerced to number.
        """
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            # Only numeric strings are allowed
            return float(value)
        # Do not silently coerce to 0; propagate error so compare() returns False.
        raise TypeError("Non-numeric value")


class MaxComparator(Comparator):
    """Maximum value comparator (<=)."""

    def compare(self, actual: Any, expected: Any) -> bool:
        """Check if actual <= expected."""
        try:
            return self._normalize_value(actual) <= self._normalize_value(expected)
        except (TypeError, ValueError):
            return False

    def _normalize_value(self, value: Any) -> Union[int, float]:
        """Normalize value to numeric type.

        Raises:
            ValueError/TypeError when value cannot be coerced to number.
        """
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            # Only numeric strings are allowed
            return float(value)
        # Do not silently coerce to 0; propagate error so compare() returns False.
        raise TypeError("Non-numeric value")


class EqComparator(Comparator):
    """Equality comparator (==)."""

    def compare(self, actual: Any, expected: Any) -> bool:
        """Check if actual == expected."""
        return actual == expected


class NeComparator(Comparator):
    """Not equal comparator (!=)."""

    def compare(self, actual: Any, expected: Any) -> bool:
        """Check if actual != expected."""
        return actual != expected


class InComparator(Comparator):
    """Membership comparator (in)."""

    def compare(self, actual: Any, expected: Any) -> bool:
        """Check if actual is in expected (list/set)."""
        if not isinstance(expected, (list, set, tuple)):
            return False
        return actual in expected


class NotInComparator(Comparator):
    """Not membership comparator (not in)."""

    def compare(self, actual: Any, expected: Any) -> bool:
        """Check if actual is not in expected (list/set)."""
        if not isinstance(expected, (list, set, tuple)):
            return False
        return actual not in expected


class ComparatorRegistry:
    """Registry for policy comparators."""

    def __init__(self):
        """Initialize the comparator registry."""
        self._comparators = {
            "min": MinComparator(),
            "max": MaxComparator(),
            "eq": EqComparator(),
            "ne": NeComparator(),
            "in": InComparator(),
            "not_in": NotInComparator(),
        }

    def get_comparator(self, name: str) -> Comparator:
        """Get a comparator by name.

        Args:
            name: The comparator name.

        Returns:
            The comparator instance.

        Raises:
            ValueError: If comparator not found.
        """
        if name not in self._comparators:
            raise ValueError(f"Unknown comparator: {name}")
        return self._comparators[name]

    def register_comparator(self, name: str, comparator: Comparator) -> None:
        """Register a new comparator.

        Args:
            name: The comparator name.
            comparator: The comparator instance.
        """
        self._comparators[name] = comparator


# Global registry instance
comparator_registry = ComparatorRegistry()
