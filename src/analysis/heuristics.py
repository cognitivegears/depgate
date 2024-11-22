"""Heuristics for package analysis."""
import time
import logging  # Added import
from constants import Constants, DefaultHeuristics

STG = f"{Constants.ANALYSIS} "

def combobulate_min(pkgs):
    """Run to check the existence of the packages in the registry.

    Args:
        pkgs (list): List of packages to check.
    """
    for x in pkgs:
        test_exists(x)

def combobulate_heur(pkgs):
    """Run heuristics on the packages.

    Args:
        pkgs (list): List of packages to check.
    """
    for x in pkgs:
        test_exists(x)
        if x.exists is True:
            test_score(x)
            test_timestamp(x)
            test_version_count(x)
    stats_exists(pkgs)

def test_exists(x):
    """Check if the package exists on the public provider.

    Args:
        x (str): Package to check.
    """
    if x.exists is True:
        logging.info("%sPackage: %s is present on public provider.", STG, x)
        x.risk_missing = False
    elif x.exists is False:
        logging.warning("%sPackage: %s is NOT present on public provider.", STG, x)
        x.risk_missing = True
    else:
        logging.info("%sPackage: %s test skipped.", STG, x)

def test_score(x):
    """Check the score of the package.

    Args:
        x (str): Package to check.
    """
    ttxt = ". Mid set to " + str(DefaultHeuristics.SCORE_THRESHOLD.value) + ")"
    if x.score is not None:
        if x.score > DefaultHeuristics.SCORE_THRESHOLD.value:
            logging.info("%s.... package scored ABOVE MID - %s%s",
                STG, str(x.score), ttxt)
            x.risk_low_score = False
        elif x.score <= DefaultHeuristics.SCORE_THRESHOLD.value and x.score > DefaultHeuristics.RISKY_THRESHOLD.value:
            logging.warning("%s.... [RISK] package scored BELOW MID - %s%s",
                STG, str(x.score), ttxt)
            x.risk_low_score = False
        elif x.score <= DefaultHeuristics.RISKY_THRESHOLD.value:
            logging.warning("%s.... [RISK] package scored LOW - %s%s", STG, str(x.score), ttxt)
            x.risk_low_score = True

def test_timestamp(x):
    """Check the timestamp of the package.

    Args:
        x (str): Package to check.
    """
    if x.timestamp is not None:
        dayspast = (time.time()*1000 - x.timestamp)/86400000
        logging.info("%s.... package is %d days old.", STG, int(dayspast))
        if dayspast < 2:  # freshness test
            logging.warning("%s.... [RISK] package is SUSPICIOUSLY NEW.", STG)
            x.risk_too_new = True
        else:
            logging.debug("%s.... package is not suspiciously new.", STG)
            x.risk_too_new = False

def stats_exists(pkgs):
    """Summarize the existence of the packages on the public provider.

    Args:
        pkgs (list): List of packages to check.
    """
    count = sum(1 for x in pkgs if x.exists is True)
    total = len(pkgs)
    percentage = (count / total) * 100 if total > 0 else 0
    logging.info("%s%d out of %d packages were present on the public provider (%.2f%% of total).",
                 STG, count, total, percentage)

def test_version_count(pkg):
    """Check the version count of the package.

    Args:
        pkg (str): Package to check.
    """
    if pkg.version_count is not None:
        if pkg.version_count < 2:
            logging.warning("%s.... [RISK] package history is SHORT. Total %d versions committed.",
                            STG, pkg.version_count)
            pkg.risk_min_versions = True
        else:
            logging.info("%s.... Total %d versions committed.", STG, pkg.version_count)
            pkg.risk_min_versions = False
    else:
        logging.warning("%s.... Package version count not available.", STG)
