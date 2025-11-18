"""CLI Registry utilities."""

import logging
import sys

from constants import ExitCodes, PackageManagers


def scan_source(pkgtype, dir_name, recursive=False, direct_only=False, require_lockfile=False):
    """Scans the source directory for packages.

    Args:
        pkgtype: Package manager type (npm, pypi, maven, nuget)
        dir_name: Directory to scan
        recursive: Whether to scan recursively
        direct_only: If True, only scan direct dependencies from manifests (default: False)
        require_lockfile: If True, require a lockfile for package managers that support it (default: False)
    """
    if pkgtype == PackageManagers.NPM.value:
        from registry import npm as _npm  # pylint: disable=import-outside-toplevel
        return _npm.scan_source(dir_name, recursive, direct_only=direct_only, require_lockfile=require_lockfile)
    if pkgtype == PackageManagers.MAVEN.value:
        from registry import maven as _maven  # pylint: disable=import-outside-toplevel
        return _maven.scan_source(dir_name, recursive, direct_only=direct_only, require_lockfile=require_lockfile)
    if pkgtype == PackageManagers.PYPI.value:
        from registry import pypi as _pypi  # pylint: disable=import-outside-toplevel
        return _pypi.scan_source(dir_name, recursive, direct_only=direct_only, require_lockfile=require_lockfile)
    if pkgtype == PackageManagers.NUGET.value:
        from registry import nuget as _nuget  # pylint: disable=import-outside-toplevel
        return _nuget.scan_source(dir_name, recursive, direct_only=direct_only, require_lockfile=require_lockfile)
    logging.error("Selected package type doesn't support import scan.")
    sys.exit(ExitCodes.FILE_ERROR.value)


def check_against(check_type, _level, check_list):
    """Checks the packages against the registry."""
    if check_type == PackageManagers.NPM.value:
        # Fetch details for all levels (fix regression where repo fields were empty on compare)
        should_fetch_details = True
        from registry import npm as _npm  # pylint: disable=import-outside-toplevel
        _npm.recv_pkg_info(check_list, should_fetch_details)
    elif check_type == PackageManagers.MAVEN.value:
        from registry import maven as _maven  # pylint: disable=import-outside-toplevel
        _maven.recv_pkg_info(check_list)
    elif check_type == PackageManagers.PYPI.value:
        from registry import pypi as _pypi  # pylint: disable=import-outside-toplevel
        _pypi.recv_pkg_info(check_list)
    elif check_type == PackageManagers.NUGET.value:
        from registry import nuget as _nuget  # pylint: disable=import-outside-toplevel
        _nuget.recv_pkg_info(check_list)
    else:
        logging.error("Selected package type doesn't support registry check.")
        sys.exit(ExitCodes.FILE_ERROR.value)
