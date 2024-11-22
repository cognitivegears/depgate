"""Combobulator - Dependency Confusion Checker

    Raises:
        TypeError: If the input list cannot be processed

    Returns:
        int: Exit code
"""
import csv
import sys
import logging

# internal module imports
from metapackage import MetaPackage as metapkg
from registry import npm
from registry import maven
from registry import pypi
from analysis import heuristics as heur
from constants import ExitCodes, PackageManagers, Constants  # Import Constants including LOG_FORMAT
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
        dir (str): Directory path to scan.
        recursive (bool, optional): Option to recurse into subdirectories. Defaults to False.

    Returns:
        list: List of packages found in the source directory.
    """
    if pkgtype == PackageManagers.NPM.value:
        return npm.scan_source(dir_name, recursive)
    elif pkgtype == PackageManagers.MAVEN.value:
        return maven.scan_source(dir_name, recursive)
    elif pkgtype == PackageManagers.PYPI.value:
        return pypi.scan_source(dir_name, recursive)
    else:
        logging.error("Selected package type doesn't support import scan.")
        sys.exit(ExitCodes.FILE_ERROR.value)

def check_against(check_type, level, check_list):
    """Checks the packages against the registry.

    Args:
        check_type (str): Package manager type, i.e. "npm".
        check_list (list): List of packages to check.
    """
    
    
    if check_type == PackageManagers.NPM.value:
        # Only fetch details for levels 1 and 2
        should_fetch_details = level in (Constants.LEVELS[2], Constants.LEVELS[3])
        npm.recv_pkg_info(check_list, should_fetch_details)
    elif check_type == PackageManagers.MAVEN.value:
        maven.recv_pkg_info(check_list)
    elif check_type == PackageManagers.PYPI.value:
        pypi.recv_pkg_info(check_list)
    else:
        logging.error("Selected package type doesn't support registry check.")
        sys.exit(ExitCodes.FILE_ERROR.value)

def export_csv(instances, path):
    """Exports the package properties to a CSV file.

    Args:
        instances (list): List of package instances.
        path (str): File path to export the CSV.
    """
    headers = ["Package Name","Package Type", "Exists on External",
            "Org/Group ID","Score","Version Count","Timestamp"]
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

def main():
    """Main function of the program."""
    # the most important part of any program starts here

    args = parse_args()

    # Configure logging
    log_level = getattr(logging, args.LOG_LEVEL.upper(), logging.INFO)
    if '-h' in sys.argv or '--help' in sys.argv:
        # Ensure help output is always at INFO level
        logging.basicConfig(level=logging.INFO, format=Constants.LOG_FORMAT)
    else:
        if args.LOG_FILE:
            logging.basicConfig(filename=args.LOG_FILE, level=log_level,
                                format=Constants.LOG_FORMAT)  # Used LOG_FORMAT constant
        else:
            logging.basicConfig(level=log_level,
                                format=Constants.LOG_FORMAT)  # Used LOG_FORMAT constant

    logging.info("Arguments parsed.")

    # Logging the ASCII art banner
    logging.info(r"""
  ____  _____ ____  _____ _   _ ____  _____ _   _  ______   __
 |  _ \| ____|  _ \| ____| \ | |  _ \| ____| \ | |/ ___\ \ / /
 | | | |  _| | |_) |  _| |  \| | | | |  _| |  \| | |    \ V / 
 | |_| | |___|  __/| |___| |\  | |_| | |___| |\  | |___  | |  
 |____/|_____|_|   |_____|_| \_|____/|_____|_| \_|\____| |_|  

   ____ ____  __  __ ____   ____  ____  _   _ _        _  _____ ____  ____  
  / ___/ /\ \|  \/  | __ ) / /\ \| __ )| | | | |      / \|_   _/ /\ \|  _ \ 
 | |  / /  \ \ |\/| |  _ \/ /  \ \  _ \| | | | |     / _ \ | |/ /  \ \ |_) |
 | |__\ \  / / |  | | |_) \ \  / / |_) | |_| | |___ / ___ \| |\ \  / /  _ < 
  \____\_\/_/|_|  |_|____/ \_\/_/|____/ \___/|_____/_/   \_\_| \_\/_/|_| \_\
""")

    # are you amazed yet?

    # SCAN & FLAG ARGS

    # Check if recursive option is used without directory
    if args.RECURSIVE and not args.FROM_SRC:
        logging.warning("Recursive option is only applicable to source scans.")

    #IMPORT
    if args.LIST_FROM_FILE:
        pkglist = load_pkgs_file(args.LIST_FROM_FILE[0])
    elif args.FROM_SRC:
        pkglist = scan_source(args.package_type, args.FROM_SRC[0], recursive=args.RECURSIVE)
    elif args.SINGLE:
        pkglist = []
        pkglist.append(args.SINGLE[0])

    if not pkglist or not isinstance(pkglist, list):
        logging.warning("No packages found in the input list.")
        sys.exit(ExitCodes.SUCCESS.value)

    logging.info("Package list imported: %s", str(pkglist))

    if args.package_type == PackageManagers.NPM.value:
        for pkg in pkglist:
            metapkg(pkg, args.package_type)
    elif args.package_type == PackageManagers.MAVEN.value:
        for pkg in pkglist: # format org_id:package_id
            metapkg(pkg.split(':')[1], args.package_type, pkg.split(':')[0])
    elif args.package_type == PackageManagers.PYPI.value:
        for pkg in pkglist:
            metapkg(pkg, args.package_type)

    # QUERY & POPULATE
    check_against(args.package_type, args.LEVEL, metapkg.instances)

    # ANALYZE
    if args.LEVEL in (Constants.LEVELS[0], Constants.LEVELS[1]):
        heur.combobulate_min(metapkg.instances)
    elif args.LEVEL in (Constants.LEVELS[2], Constants.LEVELS[3]):
        heur.combobulate_heur(metapkg.instances)

    # OUTPUT
    if args.CSV:
        export_csv(metapkg.instances, args.CSV)

    # Check if any package was not found
    not_found = any(not x.exists for x in metapkg.instances)
    if not_found:
        logging.warning("One or more packages were not found.")
        if args.ERROR_ON_WARNINGS:
            logging.error("Warnings present, exiting with non-zero status code.")
            sys.exit(ExitCodes.PACKAGE_NOT_FOUND.value)

    sys.exit(ExitCodes.SUCCESS.value)

if __name__ == "__main__":
    main()
