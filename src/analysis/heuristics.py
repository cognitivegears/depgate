"""Heuristics for package analysis."""
import time
import logging  # Added import
import math
from datetime import datetime, timezone
from constants import Constants, DefaultHeuristics
from common.logging_utils import is_debug_enabled, extra_context

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

def _score_version_match(mp) -> int:
    """Score version match: +positive if matched; -negative if repo exists but unmatched."""
    vm = getattr(mp, "repo_version_match", None)
    if not vm:
        return 0
    try:
        if bool(vm.get("matched", False)):
            return REPO_SCORE_VERSION_MATCH_POSITIVE
        if getattr(mp, "repo_exists", None) is True:
            return REPO_SCORE_VERSION_MATCH_NEGATIVE
    except (AttributeError, TypeError):
        return 0
    return 0


def _score_resolution(mp) -> int:
    """Score repository resolution/existence signals."""
    if not getattr(mp, "repo_resolved", False):
        return 0
    exists = getattr(mp, "repo_exists", None)
    if exists is True:
        return REPO_SCORE_RESOLVED_EXISTS_POSITIVE
    if exists is False:
        return REPO_SCORE_RESOLVED_NOT_EXISTS_NEGATIVE
    if exists is None:
        return REPO_SCORE_RESOLVED_UNKNOWN_POSITIVE
    return 0


def _score_presence(mp) -> int:
    """Score presence-in-registry metadata."""
    return REPO_SCORE_PRESENT_IN_REGISTRY if getattr(mp, "repo_present_in_registry", False) else 0


def _score_activity(mp) -> int:
    """Score last-activity recency."""
    iso = getattr(mp, "repo_last_activity_at", None)
    if not iso or not isinstance(iso, str):
        return 0
    try:
        if iso.endswith("Z"):
            activity_dt = datetime.fromisoformat(iso[:-1])
        else:
            activity_dt = datetime.fromisoformat(iso)
        if activity_dt.tzinfo is None:
            activity_dt = activity_dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        days = (now - activity_dt).days
        if days <= 90:
            return REPO_SCORE_ACTIVITY_RECENT
        if days <= 365:
            return REPO_SCORE_ACTIVITY_MEDIUM
        if days <= 730:
            return REPO_SCORE_ACTIVITY_OLD
        return REPO_SCORE_ACTIVITY_STALE
    except (ValueError, AttributeError, TypeError):
        return 0


def _score_engagement(mp) -> int:
    """Score stars and contributors on a log scale (bounded)."""
    total = 0
    stars = getattr(mp, "repo_stars", None)
    if stars is not None:
        try:
            total += min(
                REPO_SCORE_MAX_STARS_CONTRIBUTORS,
                math.floor(math.log10(max(1, stars)) + 1),
            )
        except (ValueError, TypeError):
            pass
    contrib = getattr(mp, "repo_contributors", None)
    if contrib is not None:
        try:
            total += min(
                REPO_SCORE_MAX_STARS_CONTRIBUTORS,
                math.floor(math.log10(max(1, contrib)) + 1),
            )
        except (ValueError, TypeError):
            pass
    return total


def compute_repo_signals_score(mp):
    """Compute repository signals score contribution.

    Args:
        mp: MetaPackage instance with repository fields

    Returns:
        float: Repository signals score contribution, clamped to [-20, +30]
    """
    score = (
        _score_version_match(mp)
        + _score_resolution(mp)
        + _score_presence(mp)
        + _score_activity(mp)
        + _score_engagement(mp)
    )
    return max(REPO_SCORE_CLAMP_MIN, min(REPO_SCORE_CLAMP_MAX, score))

def _clamp01(value):
    """Clamp a numeric value into [0.0, 1.0]."""
    try:
        v = float(value)
    except (ValueError, TypeError):
        return 0.0
    return 0.0 if v < 0.0 else 1.0 if v > 1.0 else v

def _norm_base_score(base):
    """Normalize an existing base score (already expected to be 0..1, but clamp defensively)."""
    if base is None:
        return None
    try:
        return _clamp01(float(base))
    except (ValueError, TypeError):
        return None

def _norm_repo_stars(stars):
    """Normalize repository stars to [0,1] using a log scale that saturates around 10^3."""
    if stars is None:
        return None
    try:
        s = float(stars)
        if s < 0:
            s = 0.0
        # Matches design: min(1.0, log10(stars+1)/3.0) — ~1.0 around 1k stars
        return min(1.0, max(0.0, math.log10(s + 1.0) / 3.0))
    except (ValueError, TypeError):
        return None

def _norm_repo_contributors(contrib):
    """Normalize repository contributors to [0,1], saturating at ~50 contributors."""
    if contrib is None:
        return None
    try:
        c = float(contrib)
        if c < 0:
            c = 0.0
        return min(1.0, max(0.0, c / 50.0))
    except (ValueError, TypeError):
        return None

def _parse_iso_to_days(iso_ts):
    """Parse ISO-8601 timestamp and return days since that time (int)."""
    try:
        if isinstance(iso_ts, str):
            if iso_ts.endswith('Z'):
                dt = datetime.fromisoformat(iso_ts[:-1])
            else:
                dt = datetime.fromisoformat(iso_ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            return (now - dt).days
    except (ValueError, TypeError):
        return None
    return None

def _norm_repo_last_activity(iso_ts):
    """Normalize last activity recency into [0,1] using tiered thresholds."""
    if not iso_ts:
        return None
    days = _parse_iso_to_days(iso_ts)
    if days is None:
        return None
    if days <= 30:
        return 1.0
    if days <= 365:
        return 0.6
    if days <= 730:
        return 0.3
    return 0.0

def _norm_bool(flag):
    """Normalize boolean to [0,1]; None -> None (missing)."""
    if flag is None:
        return None
    return 1.0 if bool(flag) else 0.0

def _norm_version_match(vm):
    """Normalize version match dict to [0,1]. True match => 1.0; else 0.0; None => missing."""
    if vm is None:
        return None
    try:
        return 1.0 if bool(vm.get('matched', False)) else 0.0
    except (AttributeError, TypeError):
        return None

def compute_final_score(mp):
    """Compute the final normalized score in [0,1] with per-heuristic breakdown and weights.

    Normalized inputs (each in [0,1], None if missing):
      - base_score (existing pkg.score if provided)
      - repo_version_match
      - repo_stars
      - repo_contributors
      - repo_last_activity
      - repo_present_in_registry

    Default weights (sum to 1.0 when all present; re-normalized when some are missing):
      - base_score: 0.30
      - repo_version_match: 0.30
      - repo_stars: 0.15
      - repo_contributors: 0.10
      - repo_last_activity: 0.10
      - repo_present_in_registry: 0.05

    Returns:
      tuple(final_score: float, breakdown: dict, weights_used: dict)
    """
    # Raw values
    raw = {
        'base_score': getattr(mp, 'score', None),
        'repo_version_match': getattr(mp, 'repo_version_match', None),
        'repo_stars': getattr(mp, 'repo_stars', None),
        'repo_contributors': getattr(mp, 'repo_contributors', None),
        'repo_last_activity': getattr(mp, 'repo_last_activity_at', None),
        'repo_present_in_registry': getattr(mp, 'repo_present_in_registry', None),
    }

    # Normalized values
    norm = {
        'base_score': _norm_base_score(raw['base_score']),
        'repo_version_match': _norm_version_match(raw['repo_version_match']),
        'repo_stars': _norm_repo_stars(raw['repo_stars']),
        'repo_contributors': _norm_repo_contributors(raw['repo_contributors']),
        'repo_last_activity': _norm_repo_last_activity(raw['repo_last_activity']),
        # Treat default/unknown False as missing to avoid penalizing base-only scenarios
        'repo_present_in_registry': _norm_bool(raw['repo_present_in_registry']),
    }
    # If present_in_registry is False (normalized 0.0) and no normalized repo URL exists,
    # consider it missing (None) for scoring/weight renormalization purposes.
    if norm['repo_present_in_registry'] == 0.0 and getattr(mp, 'repo_url_normalized', None) is None:
        norm['repo_present_in_registry'] = None

    # Configurable weights loaded from Constants (overridable via YAML)
    weights = dict(getattr(Constants, "HEURISTICS_WEIGHTS", {
        'base_score': 0.30,
        'repo_version_match': 0.30,
        'repo_stars': 0.15,
        'repo_contributors': 0.10,
        'repo_last_activity': 0.10,
        'repo_present_in_registry': 0.05,
    }))

    # Re-normalize weights to only those metrics that are present (norm != None)
    available = [k for k, v in norm.items() if v is not None]
    total_w = sum(weights.get(k, 0.0) for k in available) if available else 0.0
    # Fallback to defaults if configured weights sum to 0 for available metrics
    if total_w <= 0.0 and available:
        fallback = dict(getattr(Constants, "HEURISTICS_WEIGHTS_DEFAULT", weights))
        total_w = sum(fallback.get(k, 0.0) for k in available)
        weights = fallback
    if total_w <= 0.0:
        breakdown = {k: {'raw': raw[k], 'normalized': v} for k, v in norm.items()}
        return 0.0, breakdown, {}
    weights_used = {k: (weights.get(k, 0.0) / total_w) for k in available}

    # Weighted sum ensures range [0,1] since each component is clamped and weights sum to 1
    final = 0.0
    for k in available:
        val = norm.get(k)
        if val is None:
            continue
        final += float(val) * weights_used[k]
    final = _clamp01(final)

    breakdown = {k: {'raw': raw[k], 'normalized': v} for k, v in norm.items()}
    return final, breakdown, weights_used

def run_min_analysis(pkgs):
    """Run to check the existence of the packages in the registry.

    Args:
        pkgs (list): List of packages to check.
    """
    for x in pkgs:
        test_exists(x)

def run_heuristics(pkgs):
    """Run heuristics on the packages.

    Args:
        pkgs (list): List of packages to check.
    """
    logger = logging.getLogger(__name__)
    for x in pkgs:
        test_exists(x)
        if x.exists is True:
            # Compute final normalized score in [0,1] using available metrics
            final_score, breakdown, weights_used = compute_final_score(x)
            x.score = final_score
            if is_debug_enabled(logger):
                logger.debug(
                    "Heuristics score breakdown",
                    extra=extra_context(
                        event="analysis",
                        component="heuristics",
                        action="score_breakdown",
                        package_name=str(x),
                        final_score=final_score,
                        weights=weights_used,
                        breakdown=breakdown,
                    ),
                )
            # Emit [ANALYSIS] lines for repository signals
            try:
                if getattr(x, "repo_stars", None) is not None:
                    logging.info("%s.... repository stars: %s.", STG, str(x.repo_stars))
                if getattr(x, "repo_contributors", None) is not None:
                    logging.info("%s.... repository contributors: %s.", STG, str(x.repo_contributors))
                if getattr(x, "repo_last_activity_at", None):
                    _days = _parse_iso_to_days(x.repo_last_activity_at)
                    if _days is not None:
                        logging.info("%s.... repository last activity %d days ago.", STG, int(_days))
                if getattr(x, "repo_present_in_registry", None) is not None:
                    logging.info("%s.... repository present in registry: %s.", STG, str(x.repo_present_in_registry))
                if getattr(x, "repo_version_match", None) is not None:
                    try:
                        _matched = bool(x.repo_version_match.get('matched', False))
                        logging.info("%s.... repository version match: %s.", STG, "yes" if _matched else "no")
                    except (AttributeError, TypeError):
                        logging.info("%s.... repository version match: unavailable.", STG)
            except (ValueError, TypeError):
                # Do not break analysis on logging issues
                pass
            test_score(x)
            test_timestamp(x)
            test_version_count(x)
            test_license_available(x)
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

def test_license_available(pkg):
    """Check if license information is available for the package.

    Args:
        pkg: Package to check.
    """
    # Check for license information from various sources
    # This heuristic computes is_license_available based on existing data
    # without triggering network calls

    license_available = False

    # Check if license information exists from registry enrichment
    # (This would be populated by registry enrichers if available)
    if hasattr(pkg, 'license') and pkg.license:
        license_available = True
    elif hasattr(pkg, 'license_id') and pkg.license_id:
        license_available = True
    elif hasattr(pkg, 'license_url') and pkg.license_url:
        license_available = True

    # Store the result as a heuristic output
    # This can be accessed later by policy evaluation
    pkg.is_license_available = license_available

    if license_available:
        logging.info("%s.... license information available.", STG)
    else:
        logging.debug("%s.... license information not available.", STG)
