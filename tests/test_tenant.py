"""Aislamiento por tenant en db_manager (specs.md §3.2)."""
import pytest

from app.database import ChromaDBManager, ItemExistsError, TenantRequiredError
from app.utils.embeddings import E5EmbeddingFunction
from tests.fake_embeddings import FakeE5Model

COLLECTION = "identity"


@pytest.fixture
def manager(tmp_path):
    return ChromaDBManager(path=str(tmp_path), embedding_function=E5EmbeddingFunction(model=FakeE5Model()))


def test_add_injects_mandatory_metadata(manager):
    item = manager.add_item(COLLECTION, "a", "texto uno", {"category": "x"}, tenant_id="t1")
    md = item["metadata"]
    assert md["tenant_id"] == "t1"
    assert md["created_at"] and md["updated_at"]
    assert md["category"] == "x"
    stored = manager.get_item(COLLECTION, "a", tenant_id="t1")
    assert stored["metadata"]["tenant_id"] == "t1"
    assert stored["metadata"]["created_at"] == md["created_at"]


def test_client_cannot_set_tenant_or_timestamps(manager):
    item = manager.add_item(
        COLLECTION, "a", "texto",
        {"tenant_id": "otro", "created_at": "1999-01-01T00:00:00", "updated_at": "1999-01-01T00:00:00"},
        tenant_id="t1",
    )
    assert item["metadata"]["tenant_id"] == "t1"
    assert not item["metadata"]["created_at"].startswith("1999")
    assert not item["metadata"]["updated_at"].startswith("1999")
    assert manager.get_item(COLLECTION, "a", tenant_id="otro") is None


def test_client_cannot_overwrite_tenant_on_update(manager):
    manager.add_item(COLLECTION, "a", "texto", tenant_id="t1")
    updated = manager.update_item(COLLECTION, "a", metadata={"tenant_id": "otro", "k": 1}, tenant_id="t1")
    assert updated["metadata"]["tenant_id"] == "t1"
    assert manager.get_item(COLLECTION, "a", tenant_id="otro") is None
    assert manager.get_item(COLLECTION, "a", tenant_id="t1")["metadata"]["k"] == 1


def test_update_preserves_created_at_and_renews_updated_at(manager):
    created = manager.add_item(COLLECTION, "a", "texto", tenant_id="t1")["metadata"]
    updated = manager.update_item(COLLECTION, "a", text="nuevo", metadata={"created_at": "1999"}, tenant_id="t1")
    assert updated["metadata"]["created_at"] == created["created_at"]
    assert updated["metadata"]["updated_at"] >= created["updated_at"]
    assert updated["text"] == "nuevo"


def test_get_isolated_between_tenants(manager):
    manager.add_item(COLLECTION, "a", "dato de t1", tenant_id="t1")
    assert manager.get_item(COLLECTION, "a", tenant_id="t1") is not None
    assert manager.get_item(COLLECTION, "a", tenant_id="t2") is None


def test_same_id_in_two_tenants_does_not_collide(manager):
    manager.add_item(COLLECTION, "a", "dato de t1", tenant_id="t1")
    manager.add_item(COLLECTION, "a", "dato de t2", tenant_id="t2")
    assert manager.get_item(COLLECTION, "a", tenant_id="t1")["text"] == "dato de t1"
    assert manager.get_item(COLLECTION, "a", tenant_id="t2")["text"] == "dato de t2"


def test_duplicate_id_in_same_tenant_raises(manager):
    manager.add_item(COLLECTION, "a", "uno", tenant_id="t1")
    with pytest.raises(ItemExistsError):
        manager.add_item(COLLECTION, "a", "dos", tenant_id="t1")
    assert manager.get_item(COLLECTION, "a", tenant_id="t1")["text"] == "uno"


def test_list_and_count_isolated(manager):
    manager.add_item(COLLECTION, "a", "uno", tenant_id="t1")
    manager.add_item(COLLECTION, "b", "dos", tenant_id="t1")
    manager.add_item(COLLECTION, "c", "tres", tenant_id="t2")
    assert sorted(i["id"] for i in manager.list_items(COLLECTION, tenant_id="t1")) == ["a", "b"]
    assert [i["id"] for i in manager.list_items(COLLECTION, tenant_id="t2")] == ["c"]
    assert manager.count_items(COLLECTION, tenant_id="t1") == 2
    assert manager.count_items(COLLECTION, tenant_id="nadie") == 0
    assert len(manager.list_items(COLLECTION, limit=1, tenant_id="t1")) == 1
    assert len(manager.list_items(COLLECTION, limit=None, tenant_id="t1")) == 2


def test_query_isolated_even_for_identical_text(manager):
    manager.add_item(COLLECTION, "a", "me gusta el café", tenant_id="t1")
    manager.add_item(COLLECTION, "b", "me gusta el café", tenant_id="t2")
    res = manager.query_items(COLLECTION, "café", n_results=10, tenant_id="t1")
    assert res["ids"][0] == ["a"]
    assert {m["tenant_id"] for m in res["metadatas"][0]} == {"t1"}
    assert manager.query_items(COLLECTION, "café", tenant_id="t3")["ids"][0] == []


def test_query_client_filter_is_combined_not_replacing_tenant(manager):
    manager.add_item(COLLECTION, "a", "café", {"category": "x"}, tenant_id="t1")
    manager.add_item(COLLECTION, "b", "café", {"category": "x"}, tenant_id="t2")
    res = manager.query_items(COLLECTION, "café", filter={"category": "x"}, tenant_id="t1")
    assert res["ids"][0] == ["a"]
    # un filtro que intenta apuntar a otro tenant no devuelve nada
    res = manager.query_items(COLLECTION, "café", filter={"tenant_id": "t2"}, tenant_id="t1")
    assert res["ids"][0] == []
    # varias claves de primer nivel también funcionan
    res = manager.query_items(COLLECTION, "café", filter={"category": "x", "tenant_id": "t1"}, tenant_id="t1")
    assert res["ids"][0] == ["a"]


def test_update_other_tenant_is_not_found(manager):
    manager.add_item(COLLECTION, "a", "original", tenant_id="t1")
    with pytest.raises(ValueError):
        manager.update_item(COLLECTION, "a", text="hack", tenant_id="t2")
    assert manager.get_item(COLLECTION, "a", tenant_id="t1")["text"] == "original"


def test_delete_other_tenant_is_not_found_and_keeps_data(manager):
    manager.add_item(COLLECTION, "a", "original", tenant_id="t1")
    with pytest.raises(ValueError):
        manager.delete_item(COLLECTION, "a", tenant_id="t2")
    assert manager.get_item(COLLECTION, "a", tenant_id="t1") is not None
    manager.delete_item(COLLECTION, "a", tenant_id="t1")
    assert manager.get_item(COLLECTION, "a", tenant_id="t1") is None


@pytest.mark.parametrize("bad", ["", "   ", None, 5])
def test_tenant_id_required_and_valid(manager, bad):
    with pytest.raises(TenantRequiredError):
        manager.add_item(COLLECTION, "a", "x", tenant_id=bad)
    with pytest.raises(TenantRequiredError):
        manager.list_items(COLLECTION, tenant_id=bad)


def test_tenant_id_keyword_is_mandatory(manager):
    with pytest.raises(TypeError):
        manager.get_item(COLLECTION, "a")
    with pytest.raises(TypeError):
        manager.query_items(COLLECTION, "q")


def test_all_seven_collections_exist(manager):
    assert set(manager.collections) == {
        "identity", "business", "reminders", "connections", "learnings", "priorities", "suggestions"
    }


def test_metadata_unsupported_values_are_sanitized(manager):
    item = manager.add_item(
        COLLECTION, "a", "texto",
        {"tags": [], "nota": None, "extra": {"k": "v"}, "ok": ["x", "y"], "n": 3},
        tenant_id="t1",
    )
    md = item["metadata"]
    assert "tags" not in md and "nota" not in md
    assert md["extra"] == '{"k": "v"}'
    assert md["ok"] == ["x", "y"] and md["n"] == 3


# --- nivel API: todos los routers exigen auth y usan el tenant del Principal ---

from app.database import db_manager  # noqa: E402

_ROUTERS = [
    # (prefijo, ruta de creación, ruta de búsqueda, ruta de listado)
    ("/identity", "/", "/search", "/"),
    ("/business", "/", "/search", "/"),
    ("/reminders", "/", "/search", "/"),
    ("/aprendizajes", "/guardar", "/buscar", "/listar"),
]


@pytest.fixture
def fake_db(tmp_path, monkeypatch):
    mgr = ChromaDBManager(path=str(tmp_path / "chroma_api"), embedding_function=E5EmbeddingFunction(model=FakeE5Model()))
    monkeypatch.setattr(db_manager, "collections", mgr.collections)
    return mgr


@pytest.mark.parametrize("prefix,create,search,listing", _ROUTERS)
def test_module_router_requires_auth_and_scopes_tenant(client, api_key_headers, fake_db, prefix, create, search, listing):
    assert client.post(prefix + create, json={"text": "x"}).status_code == 401
    assert client.get(prefix + listing).status_code == 401
    assert client.get(prefix + search, params={"query": "x"}).status_code == 401

    r = client.post(prefix + create, headers=api_key_headers, json={"text": "plan de ahorro mensual"})
    assert r.status_code == 201, r.text
    item = r.json()
    assert item["metadata"]["tenant_id"] == "default"
    assert item["metadata"]["created_at"] and item["metadata"]["updated_at"]

    got = client.get(f"{prefix}/{item['id']}", headers=api_key_headers)
    assert got.status_code == 200
    found = client.get(prefix + search, headers=api_key_headers, params={"query": "ahorro"})
    assert found.status_code == 200 and found.json()["items"]
    listed = client.get(prefix + listing, headers=api_key_headers)
    assert listed.status_code == 200 and listed.json()["total"] >= 1

    assert client.delete(f"{prefix}/{item['id']}", headers=api_key_headers).status_code == 200
    assert client.get(f"{prefix}/{item['id']}", headers=api_key_headers).status_code == 404


def test_unused_routers_require_auth(client, fake_db):
    for method, path in [
        ("get", "/prioridad/"), ("get", "/sugerencias/listar"), ("get", "/conexiones/"),
        ("get", "/external/collections"), ("post", "/conexiones/analizar"),
    ]:
        assert getattr(client, method)(path).status_code in (401, 422), path


def test_external_collections_returns_seven(client, api_key_headers, fake_db):
    r = client.get("/external/collections", headers=api_key_headers)
    assert r.status_code == 200
    assert len(set(r.json().values())) == 7


def test_external_item_of_other_tenant_is_404(client, api_key_headers, fake_db):
    fake_db.add_item("identity", "ajeno", "dato de otro tenant", tenant_id="otro")
    assert client.put("/external/update/identity/ajeno", headers=api_key_headers, json={"text": "x"}).status_code == 404
    assert client.delete("/external/delete/identity/ajeno", headers=api_key_headers).status_code == 404
    q = client.post("/external/query", headers=api_key_headers, json={"text": "dato", "collection": "identity"})
    assert q.json()["items"] == []
    cons = client.post("/external/consolidate", headers=api_key_headers, json={"query": "dato"})
    assert cons.json()["total_results"] == 0
    assert fake_db.get_item("identity", "ajeno", tenant_id="otro") is not None


def test_all_business_endpoints_work_with_principal(client, api_key_headers, fake_db, monkeypatch):
    """Humo: ningún endpoint de negocio falla al propagar el Principal (incl. llamadas internas entre endpoints)."""
    from app.utils import embeddings

    monkeypatch.setattr(embeddings, "_default_ef", E5EmbeddingFunction(model=FakeE5Model()))
    h = api_key_headers
    for prefix in ("/identity/", "/business/", "/reminders/"):
        for text in ("plan de ahorro mensual", "plan de ahorro mensual del hogar"):
            assert client.post(prefix, headers=h, json={"text": text}).status_code == 201
    assert client.post("/aprendizajes/guardar", headers=h, json={"text": "aprendí a ahorrar"}).status_code == 201
    calls = [
        ("post", "/aprendizajes/resumir", {}),
        ("post", "/prioridad/revisar", {"min_similarity": 0.5}),
        ("post", "/prioridad/optimizar", {}),
        ("get", "/prioridad/", None),
        ("post", "/sugerencias/obtener", {}),
        ("post", "/sugerencias/analizar", {}),
        ("get", "/sugerencias/listar", None),
        ("get", "/conexiones/", None),
    ]
    for method, path, body in calls:
        kwargs = {"headers": h} if body is None else {"headers": h, "json": body}
        r = getattr(client, method)(path, **kwargs)
        assert r.status_code == 200, (path, r.status_code, r.text)
