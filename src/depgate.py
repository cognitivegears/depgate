"""DepGate - Dependency supply-chain/confusion risk checker (hard fork)

    Raises:
        TypeError: If the input list cannot be processed

    Returns:
        int: Exit code
"""
import csv
import sys
import logging
import json
import os
import xml.etree.ElementTree as ET
import requirements

# internal module imports (kept light to avoid heavy deps on --help)
from metapackage import MetaPackage as metapkg
from constants import ExitCodes, PackageManagers, Constants
from common.logging_utils import configure_logging, extra_context, is_debug_enabled
from args import parse_args

# Version resolution imports support both source and installed modes:
# - Source/tests: import via src.versioning.*
# - Installed console script: import via versioning.*
try:
    from src.versioning.models import Ecosystem
    from src.versioning.parser import parse_cli_token, parse_manifest_entry, tokenize_rightmost_colon
    from src.versioning.service import VersionResolutionService
    from src.versioning.cache import TTLCache
except ImportError:  # Fall back when 'src' package is not available
    from versioning.models import Ecosystem
    from versioning.parser import parse_cli_token, parse_manifest_entry, tokenize_rightmost_colon
    from versioning.service import VersionResolutionService
    from versioning.cache import TTLCache


SUPPORTED_PACKAGES = Constants.SUPPORTED_PACKAGES

def load_pkgs_file(file_name):
    """Loads the packages from a file.

    Args:
        file_name (str): File path containing the list of packages.

    Raises:
        TypeError: If the input list cannot be processed

    Returns:
        list: List of packages
    """
    try:
        with open(file_name, encoding='utf-8') as file:
            return [line.strip() for line in file]
    except FileNotFoundError as e:
        logging.error("File not found: %s, aborting", e)
        sys.exit(ExitCodes.FILE_ERROR.value)
    except IOError as e:
        logging.error("IO error: %s, aborting", e)
        sys.exit(ExitCodes.FILE_ERROR.value)

def scan_source(pkgtype, dir_name, recursive=False):
    """Scans the source directory for packages.

    Args:
        pkgtype (str): Package manager type, i.e. "npm".
        dir_name (str): Directory path to scan.
        recursive (bool, optional): Whether to recurse into subdirectories. Defaults to False.

    Returns:
        list: List of packages found in the source directory.
    """
    if pkgtype == PackageManagers.NPM.value:
        from registry import npm as _npm  # pylint: disable=import-outside-toplevel
        return _npm.scan_source(dir_name, recursive)
    if pkgtype == PackageManagers.MAVEN.value:
        from registry import maven as _maven  # pylint: disable=import-outside-toplevel
        return _maven.scan_source(dir_name, recursive)
    if pkgtype == PackageManagers.PYPI.value:
        from registry import pypi as _pypi  # pylint: disable=import-outside-toplevel
        return _pypi.scan_source(dir_name, recursive)
    logging.error("Selected package type doesn't support import scan.")
    sys.exit(ExitCodes.FILE_ERROR.value)

def check_against(check_type, level, check_list):
    """Checks the packages against the registry.

    Args:
        check_type (str): Package manager type, i.e. "npm".
        level (str): Analysis level affecting fetch behavior.
        check_list (list): List of packages to check.
    """


    if check_type == PackageManagers.NPM.value:
        # Fetch details for heuristics and policy levels (to enable repo enrichment)
        should_fetch_details = level in (
            Constants.LEVELS[2],  # heuristics
            Constants.LEVELS[3],  # heur
            Constants.LEVELS[4],  # policy
            Constants.LEVELS[5],  # pol
        )
        from registry import npm as _npm  # pylint: disable=import-outside-toplevel
        _npm.recv_pkg_info(check_list, should_fetch_details)
    elif check_type == PackageManagers.MAVEN.value:
        from registry import maven as _maven  # pylint: disable=import-outside-toplevel
        _maven.recv_pkg_info(check_list)
    elif check_type == PackageManagers.PYPI.value:
        from registry import pypi as _pypi  # pylint: disable=import-outside-toplevel
        _pypi.recv_pkg_info(check_list)
    else:
        logging.error("Selected package type doesn't support registry check.")
        sys.exit(ExitCodes.FILE_ERROR.value)

def export_csv(instances, path):
    """Exports the package properties to a CSV file.

    Args:
        instances (list): List of package instances.
        path (str): File path to export the CSV.
    """
    headers = [
        "Package Name",
        "Package Type",
        "Exists on External",
        "Org/Group ID",
        "Score",
        "Version Count",
        "Timestamp",
        "Risk: Missing",
        "Risk: Low Score",
        "Risk: Min Versions",
        "Risk: Too New",
        "Risk: Any Risks",
        # Append new fields before repo_* to preserve last-five repo_* columns for compatibility
        "requested_spec",
        "resolved_version",
        "resolution_mode",
        "dependency_relation",
        "dependency_requirement",
        "dependency_scope",
        "repo_stars",
        "repo_contributors",
        "repo_last_activity",
        "repo_present_in_registry",
        "repo_version_match",
    ]
    rows = [headers]

    def _nv(v):
        return "" if v is None else v

    for x in instances:
        # Build row aligned to headers; do NOT include policy/license columns here to preserve legacy CSV shape
        row = [
            x.pkg_name,
            x.pkg_type,
            x.exists,
            x.org_id,
            x.score,
            x.version_count,
            x.timestamp,
            x.risk_missing,
            x.risk_low_score,
            x.risk_min_versions,
            x.risk_too_new,
            x.has_risk(),
            _nv(getattr(x, "requested_spec", None)),
            _nv(getattr(x, "resolved_version", None)),
            _nv(getattr(x, "resolution_mode", None)),
            _nv(getattr(x, "dependency_relation", None)),
            _nv(getattr(x, "dependency_requirement", None)),
            _nv(getattr(x, "dependency_scope", None)),
            _nv(getattr(x, "repo_stars", None)),
            _nv(getattr(x, "repo_contributors", None)),
            _nv(getattr(x, "repo_last_activity_at", None)),
        ]
        # repo_present_in_registry with special-case blanking
        _present = getattr(x, "repo_present_in_registry", None)
        _norm_url = getattr(x, "repo_url_normalized", None)
        if (_present is False) and (_norm_url is None):
            row.append("")
        else:
            row.append(_nv(_present))
        # repo_version_match simplified to boolean 'matched' or blank
        _ver_match = getattr(x, "repo_version_match", None)
        if _ver_match is None:
            row.append("")
        else:
            try:
                row.append(bool(_ver_match.get("matched")))
            except Exception:  # pylint: disable=broad-exception-caught
                row.append("")
        rows.append(row)
    try:
        with open(path, 'w', newline='', encoding='utf-8') as file:
            export = csv.writer(file)
            export.writerows(rows)
        logging.info("CSV file has been successfully exported at: %s", path)
    except (OSError, csv.Error) as e:
        logging.error("CSV file couldn't be written to disk: %s", e)
        sys.exit(1)

def export_json(instances, path):
    """Exports the package properties to a JSON file.

    Args:
        instances (list): List of package instances.
        path (str): File path to export the JSON.
    """
    data = []
    for x in instances:
        data.append({
            "packageName": x.pkg_name,
            "orgId": x.org_id,
            "packageType": x.pkg_type,
            "exists": x.exists,
            "score": x.score,
            "versionCount": x.version_count,
            "createdTimestamp": x.timestamp,
            "repo_stars": x.repo_stars,
            "repo_contributors": x.repo_contributors,
            "repo_last_activity": x.repo_last_activity_at,
            "repo_present_in_registry": (
                None
                if (
                    getattr(x, "repo_url_normalized", None) is None
                    and x.repo_present_in_registry is False
                )
                else x.repo_present_in_registry
            ),
            "repo_version_match": x.repo_version_match,
            "risk": {
                "hasRisk": x.has_risk(),
                "isMissing": x.risk_missing,
                "hasLowScore": x.risk_low_score,
                "minVersions": x.risk_min_versions,
                "isNew": x.risk_too_new
            },
            "requested_spec": getattr(x, "requested_spec", None),
            "resolved_version": getattr(x, "resolved_version", None),
            "resolution_mode": getattr(x, "resolution_mode", None),
            "dependency_relation": getattr(x, "dependency_relation", None),
            "dependency_requirement": getattr(x, "dependency_requirement", None),
            "dependency_scope": getattr(x, "dependency_scope", None),
            "policy": {
                "decision": getattr(x, "policy_decision", None),
                "violated_rules": getattr(x, "policy_violated_rules", []),
                "evaluated_metrics": getattr(x, "policy_evaluated_metrics", {}),
            },
            "license": {
                "id": getattr(x, "license_id", None),
                "available": getattr(x, "license_available", None),
                "source": getattr(x, "license_source", None),
            }
        })
    try:
        with open(path, 'w', encoding='utf-8') as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
        logging.info("JSON file has been successfully exported at: %s", path)
    except OSError as e:
        logging.error("JSON file couldn't be written to disk: %s", e)
        sys.exit(1)



def _to_ecosystem(pkgtype: str) -> Ecosystem:
    """Map CLI package type to Ecosystem enum."""
    if pkgtype == PackageManagers.NPM.value:
        return Ecosystem.NPM
    if pkgtype == PackageManagers.PYPI.value:
        return Ecosystem.PYPI
    if pkgtype == PackageManagers.MAVEN.value:
        return Ecosystem.MAVEN
    raise ValueError(f"Unsupported package type: {pkgtype}")

def build_pkglist(args):
    """Build the package list from CLI inputs, stripping any optional version spec."""
    if args.RECURSIVE and not args.FROM_SRC:
        logging.warning("Recursive option is only applicable to source scans.")
    eco = _to_ecosystem(args.package_type)
    # From list: parse tokens and return identifiers only
    if args.LIST_FROM_FILE:
        tokens = load_pkgs_file(args.LIST_FROM_FILE[0])
        idents = []
        for tok in tokens:
            try:
                req = parse_cli_token(tok, eco)
                idents.append(req.identifier)
            except Exception:  # pylint: disable=broad-exception-caught
                # Fallback: rightmost-colon split
                try:
                    ident, _ = tokenize_rightmost_colon(tok)
                    idents.append(ident)
                except Exception:  # pylint: disable=broad-exception-caught
                    idents.append(tok)
        return list(dict.fromkeys(idents))
    # From source: delegate to scanners (names only for backward compatibility)
    if args.FROM_SRC:
        return scan_source(args.package_type, args.FROM_SRC[0], recursive=args.RECURSIVE)
    # Single package CLI
    if args.SINGLE:
        idents = []
        for tok in args.SINGLE:
            try:
                req = parse_cli_token(tok, eco)
                idents.append(req.identifier)
            except Exception:  # pylint: disable=broad-exception-caught
                try:
                    ident, _ = tokenize_rightmost_colon(tok)
                    idents.append(ident)
                except Exception:  # pylint: disable=broad-exception-caught
                    idents.append(tok)
        return list(dict.fromkeys(idents))
    return []

def build_version_requests(args, pkglist):
    """Produce PackageRequest list for resolution across all input types."""
    # pylint: disable=too-many-locals, too-many-branches, too-many-statements, too-many-nested-blocks
    eco = _to_ecosystem(args.package_type)
    requests = []
    seen = set()

    def add_req(identifier: str, spec, source: str):
        # Accept spec as Optional[str]; normalize here
        raw = None if spec in (None, "", "latest", "LATEST") else spec
        req = parse_manifest_entry(identifier, raw, eco, source)
        key = (eco, req.identifier)
        if key not in seen:
            seen.add(key)
            requests.append(req)

    # CLI/List tokens with optional version specs
    if args.LIST_FROM_FILE:
        tokens = load_pkgs_file(args.LIST_FROM_FILE[0])
        for tok in tokens:
            try:
                req = parse_cli_token(tok, eco)
                key = (eco, req.identifier)
                if key not in seen:
                    seen.add(key)
                    requests.append(req)
            except Exception:  # pylint: disable=broad-exception-caught
                # Fallback: treat as latest
                ident, _ = tokenize_rightmost_colon(tok)
                add_req(ident, None, "list")
        return requests

    if args.SINGLE:
        for tok in args.SINGLE:
            try:
                req = parse_cli_token(tok, eco)
                key = (eco, req.identifier)
                if key not in seen:
                    seen.add(key)
                    requests.append(req)
            except Exception:  # pylint: disable=broad-exception-caught
                ident, _ = tokenize_rightmost_colon(tok)
                add_req(ident, None, "cli")
        return requests

    # Directory scans: read manifests to extract specs where feasible
    if args.FROM_SRC:
        base_dir = args.FROM_SRC[0]
        if eco == Ecosystem.NPM:
            # Find package.json files (respect recursive flag)
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
                    for name, spec in {**deps, **dev}.items():
                        add_req(name, spec, "manifest")
                except Exception:  # pylint: disable=broad-exception-caught
                    continue
            # Ensure at least latest requests for names discovered by scan_source
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
                except Exception:  # pylint: disable=broad-exception-caught
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
            for pom_path in pom_files:
                try:
                    tree = ET.parse(pom_path)
                    pom = tree.getroot()
                    ns = ".//{http://maven.apache.org/POM/4.0.0}"
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
                except Exception:  # pylint: disable=broad-exception-caught
                    continue
            for name in pkglist or []:
                add_req(name, None, "manifest")
            return requests

    # Fallback: create 'latest' requests for the provided names
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
            # Validate Maven coordinate "groupId:artifactId"
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

def run_analysis(level, args=None):
    """Run the selected analysis for collected packages."""
    if level in (Constants.LEVELS[0], Constants.LEVELS[1]):
        from analysis import heuristics as _heur  # pylint: disable=import-outside-toplevel
        _heur.run_min_analysis(metapkg.instances)
    elif level in (Constants.LEVELS[2], Constants.LEVELS[3]):
        from analysis import heuristics as _heur  # pylint: disable=import-outside-toplevel
        _heur.run_heuristics(metapkg.instances)
    elif level in ("policy", "pol"):
        run_policy_analysis(args)


def run_policy_analysis(args):
    """Run policy analysis for collected packages."""
    # Import policy modules
    from analysis.facts import FactBuilder
    from analysis.policy import create_policy_engine
    from repository.license_discovery import license_discovery
    from analysis import heuristics as _heur

    # Get global args (assuming they're available in this scope)
    import sys
    # We need to get args from the calling context
    # For now, we'll assume args is available globally or passed somehow
    # This is a simplification - in practice we'd need to pass args

    # Step 1: Build facts for all packages
    fact_builder = FactBuilder()
    all_facts = {}
    for pkg in metapkg.instances:
        facts = fact_builder.build_facts(pkg)
        all_facts[pkg.pkg_name] = facts

    # Step 2: Check if heuristics are needed
    # (This would be based on policy config - simplified for now)
    heuristic_metrics_needed = ["heuristic_score", "is_license_available"]

    for pkg in metapkg.instances:
        facts = all_facts[pkg.pkg_name]
        needs_heuristics = any(
            key not in facts or facts.get(key) is None
            for key in heuristic_metrics_needed
        )
        if needs_heuristics:
            # Run heuristics for this package
            _heur.run_heuristics([pkg])
            # Update facts with new heuristic data
            facts["heuristic_score"] = getattr(pkg, "score", None)
            facts["is_license_available"] = getattr(pkg, "is_license_available", None)

    # Step 3: Check if license discovery is needed
    # (This would be based on policy config - simplified for now)
    for pkg in metapkg.instances:
        facts = all_facts[pkg.pkg_name]
        if (facts.get("license", {}).get("id") is None and
            getattr(pkg, "repo_url_normalized", None)):
            # Try license discovery
            try:
                license_info = license_discovery.discover_license(
                    pkg.repo_url_normalized, "default"
                )
                facts["license"] = license_info
            except Exception:
                # License discovery failed, keep as None
                pass

    # Step 4: Create policy engine and evaluate
    policy_engine = create_policy_engine()

    # Load policy configuration with precedence:
    # 1) CLI --set overrides (highest)
    # 2) Explicit --config file or default YAML locations (policy section)
    # 3) Built-in defaults (only when no user policy and no overrides)
    def _load_policy_from_user_config(cli_args):
        """Return policy dict from user config if available; otherwise None."""
        cfg = {}
        # Explicit --config path (supports YAML or JSON)
        path = getattr(cli_args, "CONFIG", None)
        if isinstance(path, str) and path.strip():
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    lower = path.lower()
                    if lower.endswith(".json"):
                        try:
                            cfg = json.load(fh) or {}
                        except Exception:
                            cfg = {}
                    else:
                        try:
                            import yaml as _yaml  # type: ignore
                        except Exception:
                            _yaml = None
                        if _yaml is not None:
                            try:
                                cfg = _yaml.safe_load(fh) or {}
                            except Exception:
                                cfg = {}
                        else:
                            cfg = {}
            except Exception:
                cfg = {}
        # Fallback: default YAML locations handled by constants
        if not cfg:
            try:
                from constants import _load_yaml_config as _defaults_loader  # type: ignore
                cfg = _defaults_loader() or {}
            except Exception:
                cfg = {}
        if isinstance(cfg, dict):
            pol = cfg.get("policy")
            if isinstance(pol, dict):
                return pol
        return None

    def _coerce_value(text):
        """Best-effort convert string to JSON/number/bool, else raw string."""
        s = str(text).strip()
        try:
            return json.loads(s)
        except Exception:
            sl = s.lower()
            if sl == "true":
                return True
            if sl == "false":
                return False
            try:
                if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
                    return int(s)
                return float(s)
            except Exception:
                return s

    def _apply_dot_path(dct, dot_path, value):
        parts = [p for p in dot_path.split(".") if p]
        cur = dct
        for key in parts[:-1]:
            if key not in cur or not isinstance(cur.get(key), dict):
                cur[key] = {}
            cur = cur[key]
        cur[parts[-1]] = value

    def _collect_policy_overrides(pairs):
        overrides = {}
        if not pairs:
            return overrides
        for item in pairs:
            if not isinstance(item, str) or "=" not in item:
                continue
            key, val = item.split("=", 1)
            key = key.strip()
            if key.startswith("policy."):
                key = key[len("policy.") :]
            _apply_dot_path(overrides, key, _coerce_value(val.strip()))
        return overrides

    user_policy = _load_policy_from_user_config(args)
    overrides_present = bool(getattr(args, "POLICY_SET", None))

    if user_policy is not None:
        policy_config = dict(user_policy)  # shallow copy from user config
    elif overrides_present:
        # If overrides are provided but no user policy config exists, start from empty
        policy_config = {}
    else:
        # Built-in fallback defaults
        policy_config = {
            "fail_fast": False,
            "metrics": {
                "stars_count": {"min": 5},
                "heuristic_score": {"min": 0.6},
            },
        }

    if overrides_present:
        ov = _collect_policy_overrides(getattr(args, "POLICY_SET", []))
        # Deep merge overrides into base policy_config
        def _deep_merge(dest, src):
            for k, v in src.items():
                if isinstance(v, dict) and isinstance(dest.get(k), dict):
                    _deep_merge(dest[k], v)
                else:
                    dest[k] = v
        _deep_merge(policy_config, ov)

    # Evaluate each package
    for pkg in metapkg.instances:
        facts = all_facts[pkg.pkg_name]
        decision = policy_engine.evaluate_policy(facts, policy_config)

        # Store decision on package for output
        pkg.policy_decision = decision.decision
        pkg.policy_violated_rules = decision.violated_rules
        pkg.policy_evaluated_metrics = decision.evaluated_metrics

        # Log results
        if decision.decision == "deny":
            logging.warning(f"Policy DENY for {pkg.pkg_name}: {', '.join(decision.violated_rules)}")
        else:
            logging.info(f"Policy ALLOW for {pkg.pkg_name}")
def build_dependency_classification(args):
    """Build mapping from identifier to classification strings for source scans."""
    try:
        eco = _to_ecosystem(args.package_type)
        result = {}
        if not getattr(args, "FROM_SRC", None):
            return result
        base_dir = args.FROM_SRC[0]

        def _merge(name, rel, req, scope):
            # Convert enum-like values to strings
            rel_s = rel.value if hasattr(rel, "value") else str(rel)
            req_s = req.value if hasattr(req, "value") else str(req)
            scope_s = scope.value if hasattr(scope, "value") else str(scope)
            existing = result.get(name)
            if not existing:
                result[name] = {"relation": rel_s, "requirement": req_s, "scope": scope_s}
                return
            # Prefer stronger requirement and scope; and direct over transitive
            prio_req = {"required": 2, "optional": 1}
            prio_scope = {"normal": 3, "development": 2, "testing": 1}
            if prio_req.get(req_s, 0) > prio_req.get(existing.get("requirement"), 0):
                existing["requirement"] = req_s
            if prio_scope.get(scope_s, 0) > prio_scope.get(existing.get("scope"), 0):
                existing["scope"] = scope_s
            if existing.get("relation") != "direct" and rel_s == "direct":
                existing["relation"] = "direct"

        import os as _os
        import json as _json

        if eco == Ecosystem.NPM:
            pkg_files = []
            if args.RECURSIVE:
                for root, _, files in _os.walk(base_dir):
                    if Constants.PACKAGE_JSON_FILE in files:
                        pkg_files.append(_os.path.join(root, Constants.PACKAGE_JSON_FILE))
            else:
                path = _os.path.join(base_dir, Constants.PACKAGE_JSON_FILE)
                if _os.path.isfile(path):
                    pkg_files.append(path)

            def _extract_npm_name_from_path(p: str) -> str:
                try:
                    # Normalize separators
                    p = str(p).replace("\\\\", "/")
                    # Find last occurrence of node_modules
                    if "node_modules/" in p:
                        segs = p.split("node_modules/")
                        tail = segs[-1]
                        parts = [s for s in tail.split("/") if s]
                        if not parts:
                            return ""
                        if parts[0].startswith("@") and len(parts) >= 2:
                            return f"{parts[0]}/{parts[1]}"
                        return parts[0]
                    return ""
                except Exception:
                    return ""

            def _scan_npm_lock_obj(obj: dict) -> dict[str, bool]:
                names_dev: dict[str, bool] = {}
                try:
                    pkgs = obj.get("packages")
                    if isinstance(pkgs, dict):
                        for path, meta in pkgs.items():
                            if not isinstance(meta, dict):
                                continue
                            name = meta.get("name") or _extract_npm_name_from_path(path or "")
                            if not name:
                                continue
                            dev = bool(meta.get("dev", False))
                            names_dev[name] = names_dev.get(name, False) or dev
                    elif isinstance(obj.get("dependencies"), dict):
                        def _rec(depmap: dict):
                            for nm, meta in depmap.items():
                                if not isinstance(meta, dict):
                                    continue
                                dev = bool(meta.get("dev", False))
                                names_dev[nm] = names_dev.get(nm, False) or dev
                                sub = meta.get("dependencies")
                                if isinstance(sub, dict):
                                    _rec(sub)
                        _rec(obj["dependencies"])
                except Exception:
                    pass
                return names_dev

            # Collect direct declarations and parse lockfiles for transitives
            for pkg_path in pkg_files:
                try:
                    with open(pkg_path, "r", encoding="utf-8") as fh:
                        pj = _json.load(fh) or {}
                    deps = pj.get("dependencies", {}) or {}
                    dev = pj.get("devDependencies", {}) or {}
                    opt = pj.get("optionalDependencies", {}) or {}
                    for name in deps.keys():
                        _merge(name, "direct", "required", "normal")
                    for name in dev.keys():
                        _merge(name, "direct", "required", "development")
                    for name in opt.keys():
                        _merge(name, "direct", "optional", "normal")

                    # Lockfile-based transitives (package-lock.json or npm-shrinkwrap.json)
                    root_dir = _os.path.dirname(pkg_path)
                    for lock_name in ("package-lock.json", "npm-shrinkwrap.json"):
                        lock_path = _os.path.join(root_dir, lock_name)
                        if _os.path.isfile(lock_path):
                            try:
                                with open(lock_path, "r", encoding="utf-8") as lf:
                                    lock_obj = _json.load(lf) or {}
                                names_dev = _scan_npm_lock_obj(lock_obj)
                                for nm, is_dev in names_dev.items():
                                    # do not override direct mapping; mark others as transitive
                                    _merge(nm, "transitive", "required", "development" if is_dev else "normal")
                            except Exception:
                                # best-effort
                                pass
                except Exception:
                    continue
            return result

        if eco == Ecosystem.PYPI:
            py_files = []
            req_files = []
            lock_files = []
            for root, _, files in _os.walk(base_dir):
                if Constants.PYPROJECT_TOML_FILE in files:
                    py_files.append(_os.path.join(root, Constants.PYPROJECT_TOML_FILE))
                if Constants.REQUIREMENTS_FILE in files:
                    req_files.append(_os.path.join(root, Constants.REQUIREMENTS_FILE))
                if Constants.UV_LOCK_FILE in files:
                    lock_files.append(_os.path.join(root, Constants.UV_LOCK_FILE))
                if Constants.POETRY_LOCK_FILE in files:
                    lock_files.append(_os.path.join(root, Constants.POETRY_LOCK_FILE))
            try:
                from versioning.parser import parse_pyproject_for_direct_pypi, parse_requirements_txt
            except Exception:
                from src.versioning.parser import parse_pyproject_for_direct_pypi, parse_requirements_txt  # type: ignore
            # Direct dependencies from manifests
            for path in py_files:
                try:
                    recs = parse_pyproject_for_direct_pypi(path) or {}
                    for name, rec in recs.items():
                        _merge(
                            name.lower().replace("_", "-"),
                            getattr(rec, "relation", "direct"),
                            getattr(rec, "requirement", "required"),
                            getattr(rec, "scope", "normal"),
                        )
                except Exception:
                    continue
            for path in req_files:
                try:
                    recs = parse_requirements_txt(path) or {}
                    for name, rec in recs.items():
                        _merge(
                            name.lower().replace("_", "-"),
                            getattr(rec, "relation", "direct"),
                            getattr(rec, "requirement", "required"),
                            getattr(rec, "scope", "normal"),
                        )
                except Exception:
                    continue

            # Lockfile-derived transitives (uv.lock / poetry.lock)
            def _scan_pypi_lock(lock_path: str) -> list[tuple[str, bool]]:
                names: list[tuple[str, bool]] = []
                try:
                    try:
                        import tomllib as _toml  # type: ignore
                    except Exception:
                        import tomli as _toml  # type: ignore
                    with open(lock_path, "rb") as fh:
                        data = _toml.load(fh) or {}
                    pkgs = data.get("package")
                    if isinstance(pkgs, list):
                        for rec in pkgs:
                            if isinstance(rec, dict):
                                nm = rec.get("name")
                                if isinstance(nm, str) and nm.strip():
                                    name = nm.strip().lower().replace("_", "-")
                                    cat = str(rec.get("category", "")).strip().lower()
                                    grp = str(rec.get("group", "")).strip().lower()
                                    is_dev = cat in ("dev", "test") or grp in ("dev", "test")
                                    names.append((name, is_dev))
                    else:
                        # Fallback: best-effort regex scan
                        try:
                            import re as _re
                            with open(lock_path, "r", encoding="utf-8") as fh2:
                                text = fh2.read()
                            for m in _re.finditer(r'\\bname\\s*=\\s*"(.*?)"', text):
                                nm = m.group(1)
                                if nm:
                                    names.append((nm.strip().lower().replace("_", "-"), False))
                        except Exception:
                            pass
                except Exception:
                    pass
                return names

            for lock in lock_files:
                for nm, is_dev in _scan_pypi_lock(lock):
                    _merge(nm, "transitive", "required", "development" if is_dev else "normal")

            return result

        if eco == Ecosystem.MAVEN:
            pom_files = []
            if args.RECURSIVE:
                for root, _, files in _os.walk(base_dir):
                    if Constants.POM_XML_FILE in files:
                        pom_files.append(_os.path.join(root, Constants.POM_XML_FILE))
            else:
                path = _os.path.join(base_dir, Constants.POM_XML_FILE)
                if _os.path.isfile(path):
                    pom_files.append(path)
            import xml.etree.ElementTree as _ET
            ns = ".//{http://maven.apache.org/POM/4.0.0}"
            for pom_path in pom_files:
                try:
                    tree = _ET.parse(pom_path)
                    pom = tree.getroot()
                    for dependencies in pom.findall(f"{ns}dependencies"):
                        for dependency in dependencies.findall(f"{ns}dependency"):
                            gid = dependency.find(f"{ns}groupId")
                            aid = dependency.find(f"{ns}artifactId")
                            if gid is None or gid.text is None or aid is None or aid.text is None:
                                continue
                            scope_node = dependency.find(f"{ns}scope")
                            scope = (scope_node.text.strip().lower() if scope_node is not None and scope_node.text else "")
                            scope_val = "testing" if scope == "test" else "normal"
                            opt_node = dependency.find(f"{ns}optional")
                            req_val = "optional" if (opt_node is not None and (opt_node.text or "").strip().lower() == "true") else "required"
                            coordinate = f"{gid.text}:{aid.text}"
                            _merge(coordinate, "direct", req_val, scope_val)
                            _merge(aid.text, "direct", req_val, scope_val)  # artifactId fallback
                except Exception:
                    continue
            return result

        return result
    except Exception:
        return {}

def main():
    """Main function of the program."""
    # pylint: disable=too-many-branches, too-many-statements, too-many-nested-blocks
    logger = logging.getLogger(__name__)

    args = parse_args()
    # Honor CLI --loglevel by passing it to centralized logger via env
    if getattr(args, "LOG_LEVEL", None):
        os.environ['DEPGATE_LOG_LEVEL'] = str(args.LOG_LEVEL).upper()
    configure_logging()
    # Ensure runtime CLI flag wins regardless of environment defaults
    try:
        _level_name = str(args.LOG_LEVEL).upper()
        _level_value = getattr(logging, _level_name, logging.INFO)
        logging.getLogger().setLevel(_level_value)
    except (ValueError, AttributeError, TypeError):
        # Defensive: never break CLI on logging setup
        pass

    # Apply CLI overrides for deps.dev feature and tunables (CLI has highest precedence)
    try:
        if getattr(args, "DEPSDEV_DISABLE", False):
            Constants.DEPSDEV_ENABLED = False  # type: ignore[attr-defined]
        if getattr(args, "DEPSDEV_BASE_URL", None):
            Constants.DEPSDEV_BASE_URL = args.DEPSDEV_BASE_URL  # type: ignore[attr-defined]
        if getattr(args, "DEPSDEV_CACHE_TTL", None) is not None:
            Constants.DEPSDEV_CACHE_TTL_SEC = int(args.DEPSDEV_CACHE_TTL)  # type: ignore[attr-defined]
        if getattr(args, "DEPSDEV_MAX_CONCURRENCY", None) is not None:
            Constants.DEPSDEV_MAX_CONCURRENCY = int(args.DEPSDEV_MAX_CONCURRENCY)  # type: ignore[attr-defined]
        if getattr(args, "DEPSDEV_MAX_RESPONSE_BYTES", None) is not None:
            Constants.DEPSDEV_MAX_RESPONSE_BYTES = int(args.DEPSDEV_MAX_RESPONSE_BYTES)  # type: ignore[attr-defined]
        if getattr(args, "DEPSDEV_STRICT_OVERRIDE", False):
            Constants.DEPSDEV_STRICT_OVERRIDE = True  # type: ignore[attr-defined]
    except Exception:
        # Defensive: never break CLI on config overrides
        pass

    if is_debug_enabled(logger):
        logger.debug(
            "CLI start",
            extra=extra_context(event="function_entry", component="cli", action="main")
        )

    logging.info("Arguments parsed.")

    logging.info(r"""
┬─┐ ┬─┐ ┬─┐ ┌─┐ ┬─┐ ┌┐┐ ┬─┐
│ │ │─  │─┘ │ ┬ │─┤  │  │─
──┘ ┴─┘ ┴   │─┘ ┘ │  ┘  ┴─┘

  Dependency Supply-Chain/Confusion Risk Checker
""")

    pkglist = build_pkglist(args)
    if is_debug_enabled(logging.getLogger(__name__)):
        logging.getLogger(__name__).debug(
            "Built package list",
            extra=extra_context(
                event="decision",
                component="cli",
                action="build_pkglist",
                outcome="empty" if not pkglist else "non_empty",
                count=len(pkglist) if isinstance(pkglist, list) else 0
            )
        )
    if not pkglist or not isinstance(pkglist, list):
        logging.warning("No packages found in the input list.")
        if is_debug_enabled(logging.getLogger(__name__)):
            logging.getLogger(__name__).debug(
                "CLI finished (no packages)",
                extra=extra_context(
                    event="function_exit",
                    component="cli",
                    action="main",
                    outcome="no_packages"
                )
            )
        if is_debug_enabled(logging.getLogger(__name__)):
            logging.getLogger(__name__).debug(
                "CLI finished",
                extra=extra_context(
                    event="function_exit",
                    component="cli",
                    action="main",
                    outcome="success"
                )
            )
        sys.exit(ExitCodes.SUCCESS.value)

    logging.info("Package list imported: %s", str(pkglist))

    create_metapackages(args, pkglist)

    # Auto-classify dependency relation/scope/requirement for source scans
    try:
        if getattr(args, "FROM_SRC", None):
            _class_map = build_dependency_classification(args)
            if isinstance(_class_map, dict):
                _eco = _to_ecosystem(args.package_type)
                for mp in metapkg.instances:
                    keys = []
                    if _eco == Ecosystem.MAVEN and getattr(mp, "org_id", None):
                        keys.append(f"{mp.org_id}:{mp.pkg_name}")
                        keys.append(mp.pkg_name)  # artifactId fallback
                    elif _eco == Ecosystem.PYPI:
                        keys.append(mp.pkg_name.lower().replace("_", "-"))
                    else:
                        keys.append(mp.pkg_name)
                    for k in keys:
                        hit = _class_map.get(k)
                        if hit:
                            try:
                                mp.dependency_relation = hit.get("relation")
                                mp.dependency_requirement = hit.get("requirement")
                                mp.dependency_scope = hit.get("scope")
                            except Exception:
                                pass
                            break
    except Exception:
        # best-effort; never fail CLI on classification
        pass

    # VERSION RESOLUTION (pre-enrichment)
    try:
        eco = _to_ecosystem(args.package_type)
        requests = build_version_requests(args, pkglist)
        if requests:
            svc = VersionResolutionService(TTLCache())
            res_map = svc.resolve_all(requests)
            for mp in metapkg.instances:
                # Build identifier key per ecosystem
                if eco == Ecosystem.MAVEN and getattr(mp, "org_id", None):
                    ident = f"{mp.org_id}:{mp.pkg_name}"
                elif eco == Ecosystem.PYPI:
                    ident = mp.pkg_name.lower().replace("_", "-")
                else:
                    ident = mp.pkg_name
                key = (eco, ident)
                rr = res_map.get(key)
                if not rr:
                    # Fallback: try raw name mapping if normalization differs
                    rr = next((v for (k_ec, k_id), v in res_map.items() if k_ec == eco and k_id == mp.pkg_name), None)
                if rr:
                    mp.requested_spec = rr.requested_spec
                    mp.resolved_version = rr.resolved_version
                    mp.resolution_mode = (
                        rr.resolution_mode.value
                        if hasattr(rr.resolution_mode, "value")
                        else rr.resolution_mode
                    )
    except Exception:  # pylint: disable=broad-exception-caught
        # Do not fail CLI if resolution errors occur; continue with legacy behavior
        pass

    # QUERY & POPULATE
    if is_debug_enabled(logging.getLogger(__name__)):
        logging.getLogger(__name__).debug(
            "Checking against registry",
            extra=extra_context(
                event="function_entry",
                component="cli",
                action="check_against",
                target=args.package_type,
                outcome="starting"
            )
        )
    check_against(args.package_type, args.LEVEL, metapkg.instances)
    if is_debug_enabled(logging.getLogger(__name__)):
        logging.getLogger(__name__).debug(
            "Finished checking against registry",
            extra=extra_context(
                event="function_exit",
                component="cli",
                action="check_against",
                target=args.package_type,
                outcome="completed"
            )
        )

    # ANALYZE
    run_analysis(args.LEVEL, args)

    # OUTPUT
    if getattr(args, "OUTPUT", None):
        fmt = None
        if getattr(args, "OUTPUT_FORMAT", None):
            fmt = args.OUTPUT_FORMAT.lower()
        else:
            lower = args.OUTPUT.lower()
            if lower.endswith(".json"):
                fmt = "json"
            elif lower.endswith(".csv"):
                fmt = "csv"
        if fmt is None:
            fmt = "json"
        if fmt == "csv":
            export_csv(metapkg.instances, args.OUTPUT)
        else:
            export_json(metapkg.instances, args.OUTPUT)

    # Check if any package was not found
    has_risk = any(x.has_risk() for x in metapkg.instances)
    if has_risk:
        logging.warning("One or more packages have identified risks.")
        if args.ERROR_ON_WARNINGS:
            logging.error("Warnings present, exiting with non-zero status code.")
            sys.exit(ExitCodes.EXIT_WARNINGS.value)

    sys.exit(ExitCodes.SUCCESS.value)

if __name__ == "__main__":
    main()
