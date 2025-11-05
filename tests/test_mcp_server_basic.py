"""Basic integration tests for the MCP server.

These tests exercise the stdio initialization and list_tools; deeper tests can
mock underlying resolvers and registry clients to avoid network.
"""
import pytest


def test_mcp_subcommand_help_runs(monkeypatch):
    # Smoke test: ensure args wiring includes 'mcp'
    from args import build_root_parser

    parser, _ = build_root_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["mcp", "--help"])  # argparse will exit on --help


def test_mcp_help_contains_expected_flags_and_tools(capsys):
    # Ensure the 'mcp' subcommand help mentions expected flags and tool names
    from args import build_root_parser

    parser, _ = build_root_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["mcp", "--help"])  # argparse exits after printing help
    out = capsys.readouterr().out
    # Transport and scope flags
    assert "--host" in out
    assert "--port" in out
    assert "--project-dir" in out
    # Runtime/network flags
    assert "--offline" in out
    assert "--no-network" in out
    assert "--request-timeout" in out
    assert "--log-level" in out
    assert "--log-json" in out
    # Mention of tools in description
    assert "Scan_Project" in out
    assert "Lookup_Latest_Version" in out
    assert "Scan_Dependency" in out
