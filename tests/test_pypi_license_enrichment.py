"""Tests for PyPI license enrichment and facts mapping."""
import json
from unittest.mock import patch
from metapackage import MetaPackage
from registry.pypi.enrich import _enrich_with_license
from registry.pypi import recv_pkg_info
from src.analysis.facts import FactBuilder


class TestPyPILicenseEnrichment:
    def test_license_from_classifiers(self):
        mp = MetaPackage("pkg")
        info = {
            "classifiers": [
                "License :: OSI Approved :: MIT License",
                "Programming Language :: Python :: 3"
            ]
        }
        _enrich_with_license(mp, info)
        assert getattr(mp, "license_id", None) == "MIT"
        assert getattr(mp, "license_available", None) is True
        assert getattr(mp, "license_source", None) == "pypi_classifiers"

    def test_license_from_license_field(self):
        mp = MetaPackage("pkg")
        info = {"license": "MIT"}
        _enrich_with_license(mp, info)
        assert getattr(mp, "license_id", None) == "MIT"
        assert getattr(mp, "license_available", None) is True
        assert getattr(mp, "license_source", None) == "pypi_license"

    def test_license_from_project_urls(self):
        mp = MetaPackage("pkg")
        url = "https://example.com/owner/repo/blob/main/LICENSE"
        info = {"project_urls": {"License": url}}
        _enrich_with_license(mp, info)
        assert getattr(mp, "license_id", None) is None
        assert getattr(mp, "license_available", None) is True
        assert getattr(mp, "license_source", None) == "pypi_project_urls"
        assert getattr(mp, "license_url", None) == url

    def test_license_missing_metadata(self):
        mp = MetaPackage("pkg")
        info = {}
        _enrich_with_license(mp, info)
        assert getattr(mp, "license_id", None) is None
        assert getattr(mp, "license_available", None) is None
        assert getattr(mp, "license_source", None) is None


class TestFactsLicenseMapping:
    def test_factbuilder_maps_license_fields(self):
        mp = MetaPackage("pkg")
        setattr(mp, "license_id", "MIT")
        setattr(mp, "license_available", True)
        setattr(mp, "license_source", "pypi_classifiers")
        facts = FactBuilder().build_facts(mp)
        assert facts.get("license", {}).get("id") == "MIT"
        assert facts.get("license", {}).get("available") is True
        assert facts.get("license", {}).get("source") == "pypi_classifiers"


class TestClientLicenseIntegration:
    def test_recv_pkg_info_sets_license_from_classifiers(self):
        mp = MetaPackage("toml")

        class DummyResp:
            status_code = 200
            text = json.dumps({
                "info": {
                    "version": "1.2.3",
                    "classifiers": ["License :: OSI Approved :: MIT License"]
                },
                "releases": {
                    "1.2.3": [{"upload_time_iso_8601": "2021-01-01T00:00:00.000Z"}]
                }
            })

        with patch("registry.pypi.safe_get", return_value=DummyResp()):
            # Prevent repository enrichment side effects (network/normalization)
            with patch("registry.pypi.client._enrich_with_repo") as noop_enrich:
                noop_enrich.side_effect = lambda *args, **kwargs: None
                with patch("time.sleep", return_value=None):
                    recv_pkg_info([mp])

        assert getattr(mp, "license_id", None) == "MIT"
        assert getattr(mp, "license_available", None) is True
        assert getattr(mp, "license_source", None) in ("pypi_classifiers", "pypi_license", "pypi_project_urls")
