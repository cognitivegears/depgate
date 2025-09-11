import json
import os

import pytest

from constants import Constants
from registry.depsdev.client import DepsDevClient


def test_get_project_caches_memory_and_file(tmp_path, monkeypatch):
    # Arrange: fake robust_get to return 200 JSON with cache-control
    calls = {"n": 0}

    def fake_robust_get(url, headers=None, context=None):
        calls["n"] += 1
        return 200, {"Cache-Control": "max-age=60"}, json.dumps({"licenses": [{"id": "MIT"}]})

    monkeypatch.setattr("registry.depsdev.client.robust_get", fake_robust_get)

    cache_path = tmp_path / "depsdev_cache.json"
    client = DepsDevClient(file_cache_path=str(cache_path))

    # Act: first call goes to network
    status1, headers1, data1 = client.get_project("npm", "left-pad")

    # Assert: first call ok
    assert status1 == 200
    assert isinstance(data1, dict)
    assert calls["n"] == 1

    # Act: second call (same process) should hit in-memory cache
    status2, headers2, data2 = client.get_project("npm", "left-pad")

    # Assert: still one network call; data returned
    assert status2 == 200
    assert isinstance(data2, dict)
    assert calls["n"] == 1

    # Act: new client process (simulated) should hit file cache and not call network again
    client2 = DepsDevClient(file_cache_path=str(cache_path))
    status3, headers3, data3 = client2.get_project("npm", "left-pad")

    # Assert: no additional network calls
    assert status3 == 200
    assert isinstance(data3, dict)
    assert calls["n"] == 1
    assert os.path.isfile(cache_path)


def test_response_size_guard(monkeypatch, tmp_path):
    # Arrange: make response exceed max bytes to trigger guard
    max_bytes = Constants.DEPSDEV_MAX_RESPONSE_BYTES

    def fake_robust_get(url, headers=None, context=None):
        big = "X" * (max_bytes + 1)
        return 200, {}, big

    monkeypatch.setattr("registry.depsdev.client.robust_get", fake_robust_get)

    client = DepsDevClient(file_cache_path=str(tmp_path / "cache.json"))

    # Act
    status, headers, data = client.get_project("npm", "left-pad")

    # Assert
    assert status == 0
    assert data is None


def test_enrich_disabled_no_network(monkeypatch, tmp_path):
    # Arrange: if enrichment is disabled, no network should be called
    called = {"hit": False}

    def raise_if_called(*args, **kwargs):
        called["hit"] = True
        raise AssertionError("Network was called while feature disabled")

    # Patch the low-level robust_get used by the client; if it runs, test fails
    monkeypatch.setattr("registry.depsdev.client.robust_get", raise_if_called)

    # Import here to ensure patches are active
    from registry.depsdev.enrich import enrich_metapackage

    class DummyMP:
        pkg_name = "left-pad"
        repo_url_normalized = None
        provenance = None

    mp = DummyMP()

    # Toggle feature flag off
    import constants as constmod

    old_enabled = constmod.Constants.DEPSDEV_ENABLED
    constmod.Constants.DEPSDEV_ENABLED = False  # type: ignore
    try:
        enrich_metapackage(mp, "npm", "left-pad", "1.0.0", client=None)
        # Assert no network attempt happened
        assert called["hit"] is False
    finally:
        # Restore flag
        constmod.Constants.DEPSDEV_ENABLED = old_enabled  # type: ignore
