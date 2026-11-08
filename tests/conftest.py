import os
import shutil
import tempfile
from pathlib import Path

import pytest

# Estas variables deben fijarse ANTES de importar app.*: app.config las lee como
# constantes de módulo con os.getenv() en el momento del import (ver CLAUDE.md).
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "test-admin-password-123"
_TMP = tempfile.mkdtemp(prefix="quark_test_")
_TEMP_CHROMA_DIR = os.path.join(_TMP, "chroma")
_DB_PATH = os.path.join(_TMP, "quark.db")
os.environ["ADMIN_USERNAME"] = ADMIN_USERNAME
os.environ["ADMIN_PASSWORD"] = ADMIN_PASSWORD
os.environ["AUTH_SECRET_KEY"] = "test-secret-key-0123456789-abcdefghijklmnop"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"
os.environ["CHROMA_DB_DIR"] = _TEMP_CHROMA_DIR
os.environ.pop("QUARK_API_KEY", None)

ROOT = Path(__file__).resolve().parent.parent

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.cli import run_bootstrap  # noqa: E402
from app.main import app  # noqa: E402
from app.sql import SessionLocal, get_session  # noqa: E402


def alembic_upgrade(database_url: str) -> None:
    """Aplica `alembic upgrade head` sobre `database_url` (env.py lee DATABASE_URL del entorno)."""
    old = os.environ["DATABASE_URL"]
    os.environ["DATABASE_URL"] = database_url
    try:
        cfg = Config(str(ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(ROOT / "alembic"))
        command.upgrade(cfg, "head")
    finally:
        os.environ["DATABASE_URL"] = old


# Migración y bootstrap de la base de pruebas, una sola vez por sesión.
alembic_upgrade(os.environ["DATABASE_URL"])
with SessionLocal() as _s:
    _BOOTSTRAP_KEY = run_bootstrap(_s, ADMIN_USERNAME, ADMIN_PASSWORD).new_key
assert _BOOTSTRAP_KEY and _BOOTSTRAP_KEY.startswith("qk_")


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture(scope="session")
def admin_credentials():
    return {"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}


@pytest.fixture(scope="session")
def bootstrap_key():
    """API key válida (scopes read,write) emitida por el bootstrap de prueba."""
    return _BOOTSTRAP_KEY


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def api_key_headers(bootstrap_key):
    return {"X-API-Key": bootstrap_key}


@pytest.fixture
def auth_headers(client, admin_credentials):
    """Bearer JWT del admin obtenido en POST /token (valida contra la tabla users)."""
    r = client.post("/token", data=admin_credentials)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def isolated_db(tmp_path):
    """Base SQLite vacía y migrada, enlazada a la app vía dependency_overrides[get_session]."""
    url = f"sqlite:///{tmp_path / 'iso.db'}"
    alembic_upgrade(url)
    eng = create_engine(url, connect_args={"check_same_thread": False})
    maker = sessionmaker(bind=eng, autoflush=False, expire_on_commit=False)

    def _override():
        s = maker()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = _override
    yield {"url": url, "maker": maker, "engine": eng}
    app.dependency_overrides.pop(get_session, None)
    eng.dispose()


@pytest.fixture
def test_item():
    return {
        "text": "Esto es un texto de prueba para QUARK",
        "collection": "identity",
        "metadata": {"category": "test", "priority": "medium", "tags": ["test", "quark", "api"]},
    }


@pytest.fixture
def created_test_item(client, api_key_headers, test_item):
    response = client.post("/external/store", headers=api_key_headers, json=test_item)
    if response.status_code != 201:
        pytest.fail(f"Error al crear item de prueba: {response.text}")
    return response.json()
