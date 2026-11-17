import base64

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _basic(user: str, password: str) -> dict:
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()}


def test_health_is_public_and_leaks_no_secrets():
    r = client.get("/health")
    assert r.status_code == 200
    assert "s3cret" not in r.text and "GROQ_API_KEY" not in r.text


@pytest.mark.parametrize("path", ["/api/videos", "/docs", "/clips/anything.mp4", "/api/jobs/x"])
def test_everything_else_requires_login(path):
    r = client.get(path)
    assert r.status_code == 401
    assert r.headers["www-authenticate"].startswith("Basic")


@pytest.mark.parametrize("headers", [
    _basic("tester", "wrong"), _basic("wrong", "s3cret-password"), _basic("", ""),
    {"Authorization": "Basic !!!not-base64!!!"}, {"Authorization": "Bearer abc"},
    {"Authorization": "Basic " + base64.b64encode(b"nocolon").decode()},
])
def test_bad_credentials_rejected(headers):
    assert client.get("/api/videos", headers=headers).status_code == 401


def test_good_credentials_accepted():
    assert client.get("/api/videos", headers=_basic("tester", "s3cret-password")).status_code == 200


def test_password_may_contain_colons():
    import os
    os.environ["CLIPRUSH_AUTH_PASSWORD"] = "a:b:c"
    try:
        assert client.get("/api/videos", headers=_basic("tester", "a:b:c")).status_code == 200
    finally:
        os.environ["CLIPRUSH_AUTH_PASSWORD"] = "s3cret-password"


def test_fails_closed_when_credentials_missing(monkeypatch):
    monkeypatch.delenv("CLIPRUSH_AUTH_USERNAME")
    monkeypatch.delenv("CLIPRUSH_AUTH_PASSWORD")
    assert client.get("/api/videos").status_code == 503
    assert client.get("/health").status_code == 200  # health stays reachable for the platform


def test_explicit_local_opt_out(monkeypatch):
    monkeypatch.setenv("CLIPRUSH_DISABLE_AUTH", "1")
    assert client.get("/api/videos").status_code == 200
