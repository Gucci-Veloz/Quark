import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.utils.auth import create_access_token

# Cliente de prueba
client = TestClient(app)

# Token de prueba
test_token = create_access_token(data={"sub": "testuser", "scopes": ["read", "write"]})
test_headers = {"Authorization": f"Bearer {test_token}"}

# API Key de prueba (debe coincidir con la usada en las pruebas)
test_api_key = "test_sofia_api_key"
api_key_headers = {"X-API-Key": test_api_key}

# Pruebas del endpoint raíz y documentación
@pytest.mark.api
def test_root(client):
    """Prueba el endpoint raíz."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "modules" in data

@pytest.mark.api
def test_docs(client):
    """Prueba el acceso a la documentación."""
    response = client.get("/docs")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

# Pruebas de autenticación
@pytest.mark.auth
def test_token_endpoint(client):
    """Prueba la obtención de token."""
    response = client.post(
        "/token",
        data={"username": "admin", "password": "sofia2023"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "token_type" in data
    assert data["token_type"] == "bearer"

@pytest.mark.auth
def test_token_endpoint_invalid_password(client):
    """Prueba la obtención de token con contraseña inválida."""
    response = client.post(
        "/token",
        data={"username": "admin", "password": "wrong_password"}
    )
    assert response.status_code == 401

@pytest.mark.auth
def test_check_auth(client, auth_headers):
    """Prueba la autenticación con token JWT."""
    response = client.get("/check-auth", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["authenticated"] == True

@pytest.mark.auth
def test_check_auth_no_token(client):
    """Prueba el acceso sin token."""
    response = client.get("/check-auth")
    assert response.status_code == 401

@pytest.mark.auth
def test_check_write_permission(client, auth_headers):
    """Prueba el acceso con permisos de escritura."""
    response = client.get("/check-write-permission", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["authorized"] == True
    assert data["scope"] == "write"

# Pruebas del módulo SofIA
@pytest.mark.api
def test_sofia_collections(client, api_key_headers):
    """Prueba el listado de colecciones disponibles."""
    response = client.get("/sofia/collections", headers=api_key_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert "identity" in data

@pytest.mark.api
def test_sofia_store(client, api_key_headers, test_item):
    """Prueba el almacenamiento de datos."""
    response = client.post(
        "/sofia/store",
        headers=api_key_headers,
        json=test_item
    )
    
    assert response.status_code == 201
    result = response.json()
    assert "id" in result
    assert result["text"] == test_item["text"]
    assert "metadata" in result

@pytest.mark.api
def test_sofia_query(client, api_key_headers, created_test_item):
    """Prueba la consulta de datos."""
    query_data = {
        "text": "texto de prueba",
        "collection": "identity",
        "n_results": 5
    }
    
    response = client.post(
        "/sofia/query",
        headers=api_key_headers,
        json=query_data
    )
    
    assert response.status_code == 200
    result = response.json()
    assert "items" in result
    assert "distances" in result
    assert len(result["items"]) > 0

@pytest.mark.api
def test_sofia_update(client, api_key_headers, created_test_item):
    """Prueba la actualización de datos."""
    update_data = {
        "text": "Texto actualizado para pruebas",
        "metadata": {
            "priority": "high",
            "status": "in_progress"
        }
    }
    
    response = client.put(
        f"/sofia/update/identity/{created_test_item['id']}",
        headers=api_key_headers,
        json=update_data
    )
    
    assert response.status_code == 200
    result = response.json()
    assert result["id"] == created_test_item["id"]
    assert result["text"] == update_data["text"]
    assert result["metadata"]["priority"] == "high"
    assert result["metadata"]["status"] == "in_progress"

@pytest.mark.api
def test_sofia_batch_operations(client, api_key_headers):
    """Prueba las operaciones por lotes."""
    operations = [
        {
            "type": "store",
            "collection": "identity",
            "text": "Texto para operaciones por lotes",
            "metadata": {
                "category": "test_batch",
                "priority": "medium"
            }
        },
        {
            "type": "query",
            "collection": "identity",
            "query": "operaciones por lotes",
            "n_results": 3
        }
    ]
    
    response = client.post(
        "/sofia/batch",
        headers=api_key_headers,
        json={"operations": operations}
    )
    
    assert response.status_code == 200
    result = response.json()
    assert "results" in result
    assert "errors" in result
    assert result["successful_operations"] > 0

@pytest.mark.api
def test_sofia_consolidate(client, api_key_headers, created_test_item):
    """Prueba la consolidación de datos de múltiples colecciones."""
    consolidate_data = {
        "query": "texto de prueba",
        "collections": ["identity", "business"],
        "limit": 5
    }
    
    response = client.post(
        "/sofia/consolidate",
        headers=api_key_headers,
        json=consolidate_data
    )
    
    assert response.status_code == 200
    result = response.json()
    assert "results" in result
    assert "query" in result
    assert "collections" in result
    assert "total_results" in result

@pytest.mark.api
def test_sofia_delete(client, api_key_headers, created_test_item):
    """Prueba la eliminación de datos."""
    response = client.delete(
        f"/sofia/delete/identity/{created_test_item['id']}",
        headers=api_key_headers
    )
    
    assert response.status_code == 200
    result = response.json()
    assert "message" in result
    
    # Verificar que el item ya no existe
    query_data = {
        "text": created_test_item["text"],
        "collection": "identity",
        "n_results": 1
    }
    
    query_response = client.post(
        "/sofia/query",
        headers=api_key_headers,
        json=query_data
    )
    
    query_result = query_response.json()
    # El item eliminado no debería aparecer entre los resultados. No se puede
    # asumir que la colección esté vacía: otros tests reutilizan el mismo texto
    # de prueba y comparten la misma colección durante la sesión de pytest.
    returned_ids = [item["id"] for item in query_result["items"]]
    assert created_test_item["id"] not in returned_ids 