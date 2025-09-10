"""Tests for policy comparators."""

import pytest
from src.analysis.policy_comparators import (
    MinComparator, MaxComparator, EqComparator, NeComparator,
    InComparator, NotInComparator, comparator_registry
)


class TestMinComparator:
    """Test MinComparator (>=)."""

    def test_numeric_comparison(self):
        """Test numeric comparisons."""
        comp = MinComparator()
        assert comp.compare(5, 3) is True
        assert comp.compare(3, 5) is False
        assert comp.compare(5, 5) is True

    def test_string_to_float_conversion(self):
        """Test string to float conversion."""
        comp = MinComparator()
        assert comp.compare("5.0", 3) is True
        assert comp.compare(3, "5.0") is False

    def test_invalid_conversion(self):
        """Test invalid conversion returns False."""
        comp = MinComparator()
        assert comp.compare("invalid", 3) is False
        assert comp.compare(3, "invalid") is False


class TestMaxComparator:
    """Test MaxComparator (<=)."""

    def test_numeric_comparison(self):
        """Test numeric comparisons."""
        comp = MaxComparator()
        assert comp.compare(3, 5) is True
        assert comp.compare(5, 3) is False
        assert comp.compare(5, 5) is True


class TestEqComparator:
    """Test EqComparator (==)."""

    def test_equality(self):
        """Test equality comparisons."""
        comp = EqComparator()
        assert comp.compare(5, 5) is True
        assert comp.compare(5, 3) is False
        assert comp.compare("test", "test") is True
        assert comp.compare("test", "other") is False


class TestNeComparator:
    """Test NeComparator (!=)."""

    def test_inequality(self):
        """Test inequality comparisons."""
        comp = NeComparator()
        assert comp.compare(5, 3) is True
        assert comp.compare(5, 5) is False


class TestInComparator:
    """Test InComparator (in)."""

    def test_membership(self):
        """Test membership in lists/sets."""
        comp = InComparator()
        assert comp.compare(3, [1, 2, 3, 4]) is True
        assert comp.compare(5, [1, 2, 3, 4]) is False
        assert comp.compare("test", ["test", "other"]) is True

    def test_invalid_container(self):
        """Test with invalid container."""
        comp = InComparator()
        assert comp.compare(3, "not_a_list") is False


class TestNotInComparator:
    """Test NotInComparator (not in)."""

    def test_non_membership(self):
        """Test non-membership in lists/sets."""
        comp = NotInComparator()
        assert comp.compare(5, [1, 2, 3, 4]) is True
        assert comp.compare(3, [1, 2, 3, 4]) is False


class TestComparatorRegistry:
    """Test ComparatorRegistry."""

    def test_get_comparator(self):
        """Test getting comparators by name."""
        registry = comparator_registry
        assert isinstance(registry.get_comparator("min"), MinComparator)
        assert isinstance(registry.get_comparator("max"), MaxComparator)
        assert isinstance(registry.get_comparator("eq"), EqComparator)

    def test_unknown_comparator(self):
        """Test unknown comparator raises ValueError."""
        registry = comparator_registry
        with pytest.raises(ValueError, match="Unknown comparator: unknown"):
            registry.get_comparator("unknown")
