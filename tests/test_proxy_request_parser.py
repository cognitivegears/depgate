"""Tests for the proxy request parser."""

import pytest
from src.proxy.request_parser import RequestParser, RegistryType


class TestRequestParserNPM:
    """Tests for NPM URL parsing."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = RequestParser()

    def test_parse_unscoped_package(self):
        """Test parsing unscoped NPM package."""
        result = self.parser.parse("/lodash")
        assert result.registry_type == RegistryType.NPM
        assert result.package_name == "lodash"
        assert result.version is None
        assert result.is_metadata_request is True

    def test_parse_scoped_package(self):
        """Test parsing scoped NPM package."""
        result = self.parser.parse("/@babel/core")
        assert result.registry_type == RegistryType.NPM
        assert result.package_name == "@babel/core"
        assert result.version is None
        assert result.is_metadata_request is True

    def test_parse_package_with_version(self):
        """Test parsing NPM package with version."""
        result = self.parser.parse("/lodash/4.17.21")
        assert result.registry_type == RegistryType.NPM
        assert result.package_name == "lodash"
        assert result.version == "4.17.21"
        assert result.is_metadata_request is True

    def test_parse_scoped_package_with_version(self):
        """Test parsing scoped NPM package with version."""
        result = self.parser.parse("/@babel/core/7.23.0")
        assert result.registry_type == RegistryType.NPM
        assert result.package_name == "@babel/core"
        assert result.version == "7.23.0"
        assert result.is_metadata_request is True

    def test_parse_tarball_request(self):
        """Test parsing NPM tarball request."""
        result = self.parser.parse("/lodash/-/lodash-4.17.21.tgz")
        assert result.registry_type == RegistryType.NPM
        assert result.package_name == "lodash"
        assert result.version == "4.17.21"
        assert result.is_tarball_request is True
        assert result.is_metadata_request is False

    def test_parse_scoped_tarball_request(self):
        """Test parsing scoped NPM tarball request."""
        result = self.parser.parse("/@babel/core/-/core-7.23.0.tgz")
        assert result.registry_type == RegistryType.NPM
        assert result.package_name == "@babel/core"
        assert result.version == "7.23.0"
        assert result.is_tarball_request is True

    def test_parse_prerelease_version(self):
        """Test parsing NPM package with prerelease version."""
        result = self.parser.parse("/package/-/package-1.0.0-beta.1.tgz")
        assert result.registry_type == RegistryType.NPM
        assert result.version == "1.0.0-beta.1"


class TestRequestParserPyPI:
    """Tests for PyPI URL parsing."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = RequestParser()

    def test_parse_simple_api(self):
        """Test parsing PyPI simple API request."""
        result = self.parser.parse("/simple/requests/", RegistryType.PYPI)
        assert result.registry_type == RegistryType.PYPI
        assert result.package_name == "requests"
        assert result.version is None
        assert result.is_metadata_request is True

    def test_parse_simple_api_without_trailing_slash(self):
        """Test parsing PyPI simple API request without trailing slash."""
        result = self.parser.parse("/simple/requests", RegistryType.PYPI)
        assert result.registry_type == RegistryType.PYPI
        assert result.package_name == "requests"

    def test_parse_json_api(self):
        """Test parsing PyPI JSON API request."""
        result = self.parser.parse("/pypi/requests/json", RegistryType.PYPI)
        assert result.registry_type == RegistryType.PYPI
        assert result.package_name == "requests"
        assert result.version is None
        assert result.is_metadata_request is True

    def test_parse_json_api_with_version(self):
        """Test parsing PyPI JSON API with version."""
        result = self.parser.parse("/pypi/requests/2.31.0/json", RegistryType.PYPI)
        assert result.registry_type == RegistryType.PYPI
        assert result.package_name == "requests"
        assert result.version == "2.31.0"

    def test_parse_json_api_with_short_version(self):
        """Test parsing PyPI JSON API with short version."""
        result = self.parser.parse("/pypi/requests/2.0/json", RegistryType.PYPI)
        assert result.registry_type == RegistryType.PYPI
        assert result.package_name == "requests"
        assert result.version == "2.0"

    def test_parse_json_api_with_rc_version(self):
        """Test parsing PyPI JSON API with RC version."""
        result = self.parser.parse("/pypi/requests/1.0rc1/json", RegistryType.PYPI)
        assert result.registry_type == RegistryType.PYPI
        assert result.package_name == "requests"
        assert result.version == "1.0rc1"

    def test_normalize_pypi_name(self):
        """Test PyPI package name normalization."""
        result = self.parser.parse("/simple/Flask_RESTful/", RegistryType.PYPI)
        assert result.package_name == "flask-restful"

    def test_normalize_pypi_name_dots(self):
        """Test PyPI package name normalization with dots."""
        result = self.parser.parse("/simple/zope.interface/", RegistryType.PYPI)
        assert result.package_name == "zope-interface"

    def test_parse_pypi_download_rc(self):
        """Test parsing PyPI download URL with RC version."""
        result = self.parser.parse(
            "/packages/ab/cd/ef/requests-1.0rc1.tar.gz",
            RegistryType.PYPI,
        )
        assert result.registry_type == RegistryType.PYPI
        assert result.package_name == "requests"
        assert result.version == "1.0rc1"

    def test_parse_pypi_wheel(self):
        """Test parsing PyPI wheel download URL."""
        result = self.parser.parse(
            "/packages/ab/cd/ef/requests-2.31.0-py3-none-any.whl",
            RegistryType.PYPI,
        )
        assert result.registry_type == RegistryType.PYPI
        assert result.package_name == "requests"
        assert result.version == "2.31.0"
        assert result.is_tarball_request is True
        assert result.is_metadata_request is False

    def test_parse_pypi_wheel_with_build_tag(self):
        """Test parsing PyPI wheel with optional build tag."""
        result = self.parser.parse(
            "/packages/ab/cd/ef/mypackage-1.0.0-1-py3-none-any.whl",
            RegistryType.PYPI,
        )
        assert result.registry_type == RegistryType.PYPI
        assert result.package_name == "mypackage"
        assert result.version == "1.0.0"

    def test_parse_pypi_sdist_ambiguous_name(self):
        """Ambiguous sdist names split at the last hyphen before a digit."""
        result = self.parser.parse(
            "/packages/ab/cd/ef/python-dateutil-2.8.2.tar.gz",
            RegistryType.PYPI,
        )
        assert result.registry_type == RegistryType.PYPI
        assert result.package_name == "python-dateutil"
        assert result.version == "2.8.2"

    def test_parse_pypi_sdist_name_with_digits(self):
        """Package names containing digits are correctly separated from version."""
        result = self.parser.parse(
            "/packages/ab/cd/ef/h5py-3.8.0.tar.gz",
            RegistryType.PYPI,
        )
        assert result.registry_type == RegistryType.PYPI
        assert result.package_name == "h5py"
        assert result.version == "3.8.0"

    def test_parse_pypi_sdist_post_version(self):
        """Post-release versions are correctly parsed."""
        result = self.parser.parse(
            "/packages/ab/cd/ef/mylib-1.0.post1.tar.gz",
            RegistryType.PYPI,
        )
        assert result.registry_type == RegistryType.PYPI
        assert result.package_name == "mylib"
        assert result.version == "1.0.post1"

    def test_parse_pypi_zip(self):
        """Zip archives are matched by the sdist pattern."""
        result = self.parser.parse(
            "/packages/ab/cd/ef/mylib-2.0.zip",
            RegistryType.PYPI,
        )
        assert result.registry_type == RegistryType.PYPI
        assert result.package_name == "mylib"
        assert result.version == "2.0"


class TestRequestParserMaven:
    """Tests for Maven URL parsing."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = RequestParser()

    def test_parse_artifact(self):
        """Test parsing Maven artifact request."""
        result = self.parser.parse(
            "/maven2/org/apache/commons/commons-lang3/3.12.0/commons-lang3-3.12.0.jar",
            RegistryType.MAVEN,
        )
        assert result.registry_type == RegistryType.MAVEN
        assert result.package_name == "org.apache.commons:commons-lang3"
        assert result.version == "3.12.0"
        assert result.is_tarball_request is True

    def test_parse_pom(self):
        """Test parsing Maven POM request."""
        result = self.parser.parse(
            "/maven2/org/apache/commons/commons-lang3/3.12.0/commons-lang3-3.12.0.pom",
            RegistryType.MAVEN,
        )
        assert result.registry_type == RegistryType.MAVEN
        assert result.package_name == "org.apache.commons:commons-lang3"
        assert result.version == "3.12.0"

    def test_parse_metadata(self):
        """Test parsing Maven metadata request."""
        result = self.parser.parse(
            "/maven2/org/apache/commons/commons-lang3/maven-metadata.xml",
            RegistryType.MAVEN,
        )
        assert result.registry_type == RegistryType.MAVEN
        assert result.package_name == "org.apache.commons:commons-lang3"
        assert result.version is None
        assert result.is_metadata_request is True


class TestRequestParserNuGet:
    """Tests for NuGet URL parsing."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = RequestParser()

    def test_parse_registration(self):
        """Test parsing NuGet registration request."""
        result = self.parser.parse(
            "/v3/registration5-gz-semver2/newtonsoft.json/index.json",
            RegistryType.NUGET,
        )
        assert result.registry_type == RegistryType.NUGET
        assert result.package_name == "newtonsoft.json"
        assert result.is_metadata_request is True

    def test_parse_registration_with_version(self):
        """Test parsing NuGet registration with version."""
        result = self.parser.parse(
            "/v3/registration5-gz-semver2/newtonsoft.json/13.0.3.json",
            RegistryType.NUGET,
        )
        assert result.registry_type == RegistryType.NUGET
        assert result.package_name == "newtonsoft.json"
        assert result.version == "13.0.3"

    def test_parse_flatcontainer(self):
        """Test parsing NuGet flat container request."""
        result = self.parser.parse(
            "/v3-flatcontainer/newtonsoft.json/index.json",
            RegistryType.NUGET,
        )
        assert result.registry_type == RegistryType.NUGET
        assert result.package_name == "newtonsoft.json"


class TestRequestParserAutoDetect:
    """Tests for registry auto-detection."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = RequestParser()

    def test_autodetect_npm(self):
        """Test auto-detecting NPM registry."""
        result = self.parser.parse("/lodash")
        assert result.registry_type == RegistryType.NPM

    def test_autodetect_pypi_simple(self):
        """Test auto-detecting PyPI simple API."""
        result = self.parser.parse("/simple/requests/")
        assert result.registry_type == RegistryType.PYPI

    def test_autodetect_pypi_json(self):
        """Test auto-detecting PyPI JSON API."""
        result = self.parser.parse("/pypi/requests/json")
        assert result.registry_type == RegistryType.PYPI

    def test_autodetect_nuget(self):
        """Test auto-detecting NuGet registry."""
        result = self.parser.parse("/v3/registration5-gz-semver2/newtonsoft.json/index.json")
        assert result.registry_type == RegistryType.NUGET

    def test_unknown_path_uses_default(self):
        """Test that generic paths are parsed as NPM (since it's the most generic)."""
        parser = RequestParser(default_registry=RegistryType.NPM)
        # This looks like an NPM package with a version path
        result = parser.parse("/some/unknown/path")
        # NPM parser will match this as package "some" with version "unknown/path"
        assert result.registry_type == RegistryType.NPM
        assert result.package_name == "some"

    def test_registry_hint_prevents_autodetect_on_miss(self):
        """Test that registry hint is honored even when parsing fails."""
        parser = RequestParser(default_registry=RegistryType.NPM)
        result = parser.parse("/v3/index.json", RegistryType.NUGET)
        assert result.registry_type == RegistryType.NUGET
        assert result.package_name == ""
