"""Module to represent a package."""
from constants import PackageManagers

class MetaPackage:
    """Class to represent a package."""
    instances = []

    def __init__(self, pkgname, pkgtype=None, pkgorg=None):
        self.instances.append(self) # adding the instance to colllective
        if len(pkgname.split(':')) == 2:
            if pkgtype == PackageManagers.MAVEN.value:
                if pkgorg is None:
                    self._pkg_name = pkgname.split(':')[1]
                    self._org_id = pkgname.split(':')[0]
        else:
            self._pkg_name = pkgname
            self._org_id = pkgorg
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
        #self._pkg_ver = pkgver TBA
        self._risk_missing = None
        self._risk_low_score = None
        self._risk_min_versions = None
        self._risk_too_new = None

    def __repr__(self):
        return self._pkg_name

    def __str__(self):
        return str(self._pkg_name)

    def listall(self):
        """List all the attributes of the class.

        Returns:
            list: List of all the attributes of the class.
        """
        lister = []
        lister.append(self._pkg_name)
        lister.append(self._pkg_type)
        lister.append(self._exists)
        lister.append(self._org_id)
        lister.append(self._score)
        lister.append(self._version_count)
        lister.append(self._timestamp)
        lister.append(self._risk_missing)
        lister.append(self._risk_low_score)
        lister.append(self._risk_min_versions)
        lister.append(self._risk_too_new)
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

    @publisher.setter
    def publisher(self, a):
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

# not-supported for now: hasTests, testsSize, privateRepo
