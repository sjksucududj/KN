"""covshim/sitecustomize.py — AUDIT INSTRUMENTATION (read-only, non-invasive).

Auto-imported by Python at startup when this dir is on PYTHONPATH.
Rewrites any request targeting a *.preview.emergentagent.com host (stale test
URLs) to the LOCAL server (http://localhost:8001) so the ENTIRE historical test
corpus exercises OUR running instance — enabling honest coverage measurement.

Does NOT modify application code. Only affects test/client processes that have
this dir on PYTHONPATH.
"""
import os

_TARGET = os.environ.get("COVSHIM_TARGET", "http://localhost:8001")


def _rewrite(url: str) -> str:
    try:
        from urllib.parse import urlsplit, urlunsplit
        parts = urlsplit(url)
        host = parts.netloc.lower()
        if host.endswith(".preview.emergentagent.com"):
            t = urlsplit(_TARGET)
            return urlunsplit((t.scheme, t.netloc, parts.path, parts.query, parts.fragment))
        return url
    except Exception:
        return url


# ── Patch requests ───────────────────────────────────────────────────────────
try:
    import requests.sessions as _rs

    _orig_req = _rs.Session.request

    def _patched_request(self, method, url, *a, **kw):
        return _orig_req(self, method, _rewrite(url), *a, **kw)

    _rs.Session.request = _patched_request
except Exception:
    pass

# ── Patch httpx (sync + async) ────────────────────────────────────────────────
try:
    import httpx as _hx

    _orig_build = _hx.Client.build_request

    def _patched_build(self, method, url, *a, **kw):
        try:
            url = _rewrite(str(url))
        except Exception:
            pass
        return _orig_build(self, method, url, *a, **kw)

    _hx.Client.build_request = _patched_build

    if hasattr(_hx, "AsyncClient"):
        _orig_abuild = _hx.AsyncClient.build_request

        def _patched_abuild(self, method, url, *a, **kw):
            try:
                url = _rewrite(str(url))
            except Exception:
                pass
            return _orig_abuild(self, method, url, *a, **kw)

        _hx.AsyncClient.build_request = _patched_abuild
except Exception:
    pass
