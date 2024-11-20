"""Constants used in the project."""

from enum import Enum


class ExitCodes(Enum):
    """Exit codes for the program.

    Args:
        Enum (int): Exit codes for the program.
    """

    SUCCESS = 0
    CONNECTION_ERROR = 2
    FILE_ERROR = 1
    PACKAGE_NOT_FOUND = 3


class PackageManagers(Enum):
    """Package managers supported by the program.

    Args:
        Enum (string): Package managers supported by the program.
    """

    NPM = "npm"
    PYPI = "pypi"
    MAVEN = "maven"


class Constants:
    """General constants used in the project."""

    REGISTRY_URL_PYPI = "https://pypi.org/pypi/"
    REGISTRY_URL_NPM = "https://api.npms.io/v2/package/mget"
    REGISTRY_URL_MAVEN = "https://search.maven.org/solrsearch/select"
    SUPPORTED_PACKAGES = [
        PackageManagers.NPM.value,
        PackageManagers.PYPI.value,
        PackageManagers.MAVEN.value,
    ]
    LEVELS = ["compare", "comp", "heuristics", "heur"]
    REQUIREMENTS_FILE = "requirements.txt"
    PACKAGE_JSON_FILE = "package.json"
    POM_XML_FILE = "pom.xml"
    LOG_FORMAT = "[%(levelname)s] %(message)s"  # Added LOG_FORMAT constant
    ANALYSIS = "[ANALYSIS]"
    REQUEST_TIMEOUT = 30  # Timeout in seconds for all HTTP requests