import os
import json
from datetime import datetime, timedelta

import requests as _requests

# Preserve real functions in case we need passthrough
_REAL_GET = _requests.get
_REAL_POST = _requests.post
_REAL_REQUEST = _requests.request
_REAL_SESSION_REQUEST = getattr(_requests.Session, "request", None)

FAKE_ENABLED = os.environ.get("FAKE_REGISTRY", "0") == "1"
FAKE_MODE = os.environ.get("FAKE_MODE", "").strip()  # "", "timeout", "conn_error", "bad_json"

class MockResponse:
    def __init__(self, status_code=200, data=None, text=None, headers=None):
        self.status_code = status_code
        if text is None and data is not None:
            self.text = json.dumps(data)
        else:
            self.text = text if text is not None else ""
        self.headers = headers if headers is not None else {}
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
        # URL decode if needed
        import urllib.parse
        pkg = urllib.parse.unquote(pkg)
        if pkg == "missing-pkg":
            return MockResponse(404, text="{}")
        versions = {"1.0.0": {}, "1.0.1": {}, "1.3.0": {}}
        if pkg == "shortver-pkg":
            versions = {"1.0.0": {}}
        # Include time field for version metadata lookup
        time_data = {
            "1.0.0": "2016-03-21T17:41:23.000Z",
            "1.0.1": "2016-03-22T17:41:23.000Z",
            "1.3.0": "2016-03-25T17:41:23.000Z"
        }
        # Add time field to versions for _enrich_lookup_metadata
        versions_with_time = {}
        for ver, ver_data in versions.items():
            versions_with_time[ver] = {
                **ver_data,
                "license": "MIT",
                "repository": {"url": "https://github.com/stevemao/left-pad"}
            }
        data = {
            "versions": versions_with_time,
            "time": time_data,
            "license": "MIT",
            "repository": {"url": "https://github.com/stevemao/left-pad"}
        }
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

    # pypistats.org weekly downloads API
    if "pypistats.org/api/packages/" in url and url.endswith("/recent"):
        data = {"data": {"last_week": 50000}}
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

def _fake_request(method, url, timeout=None, headers=None, params=None, data=None, json=None, session=None, **kwargs):
    """Mock requests.request to handle requests.request() calls used by middleware."""
    if not FAKE_ENABLED:
        return _REAL_REQUEST(method, url, timeout=timeout, headers=headers, params=params, data=data, json=json, **kwargs)

    # Route to appropriate mock based on method
    method_upper = method.upper() if method else "GET"
    if method_upper == "GET":
        return _fake_get(url, timeout=timeout, headers=headers, params=params, **kwargs)
    elif method_upper == "POST":
        # Use data or json parameter, not both
        post_data = data if data is not None else (json.dumps(json) if json else None)
        return _fake_post(url, data=post_data, timeout=timeout, headers=headers, **kwargs)
    else:
        # For other methods, use real implementation
        return _REAL_REQUEST(method, url, timeout=timeout, headers=headers, params=params, data=data, json=json, **kwargs)

def _fake_session_request(self, method, url, **kwargs):
    """Mock Session.request to handle Session.request() calls used by middleware."""
    # Extract common parameters - avoid passing data twice
    timeout = kwargs.pop("timeout", None)
    headers = kwargs.pop("headers", None)
    params = kwargs.pop("params", None)
    data = kwargs.pop("data", None)
    json_data = kwargs.pop("json", None)
    # Call the module-level _fake_request
    return _fake_request(method, url, timeout=timeout, headers=headers, params=params, data=data, json=json_data, session=self, **kwargs)

def _fake_session_get(self, url, **kwargs):
    """Mock Session.get to handle Session.get() calls."""
    return _fake_session_request(self, "GET", url, **kwargs)

# Install patches when module is imported
try:
    _requests.get = _fake_get
    _requests.post = _fake_post
    _requests.request = _fake_request
    # Patch Session methods if they exist
    if _REAL_SESSION_REQUEST:
        _requests.Session.request = _fake_session_request
        # Also patch Session.get and Session.post for completeness
        if hasattr(_requests.Session, "get"):
            _requests.Session.get = _fake_session_get
        if hasattr(_requests.Session, "post"):
            _requests.Session.post = lambda self, url, **kwargs: _fake_session_request(self, "POST", url, **kwargs)
except Exception:
    # If patching fails, leave real functions intact
    pass
