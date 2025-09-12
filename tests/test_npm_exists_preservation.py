import json
from unittest.mock import patch

from metapackage import MetaPackage
from registry.npm.client import recv_pkg_info as npm_recv_pkg_info


class DummyResp:
    def __init__(self, text: str, status_code: int = 200):
        self.status_code = status_code
        self.text = text


def test_recv_pkg_info_preserves_exists_when_details_succeeds_and_mget_missing():
    # Arrange: details (GET) returns a valid packument, but mget (POST) mapping lacks the key
    mp = MetaPackage("@biomejs/biome")

    packument = json.dumps({"versions": {"1.0.0": {}}})
    mget_body = json.dumps({})  # no entry for @biomejs/biome

    with patch("registry.npm.client.npm_pkg.safe_get", return_value=DummyResp(packument)), \
         patch("registry.npm.client.npm_pkg.safe_post", return_value=DummyResp(mget_body)), \
         patch("registry.npm.client._enrich_with_repo") as noop_enrich, \
         patch("time.sleep", return_value=None):
        noop_enrich.side_effect = lambda *args, **kwargs: None

        # Act: should_fetch_details=True will call GET first (sets exists=True), then POST
        npm_recv_pkg_info([mp], should_fetch_details=True)

    # Assert: existence set by details must be preserved even if mget lacks the key
    assert mp.exists is True
    assert mp.version_count == 1
