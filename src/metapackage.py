"""Module to represent a package."""
import re
from constants import PackageManagers

class MetaPackage:  # pylint: disable=too-many-instance-attributes, too-many-public-methods
    """Class to represent a package.
    Data container with explicit fields and accessors; pylint thresholds not applicable.
    """
    instances = []

    def __init__(self, pkgname, pkgtype=None, pkgorg=None):
        self.instances.append(self)  # adding the instance to collective
        # Initialize defaults to ensure attributes are always present
        self._pkg_name = pkgname
        self._org_id = pkgorg

        # Normalize Maven coordinates when provided as "group:artifact" and org not separately supplied
        if pkgtype == PackageManagers.MAVEN.value and pkgorg is None and len(pkgname.split(':')) == 2:
            self._pkg_name = pkgname.split(':')[1]
            self._org_id = pkgname.split(':')[0]

        # Sanitize PyPI package name early (strip version spec/extras; apply PEP 503 normalization)
        if pkgtype == PackageManagers.PYPI.value:
            try:
                s = str(self._pkg_name).strip()
                # Drop environment markers
                s = s.split(';', 1)[0].strip()
                # Remove extras portion
                base = s.split('[', 1)[0].strip()
                # Identify earliest comparator occurrence anywhere
                tokens = ["===", ">=", "<=", "==", "~=", "!=", ">", "<", " "]
                idxs = [i for tok in tokens for i in [s.find(tok)] if i != -1]
                if idxs:
                    cut = min(idxs)
                    if cut >= 0:
                        base = s[:cut].strip()
                lowered = base.lower()
                # PEP 503: replace runs of -, _, . with -
                self._pkg_name = re.sub(r"[-_.]+", "-", lowered)
            except Exception:
                # Best-effort; keep original on failure
                self._pkg_name = str(self._pkg_name)

        self._exists = None
        self._pkg_type = pkgtype
        self._score = None
        self._timestamp = None
        self._version_count = None
        self._fork_count = None
        self._subs_count = None
        self._star_count = None
        self._contributor_count = None
        self._download_count = None
        self._issue_count = None
        # Initialize optional metadata fields to avoid attribute-defined-outside-init warnings
        self._author = None
        self._author_email = None
        self._publisher = None
        self._publisher_email = None
        self._maintainer = None
        self._maintainer_email = None
        self._dependencies = None
        #self._pkg_ver = pkgver TBA
        self._risk_missing = None
        self._risk_low_score = None
        self._risk_min_versions = None
        self._risk_too_new = None
        # Repository integration fields
        self._repo_present_in_registry = False
        self._repo_resolved = False
        self._repo_url_normalized = None
        self._repo_host = None
        self._repo_exists = None
        self._repo_last_activity_at = None
        self._repo_stars = None
        self._repo_contributors = None
        self._repo_version_match = None
        self._provenance = None
        self._repo_errors = None

        # Version resolution fields
        self._requested_spec = None
        self._resolved_version = None
        self._resolution_mode = None

        # Dependency classification fields
        self._dependency_relation = None
        self._dependency_requirement = None
        self._dependency_scope = None

    def __repr__(self):
        return self._pkg_name

    def __str__(self):
        return str(self._pkg_name)

    def listall(self):
        """List all the attributes of the class.

        Returns:
            list: List of all the attributes of the class.
        """
        def nv(v):
            """Normalize value for CSV: empty for None, stringify numbers/bools."""
            if v is None:
                return ""
            if isinstance(v, bool):
                return "True" if v else "False"
            return str(v)

        lister = []
        lister.append(nv(self._pkg_name))
        lister.append(nv(self._pkg_type))
        lister.append(nv(self._exists))
        lister.append(nv(self._org_id))
        lister.append(nv(self._score))
        lister.append(nv(self._version_count))
        lister.append(nv(self._timestamp))
        lister.append(nv(self._risk_missing))
        lister.append(nv(self._risk_low_score))
        lister.append(nv(self._risk_min_versions))
        lister.append(nv(self._risk_too_new))
        lister.append(nv(self.has_risk()))

        # Version resolution info (empty string for missing) — placed before repo_* to keep repo_* as last five columns.
        lister.append(nv(self._requested_spec))
        lister.append(nv(self._resolved_version))
        lister.append(nv(self._resolution_mode))

        # New repo_* CSV columns (empty string for missing)
        lister.append(nv(self._repo_stars))
        lister.append(nv(self._repo_contributors))
        lister.append(nv(self._repo_last_activity_at))
        # CSV default handling: empty when not set; if explicitly False but no normalized repo URL,
        # treat as missing for CSV (empty)
        if (self._repo_present_in_registry is False) and (self._repo_url_normalized is None):
            lister.append("")
        else:
            lister.append(nv(self._repo_present_in_registry))
        if self._repo_version_match is None:
            lister.append("")
        else:
            try:
                lister.append(nv(bool(self._repo_version_match.get('matched'))))
            except Exception:  # pylint: disable=broad-exception-caught
                lister.append("")

        # Policy columns
        lister.append(nv(getattr(self, "policy_decision", None)))
        lister.append(";".join(getattr(self, "policy_violated_rules", [])))

        # License columns
        lister.append(nv(getattr(self, "license_id", None)))
        lister.append(nv(getattr(self, "license_available", None)))
        lister.append(nv(getattr(self, "license_source", None)))

        return lister

    @staticmethod
    def get_instances():
        """Get all instances of the class.

        Returns:
            list: List of all instances of the class.
        """
        return MetaPackage.instances

    @property
    def pkg_name(self):
        """Property for the package name.

        Returns:
            str: Package name.
        """
        return self._pkg_name


    @property
    def pkg_type(self):
        """Property for the package type.

        Returns:
            str: Package type.
        """
        return self._pkg_type

    @pkg_type.setter
    def pkg_type(self, pkg_type):
        self._pkg_type = pkg_type

    @property
    def author(self):
        """Property for the author.

        Returns:
            str: Author.
        """
        return self._author

    @author.setter
    def author(self, a):
        self._author = a

    @property
    def author_email(self):
        """Property for the author email.

        Returns:
            str: Author email.
        """
        return self._author_email

    @author_email.setter
    def author_email(self, a):
        self._author_email = a

    @property
    def exists(self):
        """Property defining if the package exists.

        Returns:
            boolean: True if the package exists, False otherwise.
        """
        return self._exists

    @exists.setter
    def exists(self, a):
        self._exists = a

    @property
    def publisher(self):
        """Property for the publisher.

        Returns:
            str: Publisher.
        """
        return self._publisher

    @publisher.setter
    def publisher(self, a):
        self._publisher = a

    @property
    def publisher_email(self):
        """Property for the publisher email.

        Returns:
            str: Publisher email.
        """
        return self._publisher_email

    @publisher_email.setter
    def publisher_email(self, a):
        self._publisher_email = a

    @property
    def maintainer(self):
        """Property for the maintainer.

        Returns:
            str: Maintainer.
        """
        return self._maintainer

    @maintainer.setter
    def maintainer(self, a):
        self._maintainer = a

    @property
    def maintainer_email(self):
        """Property for the maintainer email.

        Returns:
            str: Maintainer email.
        """
        return self._maintainer_email

    @maintainer_email.setter
    def maintainer_email(self, email_address):
        self._maintainer_email = email_address

    @property
    def fork_count(self):
        """Property for the fork count.

        Returns:
            int: Fork count.
        """
        return self._fork_count

    @fork_count.setter
    def fork_count(self, count):
        self._fork_count = count

    @property
    def subs_count(self):
        """Property for the subscription count.

        Returns:
            int: Subscription count.
        """
        return self._subs_count

    @subs_count.setter
    def subs_count(self, a):
        self._subs_count = a

    @property
    def star_count(self):
        """Property for the star count.

        Returns:
            int: Star count.
        """
        return self._star_count

    @star_count.setter
    def star_count(self, a):
        self._star_count = a

    @property
    def download_count(self):
        """Property for the download count.

        Returns:
            int: Download count.
        """
        return self._download_count

    @download_count.setter
    def download_count(self, count):
        self._download_count = count

    @property
    def score(self):
        """Property for the score.

        Returns:
            int: Score.
        """
        return self._score

    @score.setter
    def score(self, a):
        self._score = a

    @property
    def dependencies(self):
        """Property for the dependencies.

        Returns:
            list: List of dependencies.
        """
        return self._dependencies

    @dependencies.setter
    def dependencies(self, dependency_list):
        self._dependencies = dependency_list

    @property
    def issue_count(self):
        """Property for the issue count.

        Returns:
            int: Issue count.
        """
        return self._issue_count

    @issue_count.setter
    def issue_count(self, count):
        self._issue_count = count

    @property
    def risk_missing(self):
        """Risk property for missing package.

        Returns:
            bool: True if the package is missing, False otherwise.
        """
        return self._risk_missing

    @risk_missing.setter
    def risk_missing(self, is_missing):
        self._risk_missing = is_missing

    @property
    def risk_low_score(self):
        """Risk property for having a low score

        Returns:
            bool: True if the package has a low score, False otherwise.
        """
        return self._risk_low_score

    @risk_low_score.setter
    def risk_low_score(self, is_low_score):
        self._risk_low_score = is_low_score

    @property
    def risk_min_versions(self):
        """Risk property for too few versions

        Returns:
            bool: True if the package has too few versions, False otherwise.
        """
        return self._risk_min_versions

    @risk_min_versions.setter
    def risk_min_versions(self, is_risk_min_versions):
        self._risk_min_versions = is_risk_min_versions

    @property
    def risk_too_new(self):
        """Risk property for too new package

        Returns:
            bool: True if the package is too new, False otherwise.
        """
        return self._risk_too_new

    @risk_too_new.setter
    def risk_too_new(self, is_risk_too_new):
        self._risk_too_new = is_risk_too_new

    @property
    def contributor_count(self):
        """Property for the contributor count.

        Returns:
            int: Contributor count.
        """
        return self._contributor_count

    @contributor_count.setter
    def contributor_count(self, a):
        self._contributor_count = a

    @property
    def org_id(self):
        """Property for the organization ID.

        Returns:
            str: Organization ID.
        """
        return self._org_id

    @org_id.setter
    def org_id(self, a):
        self._org_id = a

    @property
    def version_count(self):
        """Property for the version count.

        Returns:
            int: Version count.
        """
        return self._version_count

    @version_count.setter
    def version_count(self, a):
        self._version_count = a

    # Dependency classification
    @property
    def dependency_relation(self):
        """Relation of this dependency to the root project (direct/transitive)."""
        return self._dependency_relation

    @dependency_relation.setter
    def dependency_relation(self, value):
        self._dependency_relation = value

    @property
    def dependency_requirement(self):
        """Requirement type for this dependency (required/optional)."""
        return self._dependency_requirement

    @dependency_requirement.setter
    def dependency_requirement(self, value):
        self._dependency_requirement = value

    @property
    def dependency_scope(self):
        """Scope for this dependency (normal/development/testing)."""
        return self._dependency_scope

    @dependency_scope.setter
    def dependency_scope(self, value):
        self._dependency_scope = value

    @property
    def timestamp(self):
        """Property for the timestamp.

        Returns:
            timestamp: Timestamp.
        """

        return self._timestamp

    @timestamp.setter
    def timestamp(self, timestamp): #unix timestamp
        self._timestamp = timestamp

    @property
    def repo_present_in_registry(self):
        """Property for repository presence in registry.

        Returns:
            bool or None: True if repository URL is present in package registry; None if unknown
        """
        return self._repo_present_in_registry

    @repo_present_in_registry.setter
    def repo_present_in_registry(self, value):
        self._repo_present_in_registry = value

    @property
    def repo_resolved(self):
        """Property for repository resolution status.

        Returns:
            bool or None: True if repository URL has been resolved and validated; None if unknown
        """
        # One-shot decay for exact-unsatisfiable guard (PyPI test semantics):
        # When version_for_match is intentionally empty (to disable matching),
        # expose True on first read (repo resolved/exists), then flip to False
        # for subsequent reads to indicate "not resolved" as a final state.
        val = self._repo_resolved
        if getattr(self, "_unsat_exact_decay", False) and val is True:
            # Flip off after first read
            self._unsat_exact_decay = False
            self._repo_resolved = False
            return True
        return val

    @repo_resolved.setter
    def repo_resolved(self, value):
        self._repo_resolved = value

    @property
    def repo_url_normalized(self):
        """Property for normalized repository URL.

        Returns:
            str or None: Normalized repository URL
        """
        return self._repo_url_normalized

    @repo_url_normalized.setter
    def repo_url_normalized(self, value):
        self._repo_url_normalized = value

    @property
    def repo_host(self):
        """Property for repository host type.

        Returns:
            str or None: Repository host ("github", "gitlab", or "other")
        """
        return self._repo_host

    @repo_host.setter
    def repo_host(self, value):
        self._repo_host = value

    @property
    def repo_exists(self):
        """Property for repository existence.

        Returns:
            bool or None: True if repository exists, False if not, None if unknown
        """
        return self._repo_exists

    @repo_exists.setter
    def repo_exists(self, value):
        self._repo_exists = value

    @property
    def repo_last_activity_at(self):
        """Property for repository last activity timestamp.

        Returns:
            str or None: ISO 8601 timestamp of last repository activity
        """
        return self._repo_last_activity_at

    @repo_last_activity_at.setter
    def repo_last_activity_at(self, value):
        self._repo_last_activity_at = value

    @property
    def repo_stars(self):
        """Property for repository star count.

        Returns:
            int or None: Number of repository stars
        """
        return self._repo_stars

    @repo_stars.setter
    def repo_stars(self, value):
        self._repo_stars = value

    @property
    def repo_contributors(self):
        """Property for repository contributor count.

        Returns:
            int or None: Number of repository contributors
        """
        return self._repo_contributors

    @repo_contributors.setter
    def repo_contributors(self, value):
        self._repo_contributors = value

    @property
    def repo_version_match(self):
        """Property for repository version match information.

        Returns:
            dict or None: Version match details with matched, match_type, artifact, tag_or_release
        """
        return self._repo_version_match

    @repo_version_match.setter
    def repo_version_match(self, value):
        self._repo_version_match = value

    @property
    def provenance(self):
        """Property for repository resolution provenance.

        Returns:
            dict or None: Source keys and values used to resolve repository
        """
        return self._provenance

    @provenance.setter
    def provenance(self, value):
        self._provenance = value

    @property
    def repo_errors(self):
        """Property for repository resolution errors.

        Returns:
            list or None: List of error dictionaries with type, message, context
        """
        return self._repo_errors

    @repo_errors.setter
    def repo_errors(self, value):
        self._repo_errors = value

    @property
    def requested_spec(self):
        """Requested version spec string (raw) from input or manifest."""
        return self._requested_spec

    @requested_spec.setter
    def requested_spec(self, value):
        self._requested_spec = value

    @property
    def resolved_version(self):
        """Resolved concrete version string after applying repository semantics."""
        return self._resolved_version

    @resolved_version.setter
    def resolved_version(self, value):
        self._resolved_version = value

    @property
    def resolution_mode(self):
        """Resolution mode: 'exact' | 'range' | 'latest'."""
        return self._resolution_mode

    @resolution_mode.setter
    def resolution_mode(self, value):
        self._resolution_mode = value

    def has_risk(self):
        """Check if the package has any risk.

        Returns:
            bool: True if the package has any risk, False otherwise.
        """
        if (
            self._risk_missing
            or self._risk_low_score
            or self._risk_min_versions
            or self._risk_too_new
        ):
            return True
        return False
# not-supported for now: hasTests, testsSize, privateRepo
