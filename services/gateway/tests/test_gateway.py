import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app, state


def test_root_serves_frontend():
    with TestClient(app) as client:
        resp = client.get("/")
    assert resp.status_code == 200
    assert "Acortador de enlaces" in resp.text


@pytest.mark.parametrize("upstream, status, expected", [(200, 200, "ok"), (500, 503, "degraded")])
def test_health_aggregates_services(monkeypatch, upstream, status, expected):
    fake = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(upstream)))
    with TestClient(app) as client, monkeypatch.context() as m:
        m.setitem(state, "http", fake)
        resp = client.get("/health")
    assert resp.status_code == status
    assert resp.json()["status"] == expected
    assert set(resp.json()["services"]) == {"shortener", "redirect", "analytics"}
