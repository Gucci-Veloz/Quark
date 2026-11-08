from fastapi import APIRouter, HTTPException, Body, Depends, Query, Path
from typing import Dict, List, Optional, Any
import uuid

from app.database import db_manager, ItemExistsError
from app.utils.auth import Principal, require_scope
from app.utils.logger import logger
from app.models.schemas import (
    Item, QueryResult, ExternalStoreRequest, ExternalQueryRequest,
    validate_connection_metadata,
)

# La autenticación y el scope se declaran por endpoint (require_scope): lectura
# para consultas, escritura para store/update/delete/batch. El tenant sale del
# Principal, nunca del cuerpo de la petición.
router = APIRouter(
    prefix="/external",
    tags=["external"],
    responses={404: {"description": "No encontrado"}},
)


def _check_connection_metadata(collection_key: str, metadata: Dict[str, Any]) -> None:
    """En `connections` exige los campos de specs.md §3.3 (422 si faltan)."""
    if collection_key == "connections":
        try:
            validate_connection_metadata(metadata)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))


def _format_query_results(results: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {
            "id": results["ids"][0][i],
            "text": results["documents"][0][i],
            "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
        }
        for i in range(len(results["ids"][0]))
    ]


@router.post("/query", response_model=QueryResult)
async def query_data(
    query: ExternalQueryRequest,
    principal: Principal = Depends(require_scope("read")),
):
    """
    Consulta semántica sobre una colección del tenant autenticado.
    """
    try:
        try:
            db_manager.get_collection(query.collection)
        except ValueError:
            raise HTTPException(status_code=404, detail=f"Colección '{query.collection}' no encontrada")

        results = db_manager.query_items(
            collection_key=query.collection,
            query_text=query.text,
            n_results=query.n_results,
            filter=query.filter,
            tenant_id=principal.tenant_id,
        )
        items = _format_query_results(results)

        logger.info("Consulta externa procesada", {
            "collection": query.collection,
            "tenant_id": principal.tenant_id,
            "results_count": len(items),
        })

        return {"items": items, "distances": results["distances"][0]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en consulta externa: {str(e)}", {"collection": query.collection})
        raise HTTPException(status_code=500, detail=f"Error al procesar consulta: {str(e)}")

@router.post("/store", response_model=Item, status_code=201)
async def store_data(
    data: ExternalStoreRequest,
    principal: Principal = Depends(require_scope("write")),
):
    """
    Almacena un documento en una colección del tenant autenticado.

    El servidor fija `tenant_id`, `created_at` y `updated_at` en la metadata.
    En la colección `connections` la metadata debe incluir `source_id`,
    `target_id`, `relation_type`, `collection_ref` y `timestamp`.
    """
    try:
        try:
            db_manager.get_collection(data.collection)
        except ValueError:
            raise HTTPException(status_code=404, detail=f"Colección '{data.collection}' no encontrada")

        metadata = dict(data.metadata)
        _check_connection_metadata(data.collection, metadata)
        metadata["external_source"] = "quark_api"
        item_id = data.id or str(uuid.uuid4())

        try:
            result = db_manager.add_item(
                collection_key=data.collection,
                id=item_id,
                text=data.text,
                metadata=metadata,
                tenant_id=principal.tenant_id,
            )
        except ItemExistsError as e:
            raise HTTPException(status_code=409, detail=str(e))

        logger.info("Datos externos almacenados", {
            "collection": data.collection,
            "item_id": item_id,
            "tenant_id": principal.tenant_id,
        })
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al almacenar datos externos: {str(e)}", {"collection": data.collection})
        raise HTTPException(status_code=500, detail=f"Error al almacenar datos: {str(e)}")

@router.put("/update/{collection_key}/{item_id}", response_model=Item)
async def update_data(
    collection_key: str = Path(..., description="Clave de la colección"),
    item_id: str = Path(..., description="ID del item a actualizar"),
    data: Dict[str, Any] = Body(..., description="Datos actualizados (`text` y/o `metadata`)"),
    principal: Principal = Depends(require_scope("write")),
):
    """
    Actualiza un documento del tenant autenticado (otro tenant => 404).
    """
    try:
        try:
            db_manager.get_collection(collection_key)
        except ValueError:
            raise HTTPException(status_code=404, detail=f"Colección '{collection_key}' no encontrada")

        existing_item = db_manager.get_item(
            collection_key=collection_key,
            id=item_id,
            tenant_id=principal.tenant_id,
        )
        if not existing_item:
            raise HTTPException(status_code=404, detail=f"Item con ID '{item_id}' no encontrado")

        text = data.get("text", existing_item["text"])

        metadata = None
        if "metadata" in data:
            metadata = existing_item["metadata"].copy()
            metadata.update(data["metadata"])
            metadata["last_update_source"] = "quark_api"
            _check_connection_metadata(collection_key, metadata)

        result = db_manager.update_item(
            collection_key=collection_key,
            id=item_id,
            text=text,
            metadata=metadata,
            tenant_id=principal.tenant_id,
        )

        logger.info("Datos externos actualizados", {
            "collection": collection_key,
            "item_id": item_id,
            "tenant_id": principal.tenant_id,
        })
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error al actualizar datos externos: {str(e)}", {
            "collection_key": collection_key,
            "item_id": item_id,
        })
        raise HTTPException(status_code=500, detail=f"Error al actualizar datos: {str(e)}")

@router.delete("/delete/{collection_key}/{item_id}")
async def delete_data(
    collection_key: str = Path(..., description="Clave de la colección"),
    item_id: str = Path(..., description="ID del item a eliminar"),
    principal: Principal = Depends(require_scope("write")),
):
    """
    Elimina un documento del tenant autenticado (otro tenant => 404).
    """
    try:
        try:
            db_manager.get_collection(collection_key)
        except ValueError:
            raise HTTPException(status_code=404, detail=f"Colección '{collection_key}' no encontrada")

        result = db_manager.delete_item(
            collection_key=collection_key,
            id=item_id,
            tenant_id=principal.tenant_id,
        )

        logger.info("Datos externos eliminados", {
            "collection": collection_key,
            "item_id": item_id,
            "tenant_id": principal.tenant_id,
        })
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error al eliminar datos externos: {str(e)}", {
            "collection_key": collection_key,
            "item_id": item_id,
        })
        raise HTTPException(status_code=500, detail=f"Error al eliminar datos: {str(e)}")

@router.get("/collections", response_model=Dict[str, str])
async def list_collections(
    principal: Principal = Depends(require_scope("read")),
):
    """
    Lista las 7 colecciones disponibles (clave -> nombre de colección ChromaDB).
    """
    try:
        return {key: collection.name for key, collection in db_manager.collections.items()}
    except Exception as e:
        logger.error(f"Error al listar colecciones para el consumidor externo: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al listar colecciones: {str(e)}")

@router.post("/batch", response_model=Dict[str, Any])
async def batch_operation(
    operations: List[Dict[str, Any]] = Body(..., embed=True, description="Lista de operaciones (`type`: query | store | update | delete)"),
    principal: Principal = Depends(require_scope("write")),
):
    """
    Realiza múltiples operaciones en una sola llamada, todas con el tenant del solicitante.
    """
    tenant_id = principal.tenant_id
    try:
        results = []
        errors = []

        for i, op in enumerate(operations):
            try:
                if "type" not in op:
                    raise ValueError("La operación debe incluir el campo 'type'")

                if op["type"] == "query":
                    if "query" not in op:
                        raise ValueError("La operación de consulta debe incluir el campo 'query'")

                    query_results = db_manager.query_items(
                        collection_key=op.get("collection", "identity"),
                        query_text=op["query"],
                        n_results=op.get("n_results", 5),
                        filter=op.get("filter", None),
                        tenant_id=tenant_id,
                    )
                    results.append({
                        "operation_index": i,
                        "success": True,
                        "type": "query",
                        "data": {
                            "items": _format_query_results(query_results),
                            "distances": query_results["distances"][0],
                        },
                    })

                elif op["type"] == "store":
                    if "text" not in op:
                        raise ValueError("La operación de almacenamiento debe incluir el campo 'text'")

                    collection_key = op.get("collection", "identity")
                    metadata = dict(op.get("metadata", {}))
                    if collection_key == "connections":
                        validate_connection_metadata(metadata)
                    metadata["external_source"] = "quark_api_batch"

                    store_result = db_manager.add_item(
                        collection_key=collection_key,
                        id=op.get("id", str(uuid.uuid4())),
                        text=op["text"],
                        metadata=metadata,
                        tenant_id=tenant_id,
                    )
                    results.append({"operation_index": i, "success": True, "type": "store", "data": store_result})

                elif op["type"] == "update":
                    if "collection" not in op or "id" not in op:
                        raise ValueError("La operación de actualización debe incluir los campos 'collection' e 'id'")

                    collection_key = op["collection"]
                    item_id = op["id"]
                    existing_item = db_manager.get_item(
                        collection_key=collection_key,
                        id=item_id,
                        tenant_id=tenant_id,
                    )
                    if not existing_item:
                        raise ValueError(f"Item con ID '{item_id}' no encontrado")

                    metadata = None
                    if "metadata" in op:
                        metadata = existing_item["metadata"].copy()
                        metadata.update(op["metadata"])
                        metadata["last_update_source"] = "quark_api_batch"
                        if collection_key == "connections":
                            validate_connection_metadata(metadata)

                    update_result = db_manager.update_item(
                        collection_key=collection_key,
                        id=item_id,
                        text=op.get("text", existing_item["text"]),
                        metadata=metadata,
                        tenant_id=tenant_id,
                    )
                    results.append({"operation_index": i, "success": True, "type": "update", "data": update_result})

                elif op["type"] == "delete":
                    if "collection" not in op or "id" not in op:
                        raise ValueError("La operación de eliminación debe incluir los campos 'collection' e 'id'")

                    delete_result = db_manager.delete_item(
                        collection_key=op["collection"],
                        id=op["id"],
                        tenant_id=tenant_id,
                    )
                    results.append({"operation_index": i, "success": True, "type": "delete", "data": delete_result})

                else:
                    raise ValueError(f"Tipo de operación desconocido: {op['type']}")

            except Exception as e:
                # Registrar error pero continuar con las demás operaciones
                errors.append({
                    "operation_index": i,
                    "type": op.get("type", "unknown"),
                    "error": str(e),
                })

        logger.info("Operación por lotes externa completada", {
            "total_operations": len(operations),
            "successful": len(results),
            "failed": len(errors),
            "tenant_id": tenant_id,
        })

        return {
            "total_operations": len(operations),
            "successful_operations": len(results),
            "failed_operations": len(errors),
            "results": results,
            "errors": errors,
        }

    except Exception as e:
        logger.error(f"Error en operación por lotes externa: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error en operación por lotes: {str(e)}")

@router.post("/consolidate", response_model=Dict[str, Any])
async def consolidate_data(
    request: Dict[str, Any] = Body(..., description="Solicitud de consolidación: `query` (obligatorio), `collections`, `limit`"),
    principal: Principal = Depends(require_scope("read")),
):
    """
    Consolida resultados de varias colecciones del tenant según la consulta.
    """
    try:
        collections = request.get("collections", ["identity", "business", "reminders"])
        query = request.get("query", "")
        limit = request.get("limit", 10)

        if not query:
            raise HTTPException(status_code=400, detail="Se requiere un texto de consulta para consolidar datos")

        consolidated_results = []

        for collection in collections:
            try:
                results = db_manager.query_items(
                    collection_key=collection,
                    query_text=query,
                    n_results=limit,
                    tenant_id=principal.tenant_id,
                )
                for i in range(len(results["ids"][0])):
                    consolidated_results.append({
                        "collection": collection,
                        "id": results["ids"][0][i],
                        "text": results["documents"][0][i],
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                        "similarity": results["distances"][0][i],
                    })
            except Exception as e:
                logger.warning(f"Error al consultar colección {collection}: {str(e)}")

        # Menor distancia = más similar
        consolidated_results.sort(key=lambda x: x["similarity"])
        consolidated_results = consolidated_results[:limit]

        logger.info("Consolidación de datos para el consumidor externo completada", {
            "collections": collections,
            "results_count": len(consolidated_results),
            "tenant_id": principal.tenant_id,
        })

        return {
            "query": query,
            "collections": collections,
            "total_results": len(consolidated_results),
            "results": consolidated_results,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en consolidación de datos para el consumidor externo: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al consolidar datos: {str(e)}")
