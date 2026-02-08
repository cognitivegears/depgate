"""Tests for policy preset CLI arguments."""

from args import parse_args


def test_parse_policy_preset_args():
    ns = parse_args(
        [
            "scan",
            "-t",
            "npm",
            "-p",
            "left-pad",
            "--policy-preset",
            "supply-chain",
            "--policy-min-release-age-days",
            "7",
        ]
    )
    assert ns.POLICY_PRESET == "supply-chain"
    assert ns.POLICY_MIN_RELEASE_AGE_DAYS == 7
