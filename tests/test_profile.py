import pytest

from app.sql import ApiKey
from app.utils.auth import hash_api_key

pytestmark = pytest.mark.api


def test_profile_requires_auth(client):
    assert client.get("/profile").status_code == 401
    assert client.post("/profile", json={"key": "a", "value": "b"}).status_code == 401


def test_profile_crud(client, api_key_headers):
    h = api_key_headers
    r = client.post("/profile", headers=h, json={"key": "idioma", "value": "es"})
    assert r.status_code == 201 and r.json()["key"] == "idioma" and r.json()["value"] == "es"
    assert client.post("/profile", headers=h, json={"key": "idioma", "value": "en"}).status_code == 409
    assert client.get("/profile/idioma", headers=h).json()["value"] == "es"
    assert "idioma" in [p["key"] for p in client.get("/profile", headers=h).json()]
    u = client.put("/profile/idioma", headers=h, json={"value": "en"})
    assert u.status_code == 200 and u.json()["value"] == "en"
    assert client.delete("/profile/idioma", headers=h).status_code == 200
    assert client.get("/profile/idioma", headers=h).status_code == 404
    assert client.put("/profile/idioma", headers=h, json={"value": "x"}).status_code == 404


def test_profile_scopes(client, isolated_db):
    with isolated_db["maker"]() as s:
        s.add(ApiKey(key_hash=hash_api_key("qk_ro"), tenant_id="default", scopes="read", is_active=True))
        s.commit()
    h = {"X-API-Key": "qk_ro"}
    assert client.get("/profile", headers=h).status_code == 200
    assert client.post("/profile", headers=h, json={"key": "k", "value": "v"}).status_code == 403


def test_profile_filtered_by_tenant(client, isolated_db):
    with isolated_db["maker"]() as s:
        s.add(ApiKey(key_hash=hash_api_key("qk_a"), tenant_id="tenantA", scopes="read,write", is_active=True))
        s.add(ApiKey(key_hash=hash_api_key("qk_b"), tenant_id="tenantB", scopes="read,write", is_active=True))
        s.commit()
    a, b = {"X-API-Key": "qk_a"}, {"X-API-Key": "qk_b"}
    assert client.post("/profile", headers=a, json={"key": "k", "value": "de A"}).status_code == 201
    assert client.get("/profile", headers=b).json() == []
    assert client.get("/profile/k", headers=b).status_code == 404
    assert client.delete("/profile/k", headers=b).status_code == 404
    assert client.post("/profile", headers=b, json={"key": "k", "value": "de B"}).status_code == 201
    assert client.get("/profile/k", headers=a).json()["value"] == "de A"
