"""Bootstrap (specs §4.2, §12): se ejecuta como proceso real, con su propia base SQLite."""
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.main import app
from app.sql import get_session
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parent.parent
PASSWORD = "bootstrap-test-password"

pytestmark = pytest.mark.auth


def _env(db_url, **extra):
    env = {k: v for k, v in os.environ.items() if k not in ("ADMIN_PASSWORD", "DATABASE_URL", "ADMIN_USERNAME")}
    env.update({"ADMIN_PASSWORD": PASSWORD, "DATABASE_URL": db_url, "AUTH_SECRET_KEY": "x" * 40})
    env.update(extra)
    return env


def _run(args, env):
    return subprocess.run([sys.executable, *args], cwd=ROOT, env=env, capture_output=True, text=True)


def _bootstrap(env, *flags):
    return _run(["-m", "app.cli", "bootstrap", *flags], env)


@pytest.fixture
def db(tmp_path):
    url = f"sqlite:///{tmp_path / 'b.db'}"
    env = _env(url)
    r = _run(["-m", "alembic", "upgrade", "head"], env)
    assert r.returncode == 0, r.stderr
    return url, env


def _q(url, sql):
    eng = create_engine(url)
    with eng.connect() as c:
        rows = c.execute(text(sql)).fetchall()
    eng.dispose()
    return rows


def _counts(url):
    return (
        _q(url, "select count(*) from users")[0][0],
        _q(url, "select count(*) from api_keys where is_active and tenant_id='default'")[0][0],
    )


def test_first_run_creates_admin_and_key(db):
    url, env = db
    r = _bootstrap(env)
    assert r.returncode == 0, r.stderr
    key = r.stdout.strip()
    assert key.startswith("qk_") and r.stdout.count("\n") == 1
    assert _counts(url) == (1, 1)
    username, scopes = _q(url, "select username, scopes from users")[0]
    assert (username, scopes) == ("admin", "read,write,admin")
    assert _q(url, "select scopes, tenant_id from api_keys")[0] == ("read,write", "default")
    assert PASSWORD not in r.stdout and PASSWORD not in r.stderr
    assert key not in r.stderr
    assert all(l.startswith("[bootstrap]") for l in r.stderr.splitlines())


def test_hashes_not_plaintext(db):
    url, env = db
    key = _bootstrap(env).stdout.strip()
    hp = _q(url, "select hashed_password from users")[0][0]
    kh = _q(url, "select key_hash from api_keys")[0][0]
    assert hp.startswith("$2b$") and PASSWORD not in hp
    assert len(kh) == 64 and int(kh, 16) >= 0 and kh == hashlib.sha256(key.encode()).hexdigest()
    assert key not in kh


def test_second_run_is_noop_even_if_password_changed(db):
    url, env = db
    _bootstrap(env)
    before = _q(url, "select id, hashed_password from users")
    keys_before = _q(url, "select id, key_hash, is_active from api_keys")
    r = _bootstrap(_env(url, ADMIN_PASSWORD="otra-password-distinta"))
    assert r.returncode == 0
    assert len(r.stdout.encode()) == 0
    assert _counts(url) == (1, 1)
    assert _q(url, "select id, hashed_password from users") == before
    assert _q(url, "select id, key_hash, is_active from api_keys") == keys_before


def test_rotate_key_invalidates_old_and_accepts_new(db, isolated_db):
    # Usa la base del fixture isolated_db (migrada) a través de un proceso real.
    url, env = isolated_db["url"], _env(isolated_db["url"])
    old = _bootstrap(env).stdout.strip()
    new = _bootstrap(env, "--rotate-key").stdout.strip()
    assert new.startswith("qk_") and new != old
    rows = _q(url, "select is_active from api_keys order by id")
    assert [bool(x[0]) for x in rows] == [False, True]  # la vieja no se borra
    with TestClient(app) as c:
        assert c.get("/external/collections", headers={"X-API-Key": old}).status_code == 401
        assert c.get("/check-auth", headers={"X-API-Key": new}).status_code == 200
        assert c.get("/check-auth", headers={"X-API-Key": old}).status_code == 401


def test_reset_admin_password_changes_hash_without_printing(db):
    url, env = db
    _bootstrap(env)
    h1 = _q(url, "select hashed_password from users")[0][0]
    r = _bootstrap(_env(url, ADMIN_PASSWORD="nueva-password-xyz"), "--reset-admin-password")
    assert r.returncode == 0 and r.stdout == ""
    h2 = _q(url, "select hashed_password from users")[0][0]
    assert h1 != h2 and h2.startswith("$2b$")
    assert "nueva-password-xyz" not in r.stderr


def test_custom_admin_username(db):
    url, env = db
    r = _bootstrap(_env(url, ADMIN_USERNAME="jefe"))
    assert r.returncode == 0
    assert _q(url, "select username from users")[0][0] == "jefe"


@pytest.mark.parametrize("missing", ["ADMIN_PASSWORD", "DATABASE_URL"])
def test_missing_env_exit_nonzero_without_writes(db, missing):
    url, env = db
    env = {k: v for k, v in env.items() if k != missing}
    r = _bootstrap(env)
    assert r.returncode != 0 and r.stdout == ""
    assert _counts(url) == (0, 0)


def test_missing_tables_exit_nonzero(tmp_path):
    url = f"sqlite:///{tmp_path / 'empty.db'}"
    r = _bootstrap(_env(url))
    assert r.returncode != 0 and r.stdout == ""
    assert "alembic upgrade head" in r.stderr
