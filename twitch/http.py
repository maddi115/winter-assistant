"""Tiny JSON-over-HTTPS helper (standard library only)."""
import json
import urllib.error
import urllib.parse
import urllib.request


class HTTPError(Exception):
    def __init__(self, status, body):
        super().__init__(f"HTTP {status}: {body}")
        self.status, self.body = status, body


def request(method, url, headers=None, form=None, body=None, timeout=15):
    data, h = None, dict(headers or {})
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        h["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode() or "{}"
            return r.status, json.loads(raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"message": raw}
        raise HTTPError(e.code, parsed)
