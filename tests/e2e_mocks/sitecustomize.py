import os
import json
from datetime import datetime, timedelta

import requests as _requests

# Preserve real functions in case we need passthrough
_REAL_GET = _requests.get
_REAL_POST = _requests.post

FAKE_ENABLED = os.environ.get("FAKE_REGISTRY", "0") == "1"
FAKE_MODE = os.environ.get("FAKE_MODE", "").strip()  # "", "timeout", "conn_error", "bad_json"

class MockResponse:
    def __init__(self, status_code=200, data=None, text=None):
        self.status_code = status_code
        if text is None and data is not None:
            self.text = json.dumps(data)
        else:
            self.text = text if text is not None else ""
    def json(self):
        return json.loads(self.text)

def _iso_now():
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")

def _iso_old():
    return "2015-01-01T00:00:00.000Z"

def _maven_doc(timestamp_ms=None, version_count=3):
    if timestamp_ms is None:
        timestamp_ms = int(datetime(2020, 1, 1).timestamp() * 1000)
    return {"timestamp": timestamp_ms, "versionCount": version_count}

def _fake_get(url, timeout=None, headers=None, params=None, **kwargs):
    if not FAKE_ENABLED:
        return _REAL_GET(url, timeout=timeout, headers=headers, params=params, **kwargs)

    if FAKE_MODE == "timeout":
        raise _requests.Timeout("Simulated timeout")
    if FAKE_MODE == "conn_error":
        raise _requests.RequestException("Simulated connection error")
    if FAKE_MODE == "bad_json":
        # Return 200 but non-JSON body to trigger JSONDecodeError
        return MockResponse(200, text="<html>bad</html>")

    # NPM package details GET
    if "registry.npmjs.org/" in url:
        pkg = url.rsplit("/", 1)[-1]
        if pkg == "missing-pkg":
            return MockResponse(404, text="{}")
        versions = {"1.0.0": {}, "1.0.1": {}}
        if pkg == "shortver-pkg":
            versions = {"1.0.0": {}}
        data = {"versions": versions}
        return MockResponse(200, data=data)

    # PyPI GET package JSON
    if "pypi.org/pypi/" in url and url.endswith("/json"):
        name = url.split("/pypi/")[1].split("/")[0]
        if name == "pypi-missing":
            return MockResponse(404, text="{}")
        releases = {}
        if name == "pypi-short":
            releases = {"0.0.1": [{"upload_time_iso_8601": _iso_old()}]}
        elif name == "pypi-new":
            # New package: ensure "new" signal (latest is now) without triggering minVersions risk
            releases = {
                "0.9.0": [{"upload_time_iso_8601": _iso_old()}],
                "1.0.0": [{"upload_time_iso_8601": _iso_now()}],
            }
        else:
            releases = {
                "1.0.0": [{"upload_time_iso_8601": _iso_old()}],
                "1.1.0": [{"upload_time_iso_8601": _iso_old()}],
                "2.0.0": [{"upload_time_iso_8601": _iso_old()}],
            }
        data = {"info": {"version": list(releases.keys())[-1]}, "releases": releases}
        return MockResponse(200, data=data)

    # Maven search GET
    if "search.maven.org/solrsearch/select" in url:
        # Expect params with q="g:GROUP a:ARTIFACT"
        q = (params or {}).get("q", "")
        artifact = ""
        for tok in q.split():
            if tok.startswith("a:"):
                artifact = tok[2:]
                break
        if artifact in ("present-art", "json-flattener", "javax.json", "commons-io", "commons-lang3"):
            data = {"response": {"numFound": 1, "docs": [_maven_doc(version_count=5)]}}
        elif artifact == "missing-art":
            data = {"response": {"numFound": 0, "docs": []}}
        else:
            # Default to found=false
            data = {"response": {"numFound": 0, "docs": []}}
        return MockResponse(200, data=data)

    # Passthrough for anything else
    return _REAL_GET(url, timeout=timeout, headers=headers, params=params, **kwargs)

def _fake_post(url, data=None, timeout=None, headers=None, **kwargs):
    if not FAKE_ENABLED:
        return _REAL_POST(url, data=data, timeout=timeout, headers=headers, **kwargs)

    if FAKE_MODE == "timeout":
        raise _requests.Timeout("Simulated timeout")
    if FAKE_MODE == "conn_error":
        raise _requests.RequestException("Simulated connection error")
    if FAKE_MODE == "bad_json":
        return MockResponse(200, text="not-json")

    # NPM mget POST
    if "api.npms.io/v2/package/mget" in url:
        try:
            names = json.loads(data or "[]")
        except Exception:
            names = []
        mapping = {}
        for name in names:
            if name == "missing-pkg":
                # omit to simulate missing
                continue
            score = 0.9
            if name == "badscore-pkg":
                score = 0.1
            date = _iso_old()
            if name == "newpkg":
                date = _iso_now()
            mapping[name] = {"score": {"final": score}, "collected": {"metadata": {"date": date}}}
        return MockResponse(200, data=mapping)

    return _REAL_POST(url, data=data, timeout=timeout, headers=headers, **kwargs)

# Install patches when module is imported
try:
    _requests.get = _fake_get
    _requests.post = _fake_post
except Exception:
    # If patching fails, leave real functions intact
    pass
