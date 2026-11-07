import logging
from datetime import timedelta

import pytest
from jose import jwt
from sqlalchemy import select

from app.cli import run_bootstrap
from app.main import app
from app.sql import ApiKey, User, utcnow
from app.utils.auth import create_access_token, hash_api_key

pytestmark = pytest.mark.auth

PUBLIC = {("GET", "/"), ("GET", "/docs"), ("GET", "/redoc"), ("GET", "/openapi.json"), ("POST", "/token")}


def test_all_business_routes_require_auth(client):
    """Ninguna ruta salvo las públicas responde sin credenciales."""
    checked = 0
    for path, methods in app.openapi()["paths"].items():
        for method in methods:
            if method.upper() in ("HEAD", "OPTIONS") or (method.upper(), path) in PUBLIC:
                continue
            url = path.replace("{", "").replace("}", "")
            r = client.request(method.upper(), url)
            assert r.status_code == 401, f"{method.upper()} {path} -> {r.status_code}"
            checked += 1
    assert checked > 10


def test_invalid_api_key_401(client):
    assert client.get("/external/collections", headers={"X-API-Key": "qk_invalida"}).status_code == 401


def test_valid_api_key_accepted(client, api_key_headers):
    r = client.get("/check-auth", headers=api_key_headers)
    assert r.status_code == 200
    info = r.json()["user_info"]
    assert info["kind"] == "api_key" and info["tenant_id"] == "default"
    assert sorted(info["scopes"]) == ["read", "write"]  # sin admin


def test_jwt_admin_accepted(client, auth_headers):
    r = client.get("/check-auth", headers=auth_headers)
    assert r.status_code == 200
    info = r.json()["user_info"]
    assert info["kind"] == "jwt" and info["tenant_id"] == "default" and "admin" in info["scopes"]


def test_jwt_unknown_user_rejected(client):
    token = create_access_token({"sub": "fantasma"})
    assert client.get("/check-auth", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_jwt_wrong_secret_rejected(client):
    token = jwt.encode({"sub": "admin", "exp": utcnow() + timedelta(minutes=5)}, "x" * 40, algorithm="HS256")
    assert client.get("/check-auth", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_jwt_inactive_user_rejected(client, isolated_db):
    with isolated_db["maker"]() as s:
        run_bootstrap(s, "admin", "pw-isolated-1")
    tok = client.post("/token", data={"username": "admin", "password": "pw-isolated-1"}).json()["access_token"]
    hdr = {"Authorization": f"Bearer {tok}"}
    assert client.get("/check-auth", headers=hdr).status_code == 200
    with isolated_db["maker"]() as s:
        s.scalar(select(User).where(User.username == "admin")).is_active = False
        s.commit()
    assert client.get("/check-auth", headers=hdr).status_code == 401
    # y tampoco puede obtener un token nuevo
    assert client.post("/token", data={"username": "admin", "password": "pw-isolated-1"}).status_code == 401


def test_inactive_api_key_rejected(client, isolated_db):
    with isolated_db["maker"]() as s:
        key = run_bootstrap(s, "admin", "pw-isolated-1").new_key
    assert client.get("/check-auth", headers={"X-API-Key": key}).status_code == 200
    with isolated_db["maker"]() as s:
        s.scalar(select(ApiKey).where(ApiKey.key_hash == hash_api_key(key))).is_active = False
        s.commit()
    assert client.get("/check-auth", headers={"X-API-Key": key}).status_code == 401


def test_scope_enforced_403(client, isolated_db):
    with isolated_db["maker"]() as s:
        s.add(ApiKey(key_hash=hash_api_key("qk_solo_lectura"), tenant_id="default", scopes="read", is_active=True))
        s.commit()
    h = {"X-API-Key": "qk_solo_lectura"}
    assert client.get("/check-auth", headers=h).status_code == 200
    assert client.get("/check-write-permission", headers=h).status_code == 403


def test_token_wrong_password_and_unknown_user(client, admin_credentials):
    assert client.post("/token", data={**admin_credentials, "password": "mala"}).status_code == 401
    assert client.post("/token", data={"username": "nadie", "password": "x"}).status_code == 401


def test_secrets_not_in_logs(client, api_key_headers, auth_headers, bootstrap_key, caplog, capfd):
    caplog.set_level(logging.DEBUG)
    client.get("/external/collections", headers=api_key_headers)
    client.get("/check-auth", headers=auth_headers)
    token = auth_headers["Authorization"].split(" ", 1)[1]
    out = capfd.readouterr()
    blob = caplog.text + out.out + out.err
    assert bootstrap_key not in blob
    assert token not in blob
