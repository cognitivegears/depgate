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

    def test_normalize_pypi_name(self):
        """Test PyPI package name normalization."""
        result = self.parser.parse("/simple/Flask_RESTful/", RegistryType.PYPI)
        assert result.package_name == "flask-restful"

    def test_normalize_pypi_name_dots(self):
        """Test PyPI package name normalization with dots."""
        result = self.parser.parse("/simple/zope.interface/", RegistryType.PYPI)
        assert result.package_name == "zope-interface"


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
