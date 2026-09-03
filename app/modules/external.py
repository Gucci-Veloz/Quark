from fastapi import APIRouter, HTTPException, Body, Depends, Query, Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid
import json

from app.database import db_manager
from app.utils.auth import validate_access
from app.utils.logger import logger
from app.models.schemas import Item, ItemList, QueryResult

router = APIRouter(
    prefix="/external",
    tags=["external"],
    responses={404: {"description": "No encontrado"}},
    dependencies=[Depends(validate_access)]  # Proteger todas las rutas con autenticación
)

@router.post("/query", response_model=QueryResult)
async def query_data(
    query: Dict[str, Any] = Body(..., description="Consulta del cliente externo"),
):
    """
    Endpoint para consultas semánticas desde aplicaciones externas.
    """
    try:
        # Validar la consulta
        if "text" not in query:
            raise HTTPException(status_code=400, detail="La consulta debe incluir el campo 'text'")
        
        collection_key = query.get("collection", "identity")
        n_results = query.get("n_results", 5)
        filter_dict = query.get("filter", None)
        
        # Validar que la colección existe
        try:
            db_manager.get_collection(collection_key)
        except ValueError:
            raise HTTPException(status_code=404, detail=f"Colección '{collection_key}' no encontrada")
        
        # Realizar la consulta
        results = db_manager.query_items(
            collection_key=collection_key,
            query_text=query["text"],
            n_results=n_results,
            filter=filter_dict
        )
        
        # Construir la respuesta
        items = []
        for i in range(len(results["ids"][0])):
            items.append({
                "id": results["ids"][0][i],
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {}
            })
        
        logger.info("Consulta externa procesada", {
            "collection": collection_key,
            "query": query["text"],
            "results_count": len(items)
        })
        
        return {
            "items": items,
            "distances": results["distances"][0]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en consulta externa: {str(e)}", {"query": query})
        raise HTTPException(status_code=500, detail=f"Error al procesar consulta: {str(e)}")

@router.post("/store", response_model=Item, status_code=201)
async def store_data(
    data: Dict[str, Any] = Body(..., description="Datos a almacenar"),
):
    """
    Endpoint para almacenar datos desde aplicaciones externas.
    """
    try:
        # Validar los datos
        if "text" not in data:
            raise HTTPException(status_code=400, detail="Los datos deben incluir el campo 'text'")
        
        collection_key = data.get("collection", "identity")
        text = data["text"]
        metadata = data.get("metadata", {})
        
        # Validar que la colección existe
        try:
            db_manager.get_collection(collection_key)
        except ValueError:
            raise HTTPException(status_code=404, detail=f"Colección '{collection_key}' no encontrada")
        
        # Generar ID único
        item_id = data.get("id", str(uuid.uuid4()))
        
        # Añadir información de creación si no existe
        if "created_at" not in metadata:
            metadata["created_at"] = datetime.now().isoformat()
        metadata["updated_at"] = datetime.now().isoformat()
        metadata["external_source"] = "quark_api"

        # Almacenar los datos
        result = db_manager.add_item(
            collection_key=collection_key,
            id=item_id,
            text=text,
            metadata=metadata
        )
        
        logger.info("Datos externos almacenados", {
            "collection": collection_key,
            "item_id": item_id
        })
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al almacenar datos externos: {str(e)}", {"data": data})
        raise HTTPException(status_code=500, detail=f"Error al almacenar datos: {str(e)}")

@router.put("/update/{collection_key}/{item_id}", response_model=Item)
async def update_data(
    collection_key: str = Path(..., description="Clave de la colección"),
    item_id: str = Path(..., description="ID del item a actualizar"),
    data: Dict[str, Any] = Body(..., description="Datos actualizados"),
):
    """
    Endpoint para actualizar datos desde aplicaciones externas.
    """
    try:
        # Validar que la colección existe
        try:
            db_manager.get_collection(collection_key)
        except ValueError:
            raise HTTPException(status_code=404, detail=f"Colección '{collection_key}' no encontrada")
        
        # Verificar que el item existe
        existing_item = db_manager.get_item(
            collection_key=collection_key,
            id=item_id
        )
        
        if not existing_item:
            raise HTTPException(status_code=404, detail=f"Item con ID '{item_id}' no encontrado")
        
        # Preparar los datos para actualización
        text = data.get("text", existing_item["text"])
        
        # Si hay metadatos para actualizar
        metadata = None
        if "metadata" in data:
            metadata = existing_item["metadata"].copy()
            metadata.update(data["metadata"])
            metadata["updated_at"] = datetime.now().isoformat()
            metadata["last_update_source"] = "quark_api"
        
        # Actualizar el item
        result = db_manager.update_item(
            collection_key=collection_key,
            id=item_id,
            text=text,
            metadata=metadata
        )
        
        logger.info("Datos externos actualizados", {
            "collection": collection_key,
            "item_id": item_id
        })
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al actualizar datos externos: {str(e)}", {
            "collection_key": collection_key,
            "item_id": item_id,
            "data": data
        })
        raise HTTPException(status_code=500, detail=f"Error al actualizar datos: {str(e)}")

@router.delete("/delete/{collection_key}/{item_id}")
async def delete_data(
    collection_key: str = Path(..., description="Clave de la colección"),
    item_id: str = Path(..., description="ID del item a eliminar"),
):
    """
    Endpoint para eliminar datos desde aplicaciones externas.
    """
    try:
        # Validar que la colección existe
        try:
            db_manager.get_collection(collection_key)
        except ValueError:
            raise HTTPException(status_code=404, detail=f"Colección '{collection_key}' no encontrada")
        
        # Eliminar el item
        result = db_manager.delete_item(
            collection_key=collection_key,
            id=item_id
        )
        
        logger.info("Datos externos eliminados", {
            "collection": collection_key,
            "item_id": item_id
        })
        
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error al eliminar datos externos: {str(e)}", {
            "collection_key": collection_key,
            "item_id": item_id
        })
        raise HTTPException(status_code=500, detail=f"Error al eliminar datos: {str(e)}")

@router.get("/collections", response_model=Dict[str, str])
async def list_collections():
    """
    Lista todas las colecciones disponibles para el consumidor externo.
    """
    try:
        return {key: collection.name for key, collection in db_manager.collections.items()}
    except Exception as e:
        logger.error(f"Error al listar colecciones para el consumidor externo: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al listar colecciones: {str(e)}")

@router.post("/batch", response_model=Dict[str, Any])
async def batch_operation(
    operations: List[Dict[str, Any]] = Body(..., embed=True, description="Lista de operaciones a realizar"),
):
    """
    Realiza múltiples operaciones en una sola llamada.
    """
    try:
        results = []
        errors = []
        
        for i, op in enumerate(operations):
            try:
                # Verificar que la operación tiene los campos requeridos
                if "type" not in op:
                    raise ValueError("La operación debe incluir el campo 'type'")
                
                # Procesar según el tipo de operación
                if op["type"] == "query":
                    # Realizar consulta
                    if "query" not in op:
                        raise ValueError("La operación de consulta debe incluir el campo 'query'")
                    
                    collection_key = op.get("collection", "identity")
                    n_results = op.get("n_results", 5)
                    filter_dict = op.get("filter", None)
                    
                    query_results = db_manager.query_items(
                        collection_key=collection_key,
                        query_text=op["query"],
                        n_results=n_results,
                        filter=filter_dict
                    )
                    
                    # Formatear resultados
                    items = []
                    for j in range(len(query_results["ids"][0])):
                        items.append({
                            "id": query_results["ids"][0][j],
                            "text": query_results["documents"][0][j],
                            "metadata": query_results["metadatas"][0][j] if query_results["metadatas"] else {}
                        })
                    
                    results.append({
                        "operation_index": i,
                        "success": True,
                        "type": "query",
                        "data": {
                            "items": items,
                            "distances": query_results["distances"][0]
                        }
                    })
                
                elif op["type"] == "store":
                    # Almacenar datos
                    if "text" not in op:
                        raise ValueError("La operación de almacenamiento debe incluir el campo 'text'")
                    
                    collection_key = op.get("collection", "identity")
                    text = op["text"]
                    metadata = op.get("metadata", {})
                    item_id = op.get("id", str(uuid.uuid4()))
                    
                    # Añadir información de creación
                    if "created_at" not in metadata:
                        metadata["created_at"] = datetime.now().isoformat()
                    metadata["updated_at"] = datetime.now().isoformat()
                    metadata["external_source"] = "quark_api_batch"

                    store_result = db_manager.add_item(
                        collection_key=collection_key,
                        id=item_id,
                        text=text,
                        metadata=metadata
                    )
                    
                    results.append({
                        "operation_index": i,
                        "success": True,
                        "type": "store",
                        "data": store_result
                    })
                
                elif op["type"] == "update":
                    # Actualizar datos
                    if "collection" not in op or "id" not in op:
                        raise ValueError("La operación de actualización debe incluir los campos 'collection' e 'id'")
                    
                    collection_key = op["collection"]
                    item_id = op["id"]
                    
                    # Verificar que el item existe
                    existing_item = db_manager.get_item(
                        collection_key=collection_key,
                        id=item_id
                    )
                    
                    if not existing_item:
                        raise ValueError(f"Item con ID '{item_id}' no encontrado")
                    
                    # Preparar datos para actualización
                    text = op.get("text", existing_item["text"])
                    
                    # Si hay metadatos para actualizar
                    metadata = None
                    if "metadata" in op:
                        metadata = existing_item["metadata"].copy()
                        metadata.update(op["metadata"])
                        metadata["updated_at"] = datetime.now().isoformat()
                        metadata["last_update_source"] = "quark_api_batch"
                    
                    update_result = db_manager.update_item(
                        collection_key=collection_key,
                        id=item_id,
                        text=text,
                        metadata=metadata
                    )
                    
                    results.append({
                        "operation_index": i,
                        "success": True,
                        "type": "update",
                        "data": update_result
                    })
                
                elif op["type"] == "delete":
                    # Eliminar datos
                    if "collection" not in op or "id" not in op:
                        raise ValueError("La operación de eliminación debe incluir los campos 'collection' e 'id'")
                    
                    collection_key = op["collection"]
                    item_id = op["id"]
                    
                    delete_result = db_manager.delete_item(
                        collection_key=collection_key,
                        id=item_id
                    )
                    
                    results.append({
                        "operation_index": i,
                        "success": True,
                        "type": "delete",
                        "data": delete_result
                    })
                
                else:
                    raise ValueError(f"Tipo de operación desconocido: {op['type']}")
            
            except Exception as e:
                # Registrar error pero continuar con las demás operaciones
                errors.append({
                    "operation_index": i,
                    "type": op.get("type", "unknown"),
                    "error": str(e)
                })
        
        logger.info("Operación por lotes externa completada", {
            "total_operations": len(operations),
            "successful": len(results),
            "failed": len(errors)
        })
        
        return {
            "total_operations": len(operations),
            "successful_operations": len(results),
            "failed_operations": len(errors),
            "results": results,
            "errors": errors
        }
    
    except Exception as e:
        logger.error(f"Error en operación por lotes externa: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error en operación por lotes: {str(e)}")

@router.post("/consolidate", response_model=Dict[str, Any])
async def consolidate_data(
    request: Dict[str, Any] = Body(..., description="Solicitud de consolidación de datos"),
):
    """
    Consolida múltiples colecciones de datos según los criterios proporcionados.
    """
    try:
        collections = request.get("collections", ["identity", "business", "reminders"])
        query = request.get("query", "")
        limit = request.get("limit", 10)
        
        if not query:
            raise HTTPException(status_code=400, detail="Se requiere un texto de consulta para consolidar datos")
        
        consolidated_results = []
        
        # Consultar cada colección
        for collection in collections:
            try:
                results = db_manager.query_items(
                    collection_key=collection,
                    query_text=query,
                    n_results=limit
                )
                
                # Añadir los resultados al consolidado
                for i in range(len(results["ids"][0])):
                    consolidated_results.append({
                        "collection": collection,
                        "id": results["ids"][0][i],
                        "text": results["documents"][0][i],
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                        "similarity": results["distances"][0][i]
                    })
            except Exception as e:
                logger.warning(f"Error al consultar colección {collection}: {str(e)}")
                # Continuar con las demás colecciones a pesar del error
        
        # Ordenar por similitud (menor distancia es más similar)
        consolidated_results.sort(key=lambda x: x["similarity"])
        
        # Limitar al número solicitado
        consolidated_results = consolidated_results[:limit]
        
        logger.info("Consolidación de datos para el consumidor externo completada", {
            "query": query,
            "collections": collections,
            "results_count": len(consolidated_results)
        })
        
        return {
            "query": query,
            "collections": collections,
            "total_results": len(consolidated_results),
            "results": consolidated_results
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en consolidación de datos para el consumidor externo: {str(e)}", {"request": request})
        raise HTTPException(status_code=500, detail=f"Error al consolidar datos: {str(e)}") 