from fastapi.testclient import TestClient

from app.main import app


def test_health():
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "redirect", "cache": "memory"}


def test_root_has_no_link():
    # Este servicio no define "/": la portada la sirve el gateway.
    with TestClient(app) as client:
        assert client.get("/").status_code == 404
