"""Acceso a ChromaDB con aislamiento por tenant (specs.md §3.2).

Toda operación de ``db_manager`` exige ``tenant_id`` como argumento keyword:

* Escrituras: el servidor fija ``tenant_id``, ``created_at`` y ``updated_at`` en
  la metadata y sobrescribe lo que mande el cliente.
* Lecturas/updates/deletes: filtran por ``tenant_id``. Un id de otro tenant se
  comporta como inexistente (``get_item`` -> ``None``; ``update_item`` y
  ``delete_item`` -> ``ValueError``, que los routers traducen a 404).
* Los ids se guardan en ChromaDB con el prefijo ``"<tenant_id>:"``: dos tenants
  pueden usar el mismo id sin colisionar ni revelar que existe. Hacia fuera el
  id es siempre el original.
"""
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings

from app.config import CHROMA_DB_DIR, COLLECTIONS
from app.utils.embeddings import get_embedding_function


class TenantRequiredError(RuntimeError):
    """Se intentó operar sin un ``tenant_id`` válido."""


class ItemExistsError(Exception):
    """Ya existe un item con ese id en el tenant (los routers responden 409)."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check_tenant(tenant_id: Any) -> str:
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise TenantRequiredError("tenant_id es obligatorio en toda operación")
    return tenant_id


def _sanitize_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Adapta la metadata a lo que acepta ChromaDB 1.5.x.

    Descarta ``None`` y listas vacías (ChromaDB las rechaza) y serializa a JSON
    los dicts anidados; escalares y listas no vacías pasan tal cual.
    """
    clean: Dict[str, Any] = {}
    for key, value in metadata.items():
        if value is None or (isinstance(value, (list, tuple)) and len(value) == 0):
            continue
        clean[key] = json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value
    return clean


def _cid(tenant_id: str, item_id: str) -> str:
    """Id interno de ChromaDB (namespaced por tenant)."""
    return f"{tenant_id}:{item_id}"


def _public_id(tenant_id: str, chroma_id: str) -> str:
    prefix = f"{tenant_id}:"
    return chroma_id[len(prefix):] if chroma_id.startswith(prefix) else chroma_id


def _build_where(tenant_id: str, client_filter: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Combina el filtro del servidor (tenant) con el del cliente mediante ``$and``."""
    tenant_clause = {"tenant_id": tenant_id}
    if not client_filter:
        return tenant_clause
    if len(client_filter) == 1:
        clauses = [tenant_clause, client_filter]
    else:  # varias claves de primer nivel: ChromaDB exige $and explícito
        clauses = [tenant_clause] + [{k: v} for k, v in client_filter.items()]
    return {"$and": clauses}


class ChromaDBManager:
    """Gestor de conexión y operaciones con ChromaDB (siempre por tenant)."""

    def __init__(self, path: Optional[str] = None, embedding_function: Any = None):
        """Inicializa la conexión con ChromaDB.

        ``path`` y ``embedding_function`` son inyectables (tests); por defecto se
        usan ``CHROMA_DB_DIR`` y la función E5 con prefijos passage/query.
        """
        self.client = chromadb.PersistentClient(
            path=path or CHROMA_DB_DIR,
            settings=Settings(allow_reset=True),
        )
        self.embedding_function = embedding_function or get_embedding_function()
        self._initialize_collections()

    def _initialize_collections(self):
        """Obtiene o crea las colecciones (distancia coseno)."""
        self.collections = {}
        for key, name in COLLECTIONS.items():
            self.collections[key] = self.client.get_or_create_collection(
                name=name,
                embedding_function=self.embedding_function,
                configuration={"hnsw": {"space": "cosine"}},
            )

    def get_collection(self, collection_key):
        """Obtiene una colección por su clave."""
        if collection_key not in self.collections:
            raise ValueError(f"Colección '{collection_key}' no encontrada")
        return self.collections[collection_key]

    def add_item(self, collection_key, id, text, metadata=None, *, tenant_id):
        """Añade un item. El servidor fija tenant_id/created_at/updated_at."""
        tenant_id = _check_tenant(tenant_id)
        collection = self.get_collection(collection_key)
        cid = _cid(tenant_id, id)

        if collection.get(ids=[cid], include=[])["ids"]:
            raise ItemExistsError(f"Item con ID '{id}' ya existe")

        now = _now()
        final_metadata = _sanitize_metadata(metadata or {})
        final_metadata.update({"tenant_id": tenant_id, "created_at": now, "updated_at": now})

        collection.add(ids=[cid], documents=[text], metadatas=[final_metadata])
        return {"id": id, "text": text, "metadata": final_metadata}

    def query_items(self, collection_key, query_text, n_results=5, filter=None, *, tenant_id):
        """Consulta por similitud semántica dentro del tenant.

        Devuelve la estructura de ChromaDB (``ids``, ``documents``, ``metadatas``,
        ``distances``, listas anidadas) con los ids ya sin prefijo de tenant.
        """
        tenant_id = _check_tenant(tenant_id)
        collection = self.get_collection(collection_key)

        results = collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where=_build_where(tenant_id, filter),
        )
        results["ids"] = [[_public_id(tenant_id, i) for i in ids] for ids in results["ids"]]
        return results

    def get_item(self, collection_key, id, *, tenant_id):
        """Obtiene un item por su ID; ``None`` si no existe en este tenant."""
        tenant_id = _check_tenant(tenant_id)
        collection = self.get_collection(collection_key)

        results = collection.get(ids=[_cid(tenant_id, id)], where={"tenant_id": tenant_id})
        if not results["ids"]:
            return None
        return {
            "id": id,
            "text": results["documents"][0],
            "metadata": results["metadatas"][0] if results["metadatas"] else {},
        }

    def update_item(self, collection_key, id, text=None, metadata=None, *, tenant_id):
        """Actualiza un item del tenant. Conserva ``created_at``; renueva ``updated_at``."""
        tenant_id = _check_tenant(tenant_id)
        collection = self.get_collection(collection_key)

        current = self.get_item(collection_key, id, tenant_id=tenant_id)
        if not current:
            raise ValueError(f"Item con ID '{id}' no encontrado")

        update_text = text if text is not None else current["text"]
        update_metadata = _sanitize_metadata(metadata) if metadata is not None else dict(current["metadata"])
        update_metadata.update({
            "tenant_id": tenant_id,
            "created_at": current["metadata"].get("created_at", _now()),
            "updated_at": _now(),
        })

        collection.update(
            ids=[_cid(tenant_id, id)],
            documents=[update_text],
            metadatas=[update_metadata],
        )
        return {"id": id, "text": update_text, "metadata": update_metadata}

    def delete_item(self, collection_key, id, *, tenant_id):
        """Elimina un item del tenant."""
        tenant_id = _check_tenant(tenant_id)
        collection = self.get_collection(collection_key)

        if not self.get_item(collection_key, id, tenant_id=tenant_id):
            raise ValueError(f"Item con ID '{id}' no encontrado")

        collection.delete(ids=[_cid(tenant_id, id)], where={"tenant_id": tenant_id})
        return {"message": f"Item con ID '{id}' eliminado correctamente"}

    def list_items(self, collection_key, limit: Optional[int] = 100, offset=0, *, tenant_id) -> List[Dict[str, Any]]:
        """Lista los items del tenant (``limit=None`` devuelve todos)."""
        tenant_id = _check_tenant(tenant_id)
        collection = self.get_collection(collection_key)

        kwargs: Dict[str, Any] = {"where": {"tenant_id": tenant_id}, "offset": offset}
        if limit is not None:
            kwargs["limit"] = limit
        results = collection.get(**kwargs)

        return [
            {
                "id": _public_id(tenant_id, results["ids"][i]),
                "text": results["documents"][i],
                "metadata": results["metadatas"][i] if results["metadatas"] else {},
            }
            for i in range(len(results["ids"]))
        ]

    def count_items(self, collection_key, *, tenant_id) -> int:
        """Número de items del tenant en la colección."""
        tenant_id = _check_tenant(tenant_id)
        collection = self.get_collection(collection_key)
        return len(collection.get(where={"tenant_id": tenant_id}, include=[])["ids"])


# Instancia global del gestor de ChromaDB
db_manager = ChromaDBManager()
