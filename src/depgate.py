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

# internal module imports (kept light to avoid heavy deps on --help)
from metapackage import MetaPackage as metapkg
from constants import ExitCodes, PackageManagers, Constants
from common.logging_utils import configure_logging, extra_context, is_debug_enabled
from args import parse_args

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
        # Only fetch details for levels 1 and 2
        should_fetch_details = level in (Constants.LEVELS[2], Constants.LEVELS[3])
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
        "repo_stars",
        "repo_contributors",
        "repo_last_activity",
        "repo_present_in_registry",
        "repo_version_match",
    ]
    rows = [headers]
    for x in instances:
        rows.append(x.listall())
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
            "repo_present_in_registry": (None if (getattr(x, "repo_url_normalized", None) is None and x.repo_present_in_registry is False) else x.repo_present_in_registry),
            "repo_version_match": x.repo_version_match,
            "risk": {
                "hasRisk": x.has_risk(),
                "isMissing": x.risk_missing,
                "hasLowScore": x.risk_low_score,
                "minVersions": x.risk_min_versions,
                "isNew": x.risk_too_new
            }
        })
    try:
        with open(path, 'w', encoding='utf-8') as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
        logging.info("JSON file has been successfully exported at: %s", path)
    except OSError as e:
        logging.error("JSON file couldn't be written to disk: %s", e)
        sys.exit(1)



def build_pkglist(args):
    """Build the package list from CLI inputs."""
    if args.RECURSIVE and not args.FROM_SRC:
        logging.warning("Recursive option is only applicable to source scans.")
    if args.LIST_FROM_FILE:
        return load_pkgs_file(args.LIST_FROM_FILE[0])
    if args.FROM_SRC:
        return scan_source(args.package_type, args.FROM_SRC[0], recursive=args.RECURSIVE)
    if args.SINGLE:
        return [args.SINGLE[0]]
    return []

def create_metapackages(args, pkglist):
    """Create MetaPackage instances from the package list."""
    if args.package_type == PackageManagers.NPM.value:
        for pkg in pkglist:
            metapkg(pkg, args.package_type)
    elif args.package_type == PackageManagers.MAVEN.value:
        for pkg in pkglist:  # format org_id:package_id
            metapkg(pkg.split(':')[1], args.package_type, pkg.split(':')[0])
    elif args.package_type == PackageManagers.PYPI.value:
        for pkg in pkglist:
            metapkg(pkg, args.package_type)

def run_analysis(level):
    """Run the selected analysis for collected packages."""
    if level in (Constants.LEVELS[0], Constants.LEVELS[1]):
        from analysis import heuristics as _heur  # pylint: disable=import-outside-toplevel
        _heur.run_min_analysis(metapkg.instances)
    elif level in (Constants.LEVELS[2], Constants.LEVELS[3]):
        from analysis import heuristics as _heur  # pylint: disable=import-outside-toplevel
        _heur.run_heuristics(metapkg.instances)
def main():
    """Main function of the program."""
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
    except Exception:  # defensive: never break CLI on logging setup
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
    run_analysis(args.LEVEL)

    # OUTPUT
    if args.CSV:
        export_csv(metapkg.instances, args.CSV)
    if args.JSON:
        export_json(metapkg.instances, args.JSON)

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
