from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_create_get_delete(client):
    created = client.post("/links", json={"url": "https://example.com/a"})
    assert created.status_code == 201
    code = created.json()["code"]
    assert created.json()["short_url"].endswith(f"/{code}")

    fetched = client.get(f"/links/{code}")
    assert fetched.status_code == 200
    assert fetched.json()["url"] == "https://example.com/a"

    assert client.delete(f"/links/{code}").status_code == 204
    assert client.get(f"/links/{code}").status_code == 404


def test_duplicate_alias(client):
    body = {"url": "https://example.com", "custom_code": f"t-{uuid4().hex[:8]}"}
    assert client.post("/links", json=body).status_code == 201
    assert client.post("/links", json=body).status_code == 409
