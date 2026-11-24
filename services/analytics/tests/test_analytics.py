from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def test_event_is_counted():
    code = uuid4().hex[:8]
    event = {"code": code, "ts": "2026-01-02T03:04:05+00:00", "referrer": "https://example.com"}
    with TestClient(app) as client:
        assert client.post("/events", json=event).status_code == 202

        stats = client.get(f"/stats/{code}")
        assert stats.status_code == 200
        data = stats.json()
        assert data["total_clicks"] == 1
        assert data["last_click"].startswith("2026-01-02T03:04:05")
        assert data["by_day"] == [{"day": "2026-01-02", "clicks": 1}]
        assert data["top_referrers"] == [{"referrer": "https://example.com", "clicks": 1}]
        assert {"code": code, "clicks": 1} in client.get("/stats?limit=100").json()
