import os
import shutil
import tempfile

import pytest

# Estas variables deben fijarse ANTES de importar app.main: app.config las lee
# como constantes de módulo con os.getenv() en el momento del import, así que
# sobreescribir os.environ después de ese punto no tiene efecto (ver CLAUDE.md).
os.environ["QUARK_API_KEY"] = "test_quark_api_key"
# ADMIN_PASSWORD ya no tiene default: Settings() lanza un error de validación
# al importar app.main si falta. Debe coincidir con el valor usado en
# test_api.py::test_token_endpoint.
os.environ["ADMIN_PASSWORD"] = "abundancia2026"
_TEMP_CHROMA_DIR = tempfile.mkdtemp(prefix="quark_test_chroma_")
os.environ["CHROMA_DB_DIR"] = _TEMP_CHROMA_DIR

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.utils.auth import create_access_token  # noqa: E402


def pytest_sessionfinish(session, exitstatus):
    """Limpia el directorio temporal de ChromaDB usado durante las pruebas."""
    shutil.rmtree(_TEMP_CHROMA_DIR, ignore_errors=True)


@pytest.fixture
def client():
    """Cliente de prueba para la API FastAPI."""
    with TestClient(app) as test_client:
        yield test_client

@pytest.fixture
def auth_token():
    """Token JWT de autenticación para pruebas."""
    token = create_access_token(data={"sub": "testuser", "scopes": ["read", "write"]})
    return token

@pytest.fixture
def auth_headers(auth_token):
    """Encabezados con token de autenticación para pruebas."""
    return {"Authorization": f"Bearer {auth_token}"}

@pytest.fixture
def api_key_headers():
    """Encabezados con API Key para pruebas."""
    return {"X-API-Key": "test_quark_api_key"}

@pytest.fixture
def test_item():
    """Item de prueba para crear en la base de datos."""
    return {
        "text": "Esto es un texto de prueba para QUARK",
        "collection": "identity",
        "metadata": {
            "category": "test",
            "priority": "medium",
            "tags": ["test", "quark", "api"]
        }
    }

@pytest.fixture
def created_test_item(client, api_key_headers, test_item):
    """Crea un item de prueba y lo devuelve."""
    response = client.post("/external/store", headers=api_key_headers, json=test_item)
    if response.status_code != 201:
        pytest.fail(f"Error al crear item de prueba: {response.text}")
    return response.json()
