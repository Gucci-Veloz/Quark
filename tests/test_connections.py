"""Colección `connections` (specs.md §3.3, runbook 0.12) y metadata obligatoria vía API."""
import pytest

from app.database import ChromaDBManager, db_manager
from app.models.schemas import CONNECTION_REQUIRED_FIELDS, validate_connection_metadata
from app.utils.embeddings import E5EmbeddingFunction
from tests.fake_embeddings import FakeE5Model

VALID = {
    "source_id": "doc-origen",
    "target_id": "doc-destino",
    "relation_type": "semantic",
    "collection_ref": "learnings",
    "timestamp": "2026-11-07T12:00:00+00:00",
}


@pytest.fixture
def fake_db(tmp_path, monkeypatch):
    """Sustituye las colecciones del db_manager global por unas con embeddings simulados."""
    manager = ChromaDBManager(path=str(tmp_path / "chroma"), embedding_function=E5EmbeddingFunction(model=FakeE5Model()))
    monkeypatch.setattr(db_manager, "collections", manager.collections)
    return manager


def _store(client, headers, metadata, text="Conexión entre dos ideas", **extra):
    return client.post(
        "/external/store", headers=headers,
        json={"text": text, "collection": "connections", "metadata": metadata, **extra},
    )


# --- validador ---------------------------------------------------------------

def test_validator_accepts_valid_metadata():
    assert validate_connection_metadata(dict(VALID)) == VALID


@pytest.mark.parametrize("missing", CONNECTION_REQUIRED_FIELDS)
def test_validator_requires_each_field(missing):
    md = {k: v for k, v in VALID.items() if k != missing}
    with pytest.raises(ValueError, match=missing):
        validate_connection_metadata(md)


def test_validator_rejects_empty_unknown_collection_and_bad_timestamp():
    with pytest.raises(ValueError, match="source_id"):
        validate_connection_metadata({**VALID, "source_id": " "})
    with pytest.raises(ValueError, match="collection_ref"):
        validate_connection_metadata({**VALID, "collection_ref": "no_existe"})
    with pytest.raises(ValueError, match="timestamp"):
        validate_connection_metadata({**VALID, "timestamp": "ayer"})


def test_validator_accepts_collection_name_or_key():
    validate_connection_metadata({**VALID, "collection_ref": "learnings_reflections"})
    validate_connection_metadata({**VALID, "collection_ref": "learnings"})


# --- /external/store en connections -----------------------------------------

def test_store_connection_without_fields_is_422(client, api_key_headers, fake_db):
    r = _store(client, api_key_headers, {})
    assert r.status_code == 422
    for field in CONNECTION_REQUIRED_FIELDS:
        assert field in r.json()["detail"]


def test_store_connection_missing_one_field_is_422(client, api_key_headers, fake_db):
    md = {k: v for k, v in VALID.items() if k != "relation_type"}
    r = _store(client, api_key_headers, md)
    assert r.status_code == 422
    assert "relation_type" in r.json()["detail"]


def test_store_and_query_connection_has_all_metadata(client, api_key_headers, fake_db):
    r = _store(client, api_key_headers, VALID, text="idea de negocio relacionada con un aprendizaje")
    assert r.status_code == 201, r.text
    stored = r.json()["metadata"]
    for field in (*CONNECTION_REQUIRED_FIELDS, "tenant_id", "created_at", "updated_at"):
        assert stored.get(field), field

    q = client.post(
        "/external/query", headers=api_key_headers,
        json={"text": "idea de negocio relacionada", "collection": "connections"},
    )
    assert q.status_code == 200, q.text
    items = q.json()["items"]
    assert len(items) == 1
    md = items[0]["metadata"]
    for field in (*CONNECTION_REQUIRED_FIELDS, "tenant_id", "created_at", "updated_at"):
        assert md.get(field), field


def test_client_cannot_set_tenant_via_api(client, api_key_headers, fake_db):
    r = _store(client, api_key_headers, {**VALID, "tenant_id": "otro-tenant", "created_at": "1999-01-01"})
    assert r.status_code == 201
    md = r.json()["metadata"]
    assert md["tenant_id"] == "default"
    assert md["created_at"] != "1999-01-01"


def test_update_cannot_strip_connection_fields(client, api_key_headers, fake_db):
    item_id = _store(client, api_key_headers, VALID).json()["id"]
    r = client.put(
        f"/external/update/connections/{item_id}", headers=api_key_headers,
        json={"metadata": {"source_id": ""}},
    )
    assert r.status_code == 422
    ok = client.put(
        f"/external/update/connections/{item_id}", headers=api_key_headers,
        json={"metadata": {"relation_type": "causal"}},
    )
    assert ok.status_code == 200
    assert ok.json()["metadata"]["relation_type"] == "causal"
    assert ok.json()["metadata"]["source_id"] == "doc-origen"


def test_batch_store_validates_connections(client, api_key_headers, fake_db):
    r = client.post("/external/batch", headers=api_key_headers, json={"operations": [
        {"type": "store", "collection": "connections", "text": "sin campos", "metadata": {}},
        {"type": "store", "collection": "connections", "text": "completa", "metadata": VALID},
    ]})
    assert r.status_code == 200
    body = r.json()
    assert body["successful_operations"] == 1 and body["failed_operations"] == 1
    assert "source_id" in body["errors"][0]["error"]


def test_store_other_collections_do_not_require_connection_fields(client, api_key_headers, fake_db):
    r = client.post("/external/store", headers=api_key_headers, json={"text": "algo", "collection": "identity"})
    assert r.status_code == 201
    assert r.json()["metadata"]["tenant_id"] == "default"


def test_store_duplicate_id_is_409(client, api_key_headers, fake_db):
    assert _store(client, api_key_headers, VALID, id="fijo").status_code == 201
    assert _store(client, api_key_headers, VALID, id="fijo").status_code == 409


# --- /conexiones/analizar ----------------------------------------------------

def test_analizar_creates_connections_with_spec_metadata(client, api_key_headers, fake_db):
    text = "estrategia de precios para el negocio"
    src = client.post("/identity/", headers=api_key_headers, json={"text": text}).json()
    client.post("/aprendizajes/guardar", headers=api_key_headers, json={"text": text})
    r = client.post(
        "/conexiones/analizar", headers=api_key_headers,
        json={"item_id": src["id"], "module": "identity", "min_similarity": 0.5, "max_connections": 3},
    )
    assert r.status_code == 200, r.text
    conns = r.json()["connections"]
    assert conns, "debería detectarse al menos una conexión"
    for c in conns:
        md = c["metadata"]
        for field in (*CONNECTION_REQUIRED_FIELDS, "tenant_id", "created_at", "updated_at"):
            assert md.get(field), field
        assert md["source_id"] == src["id"]
        assert md["tenant_id"] == "default"


# --- documentación OpenAPI (verificación 0.12) -------------------------------

def test_openapi_documents_store_body_for_connections(client):
    spec = client.get("/openapi.json").json()
    schema = spec["components"]["schemas"]["ExternalStoreRequest"]
    desc = schema["properties"]["metadata"]["description"]
    for field in CONNECTION_REQUIRED_FIELDS:
        assert field in desc
    examples = schema["examples"]
    assert any(e.get("collection") == "connections" for e in examples)


def test_external_requires_auth(client, fake_db):
    assert client.get("/external/collections").status_code == 401
    assert client.post("/external/store", json={"text": "x"}).status_code == 401
