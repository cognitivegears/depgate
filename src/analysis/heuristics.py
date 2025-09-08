"""Heuristics for package analysis."""
import time
import logging  # Added import
import math
from datetime import datetime, timezone
from constants import Constants, DefaultHeuristics

STG = f"{Constants.ANALYSIS} "
# Repository signals scoring constants
REPO_SCORE_VERSION_MATCH_POSITIVE = 15
REPO_SCORE_VERSION_MATCH_NEGATIVE = -8
REPO_SCORE_RESOLVED_EXISTS_POSITIVE = 8
REPO_SCORE_RESOLVED_UNKNOWN_POSITIVE = 3
REPO_SCORE_RESOLVED_NOT_EXISTS_NEGATIVE = -5
REPO_SCORE_PRESENT_IN_REGISTRY = 2
REPO_SCORE_ACTIVITY_RECENT = 6
REPO_SCORE_ACTIVITY_MEDIUM = 3
REPO_SCORE_ACTIVITY_OLD = 1
REPO_SCORE_ACTIVITY_STALE = -2
REPO_SCORE_MAX_STARS_CONTRIBUTORS = 4
REPO_SCORE_CLAMP_MIN = -20
REPO_SCORE_CLAMP_MAX = 30

def compute_repo_signals_score(mp):
    """Compute repository signals score contribution.

    Args:
        mp: MetaPackage instance with repository fields

    Returns:
        float: Repository signals score contribution, clamped to [-20, +30]
    """
    score = 0

    # Version match scoring
    if mp.repo_version_match:
        if mp.repo_version_match.get('matched', False):
            score += REPO_SCORE_VERSION_MATCH_POSITIVE
        elif mp.repo_exists is True:
            # Repo exists but no version match found after checking
            score += REPO_SCORE_VERSION_MATCH_NEGATIVE

    # Repository resolution and existence scoring
    if mp.repo_resolved:
        if mp.repo_exists is True:
            score += REPO_SCORE_RESOLVED_EXISTS_POSITIVE
        elif mp.repo_exists is False:
            score += REPO_SCORE_RESOLVED_NOT_EXISTS_NEGATIVE
        elif mp.repo_exists is None:
            score += REPO_SCORE_RESOLVED_UNKNOWN_POSITIVE

    # Present in registry scoring
    if mp.repo_present_in_registry:
        score += REPO_SCORE_PRESENT_IN_REGISTRY

    # Last activity recency scoring
    if mp.repo_last_activity_at:
        try:
            # Parse ISO 8601 timestamp
            if isinstance(mp.repo_last_activity_at, str):
                # Handle different ISO 8601 formats
                if mp.repo_last_activity_at.endswith('Z'):
                    activity_dt = datetime.fromisoformat(mp.repo_last_activity_at[:-1])
                else:
                    activity_dt = datetime.fromisoformat(mp.repo_last_activity_at)

                # Ensure timezone awareness
                if activity_dt.tzinfo is None:
                    activity_dt = activity_dt.replace(tzinfo=timezone.utc)

                now = datetime.now(timezone.utc)
                days_since_activity = (now - activity_dt).days

                if days_since_activity <= 90:
                    score += REPO_SCORE_ACTIVITY_RECENT
                elif days_since_activity <= 365:
                    score += REPO_SCORE_ACTIVITY_MEDIUM
                elif days_since_activity <= 730:
                    score += REPO_SCORE_ACTIVITY_OLD
                else:
                    score += REPO_SCORE_ACTIVITY_STALE
        except (ValueError, AttributeError):
            # If parsing fails, treat as unknown (0 points)
            pass

    # Stars scoring (log scale)
    if mp.repo_stars is not None:
        stars_score = min(REPO_SCORE_MAX_STARS_CONTRIBUTORS,
                         math.floor(math.log10(max(1, mp.repo_stars)) + 1))
        score += stars_score

    # Contributors scoring (log scale)
    if mp.repo_contributors is not None:
        contributors_score = min(REPO_SCORE_MAX_STARS_CONTRIBUTORS,
                                math.floor(math.log10(max(1, mp.repo_contributors)) + 1))
        score += contributors_score

    # Clamp the final score
    return max(REPO_SCORE_CLAMP_MIN, min(REPO_SCORE_CLAMP_MAX, score))
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
            # Add repository signals score to existing score
            repo_score = compute_repo_signals_score(x)
            if x.score is not None:
                x.score += repo_score
            else:
                x.score = repo_score
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
        elif (
            x.score <= DefaultHeuristics.SCORE_THRESHOLD.value
            and x.score > DefaultHeuristics.RISKY_THRESHOLD.value
        ):
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
