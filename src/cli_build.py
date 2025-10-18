"""CLI Build utilities.

Provides functions for ecosystem mapping, package list construction,
version request generation, metapackage creation, version resolution,
and exit code determination. These were originally part of ``src/depgate.py``
and have been moved here to keep the entrypoint slim.
"""

# pylint: disable=too-many-locals, too-many-branches, too-many-statements, too-many-nested-blocks, import-outside-toplevel
import logging
import os
import sys

import json
import requirements

from constants import PackageManagers, ExitCodes, Constants
from cli_registry import scan_source
from cli_io import load_pkgs_file
from metapackage import MetaPackage as metapkg

# Version resolution imports support both source and installed modes:
# - Source/tests: import via src.versioning.*
# - Installed console script: import via versioning.*
try:
    from src.versioning.models import Ecosystem  # type: ignore
    from src.versioning.parser import (
        parse_cli_token,
        parse_manifest_entry,
        tokenize_rightmost_colon,
    )
    from src.versioning.service import VersionResolutionService
    from src.versioning.cache import TTLCache
except ImportError:  # Fall back when 'src' package is not available
    from versioning.models import Ecosystem  # type: ignore
    from versioning.parser import (
        parse_cli_token,
        parse_manifest_entry,
        tokenize_rightmost_colon,
    )
    from versioning.service import VersionResolutionService
    from versioning.cache import TTLCache


def to_ecosystem(pkgtype: str) -> Ecosystem:
    """Map CLI package type to Ecosystem enum."""
    if pkgtype == PackageManagers.NPM.value:
        return Ecosystem.NPM
    if pkgtype == PackageManagers.PYPI.value:
        return Ecosystem.PYPI
    if pkgtype == PackageManagers.MAVEN.value:
        return Ecosystem.MAVEN
    raise ValueError(f"Unsupported package type: {pkgtype}")


def safe_parse_token(token: str, eco: Ecosystem):
    """Parse a CLI token safely, falling back to colon split."""
    try:
        return parse_cli_token(token, eco)
    except Exception:  # pylint: disable=broad-except
        try:
            ident, _ = tokenize_rightmost_colon(token)
        except Exception:  # pylint: disable=broad-except
            ident = token
        # Return a simple object with an identifier attribute
        class _Req:
            identifier = ident
        return _Req()


def build_pkglist(args):
    """Build the package list from CLI inputs, stripping any optional version spec."""
    if args.RECURSIVE and not args.FROM_SRC:
        logging.warning("Recursive option is only applicable to source scans.")
    eco = to_ecosystem(args.package_type)

    # From list file
    if args.LIST_FROM_FILE:
        tokens = load_pkgs_file(args.LIST_FROM_FILE[0])
        idents = []
        for tok in tokens:
            req = safe_parse_token(tok, eco)
            idents.append(req.identifier)
        return list(dict.fromkeys(idents))

    # From source directory
    if args.FROM_SRC:
        return scan_source(args.package_type, args.FROM_SRC[0], recursive=args.RECURSIVE)

    # Single package CLI
    if args.SINGLE:
        idents = []
        for tok in args.SINGLE:
            req = safe_parse_token(tok, eco)
            idents.append(req.identifier)
        return list(dict.fromkeys(idents))

    return []


def build_version_requests(args, pkglist):
    """Produce PackageRequest list for resolution across all input types."""
    eco = to_ecosystem(args.package_type)
    requests = []
    seen = set()

    def add_req(identifier: str, spec, source: str):
        raw = None if spec in (None, "", "latest", "LATEST") else spec
        req = parse_manifest_entry(identifier, raw, eco, source)
        key = (eco, req.identifier)
        if key not in seen:
            seen.add(key)
            requests.append(req)

    # Tokens from list file
    if args.LIST_FROM_FILE:
        tokens = load_pkgs_file(args.LIST_FROM_FILE[0])
        for tok in tokens:
            try:
                req = parse_cli_token(tok, eco)
                key = (eco, req.identifier)
                if key not in seen:
                    seen.add(key)
                    requests.append(req)
            except Exception:  # pylint: disable=broad-except
                ident, _ = tokenize_rightmost_colon(tok)
                add_req(ident, None, "list")
        return requests

    # Single CLI tokens
    if args.SINGLE:
        for tok in args.SINGLE:
            try:
                req = parse_cli_token(tok, eco)
                key = (eco, req.identifier)
                if key not in seen:
                    seen.add(key)
                    requests.append(req)
            except Exception:  # pylint: disable=broad-except
                ident, _ = tokenize_rightmost_colon(tok)
                add_req(ident, None, "cli")
        return requests

    # Directory scans – manifest extraction
    if args.FROM_SRC:
        base_dir = args.FROM_SRC[0]

        if eco == Ecosystem.NPM:
            pkg_files = []
            if args.RECURSIVE:
                for root, _, files in os.walk(base_dir):
                    if Constants.PACKAGE_JSON_FILE in files:
                        pkg_files.append(os.path.join(root, Constants.PACKAGE_JSON_FILE))
            else:
                path = os.path.join(base_dir, Constants.PACKAGE_JSON_FILE)
                if os.path.isfile(path):
                    pkg_files.append(path)

            for pkg_path in pkg_files:
                try:
                    with open(pkg_path, "r", encoding="utf-8") as fh:
                        pj = json.load(fh)
                    deps = pj.get("dependencies", {}) or {}
                    dev = pj.get("devDependencies", {}) or {}
                    opt = pj.get("optionalDependencies", {}) or {}
                    for name, spec in {**deps, **dev, **opt}.items():
                        add_req(name, spec, "manifest")
                except Exception:  # pylint: disable=broad-except
                    continue
            for name in pkglist or []:
                add_req(name, None, "manifest")
            return requests

        if eco == Ecosystem.PYPI:
            req_files = []
            if args.RECURSIVE:
                for root, _, files in os.walk(base_dir):
                    if Constants.REQUIREMENTS_FILE in files:
                        req_files.append(os.path.join(root, Constants.REQUIREMENTS_FILE))
            else:
                path = os.path.join(base_dir, Constants.REQUIREMENTS_FILE)
                if os.path.isfile(path):
                    req_files.append(path)

            for req_path in req_files:
                try:
                    with open(req_path, "r", encoding="utf-8") as fh:
                        body = fh.read()
                    for r in requirements.parse(body):
                        name = getattr(r, "name", None)
                        if not isinstance(name, str) or not name:
                            continue
                        specs = getattr(r, "specs", []) or []
                        spec_str = ",".join(op + ver for op, ver in specs) if specs else None
                        add_req(name, spec_str, "manifest")
                except Exception:  # pylint: disable=broad-except
                    continue
            for name in pkglist or []:
                add_req(name, None, "manifest")
            return requests

        if eco == Ecosystem.MAVEN:
            pom_files = []
            if args.RECURSIVE:
                for root, _, files in os.walk(base_dir):
                    if Constants.POM_XML_FILE in files:
                        pom_files.append(os.path.join(root, Constants.POM_XML_FILE))
            else:
                path = os.path.join(base_dir, Constants.POM_XML_FILE)
                if os.path.isfile(path):
                    pom_files.append(path)

            import xml.etree.ElementTree as ET
            ns = ".//{http://maven.apache.org/POM/4.0.0}"
            for pom_path in pom_files:
                try:
                    tree = ET.parse(pom_path)
                    pom = tree.getroot()
                    for dependencies in pom.findall(f"{ns}dependencies"):
                        for dependency in dependencies.findall(f"{ns}dependency"):
                            gid = dependency.find(f"{ns}groupId")
                            aid = dependency.find(f"{ns}artifactId")
                            if gid is None or gid.text is None or aid is None or aid.text is None:
                                continue
                            ver_node = dependency.find(f"{ns}version")
                            raw_spec = (
                                ver_node.text
                                if (ver_node is not None and ver_node.text and "${" not in ver_node.text)
                                else None
                            )
                            identifier = f"{gid.text}:{aid.text}"
                            add_req(identifier, raw_spec, "manifest")
                except Exception:  # pylint: disable=broad-except
                    continue
            for name in pkglist or []:
                add_req(name, None, "manifest")
            return requests

    # Fallback – create 'latest' requests for provided names
    for name in pkglist or []:
        add_req(name, None, "fallback")
    return requests


def create_metapackages(args, pkglist):
    """Create MetaPackage instances from the package list."""
    if args.package_type == PackageManagers.NPM.value:
        for pkg in pkglist:
            metapkg(pkg, args.package_type)
    elif args.package_type == PackageManagers.MAVEN.value:
        for pkg in pkglist:  # format org_id:package_id
            if not isinstance(pkg, str) or ":" not in pkg:
                logging.error("Invalid Maven coordinate '%s'. Expected 'groupId:artifactId'.", pkg)
                sys.exit(ExitCodes.FILE_ERROR.value)
            parts = pkg.split(":")
            if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
                logging.error("Invalid Maven coordinate '%s'. Expected 'groupId:artifactId'.", pkg)
                sys.exit(ExitCodes.FILE_ERROR.value)
            metapkg(parts[1], args.package_type, parts[0])
    elif args.package_type == PackageManagers.PYPI.value:
        for pkg in pkglist:
            metapkg(pkg, args.package_type)


def apply_version_resolution(args, pkglist):
    """Resolve package versions and populate MetaPackage fields."""
    try:
        eco = to_ecosystem(args.package_type)
        requests = build_version_requests(args, pkglist)
        if requests:
            svc = VersionResolutionService(TTLCache())
            res_map = svc.resolve_all(requests)
            for mp in metapkg.instances:
                if eco == Ecosystem.MAVEN and getattr(mp, "org_id", None):
                    ident = f"{mp.org_id}:{mp.pkg_name}"
                elif eco == Ecosystem.PYPI:
                    ident = mp.pkg_name.lower().replace("_", "-")
                else:
                    ident = mp.pkg_name
                key = (eco, ident)
                rr = res_map.get(key)
                if not rr:
                    rr = next((v for (k_ec, k_id), v in res_map.items() if k_ec == eco and k_id == mp.pkg_name), None)
                if rr:
                    mp.requested_spec = rr.requested_spec
                    mp.resolved_version = rr.resolved_version
                    mp.resolution_mode = (
                        rr.resolution_mode.value
                        if hasattr(rr.resolution_mode, "value")
                        else rr.resolution_mode
                    )
    except Exception:  # pylint: disable=broad-except
        # Do not fail CLI if resolution errors occur; continue with legacy behavior
        pass


def determine_exit_code(args):
    """Determine final exit code based on risk and warning flags."""
    # Linked analysis has dedicated semantics: all packages must pass linkage checks.
    try:
        level = getattr(args, "LEVEL", None)
    except Exception:  # pylint: disable=broad-exception-caught
        level = None

    # Policy mode: non-zero exit for any policy denial
    if level in ("policy", "pol"):
        any_deny = False
        for x in metapkg.instances:
            if getattr(x, "policy_decision", None) == "deny":
                any_deny = True
                break
        if any_deny:
            logging.error("Policy violations detected; exiting with non-zero status.")
        sys.exit(ExitCodes.SUCCESS.value if not any_deny else ExitCodes.FILE_ERROR.value)

    if level == "linked":
        any_fail = False
        # flag previously tracked whether any manifest was found; not used
        for x in metapkg.instances:
            if getattr(x, "_linked_mode", False):
                if not bool(getattr(x, "linked", False)):
                    any_fail = True
        # For linked analysis, exit 0 only when all packages are linked; otherwise 1.
        sys.exit(ExitCodes.SUCCESS.value if not any_fail else ExitCodes.FILE_ERROR.value)

    has_risk = any(x.has_risk() for x in metapkg.instances)
    if has_risk:
        logging.warning("One or more packages have identified risks.")
        if getattr(args, "ERROR_ON_WARNINGS", False):
            logging.error("Warnings present, exiting with non-zero status code.")
            sys.exit(ExitCodes.EXIT_WARNINGS.value)
    sys.exit(ExitCodes.SUCCESS.value)


# scan_source functionality moved to src/cli_registry.py
