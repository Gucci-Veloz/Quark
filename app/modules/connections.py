from fastapi import APIRouter, HTTPException, Query, Path, Depends, Body
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone

from app.database import db_manager
from app.utils.auth import Principal, require_scope
from app.models.schemas import (
    Item, ConnectionItemCreate, ConnectionItemUpdate, 
    ConnectionAnalysisRequest, ConnectionAnalysisResult,
    ItemList, QueryResult, generate_id, validate_connection_metadata
)

router = APIRouter(
    prefix="/conexiones",
    tags=["conexiones"],
    responses={404: {"description": "No encontrado"}},
)

COLLECTION_KEY = "connections"

@router.post("/analizar", response_model=ConnectionAnalysisResult)
async def analyze_connections(request: ConnectionAnalysisRequest, principal: Principal = Depends(require_scope("write"))):
    """
    Analiza y detecta relaciones entre un item específico y otros datos almacenados.
    
    Este endpoint:
    1. Obtiene el item especificado
    2. Busca items similares en todos los módulos
    3. Crea conexiones para los items con similitud superior al umbral
    4. Retorna las conexiones encontradas
    """
    try:
        # Verificar que el módulo es válido
        valid_modules = ["identity", "business", "reminders", "learnings"]
        if request.module not in valid_modules:
            raise HTTPException(status_code=400, detail=f"Módulo '{request.module}' no válido")
        
        # Obtener el item de origen
        source_item = db_manager.get_item(
            collection_key=request.module,
            id=request.item_id,
            tenant_id=principal.tenant_id
        )
        
        if not source_item:
            raise HTTPException(status_code=404, detail=f"Item con ID '{request.item_id}' no encontrado en el módulo '{request.module}'")
        
        # Buscar items similares en todos los módulos
        connections = []
        
        for module in valid_modules:
            # Evitar buscar en el módulo de conexiones
            if module == "connections":
                continue
                
            # Buscar items similares
            results = db_manager.query_items(
                collection_key=module,
                query_text=source_item["text"],
                n_results=request.max_connections,
                tenant_id=principal.tenant_id
            )
            
            # Procesar los resultados
            if results["ids"] and results["ids"][0]:
                for i in range(len(results["ids"][0])):
                    # Evitar conectar el item consigo mismo
                    if module == request.module and results["ids"][0][i] == request.item_id:
                        continue
                    
                    # Verificar si la similitud supera el umbral
                    similarity = 1.0 - results["distances"][0][i]  # Convertir distancia a similitud
                    if similarity >= request.min_similarity:
                        # Crear una conexión
                        connection_id = generate_id()
                        connection_text = f"Conexión entre '{source_item['text'][:50]}...' y '{results['documents'][0][i][:50]}...'"
                        
                        now = datetime.now(timezone.utc).isoformat()
                        # Campos de specs.md §3.3; tenant_id/created_at/updated_at los fija db_manager
                        connection_metadata = {
                            "source_id": request.item_id,
                            "target_id": results["ids"][0][i],
                            "relation_type": "semantic",
                            "collection_ref": module,
                            "timestamp": now,
                            "source_module": request.module,
                            "target_module": module,
                            "strength": similarity,
                        }
                        validate_connection_metadata(connection_metadata)
                        
                        # Guardar la conexión en la base de datos
                        saved = db_manager.add_item(
                            collection_key=COLLECTION_KEY,
                            id=connection_id,
                            text=connection_text,
                            metadata=connection_metadata,
                            tenant_id=principal.tenant_id
                        )
                        
                        # Añadir a la lista de conexiones
                        connections.append({
                            "id": connection_id,
                            "text": connection_text,
                            "metadata": saved["metadata"]
                        })
        
        # Retornar el resultado
        return {
            "source_id": request.item_id,
            "source_module": request.module,
            "connections": connections,
            "total": len(connections)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al analizar conexiones: {str(e)}")

@router.get("/", response_model=ItemList)
async def list_connections(
    limit: int = Query(100, ge=1, le=1000, description="Número máximo de conexiones a retornar"),
    offset: int = Query(0, ge=0, description="Número de conexiones a saltar"),
    source_module: Optional[str] = Query(None, description="Filtrar por módulo de origen"),
    target_module: Optional[str] = Query(None, description="Filtrar por módulo de destino"),
    min_strength: float = Query(0.0, ge=0.0, le=1.0, description="Fuerza mínima de la conexión"),
    principal: Principal = Depends(require_scope("read"))
):
    """
    Lista todas las conexiones detectadas.
    """
    try:
        # Obtener todas las conexiones
        all_items = db_manager.list_items(collection_key=COLLECTION_KEY, limit=None, tenant_id=principal.tenant_id)
        
        # Aplicar filtros si se proporcionan
        filtered_items = all_items
        
        if source_module:
            filtered_items = [item for item in filtered_items if item["metadata"].get("source_module") == source_module]
        
        if target_module:
            filtered_items = [item for item in filtered_items if item["metadata"].get("target_module") == target_module]
        
        if min_strength > 0.0:
            filtered_items = [item for item in filtered_items if item["metadata"].get("strength", 0.0) >= min_strength]
        
        # Aplicar paginación
        start_idx = min(offset, len(filtered_items))
        end_idx = min(start_idx + limit, len(filtered_items))
        
        paginated_items = filtered_items[start_idx:end_idx]
        
        return {
            "items": paginated_items,
            "total": len(filtered_items)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al listar las conexiones: {str(e)}")

@router.get("/buscar", response_model=QueryResult)
async def search_connections(
    query: str = Query(..., min_length=1, description="Texto a buscar"),
    n_results: int = Query(5, ge=1, le=100, description="Número de resultados a retornar"),
    source_module: Optional[str] = Query(None, description="Filtrar por módulo de origen"),
    target_module: Optional[str] = Query(None, description="Filtrar por módulo de destino"),
    min_strength: float = Query(0.0, ge=0.0, le=1.0, description="Fuerza mínima de la conexión"),
    principal: Principal = Depends(require_scope("read"))
):
    """
    Busca conexiones por similitud semántica.
    """
    try:
        # Construir el filtro si se proporcionan parámetros
        filter_dict = {}
        
        if source_module:
            filter_dict["source_module"] = source_module
        
        if target_module:
            filter_dict["target_module"] = target_module
        
        if min_strength > 0.0:
            filter_dict["strength"] = {"$gte": min_strength}
        
        # Si no hay filtros, establecer a None
        if not filter_dict:
            filter_dict = None
        
        results = db_manager.query_items(
            collection_key=COLLECTION_KEY,
            query_text=query,
            n_results=n_results,
            filter=filter_dict,
            tenant_id=principal.tenant_id
        )
        
        # Construir la respuesta
        items = []
        for i in range(len(results["ids"][0])):
            items.append({
                "id": results["ids"][0][i],
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {}
            })
        
        return {
            "items": items,
            "distances": results["distances"][0]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al buscar conexiones: {str(e)}")

@router.get("/{connection_id}", response_model=Item)
async def get_connection(
    connection_id: str = Path(..., description="ID de la conexión a obtener"),
    principal: Principal = Depends(require_scope("read"))
):
    """
    Obtiene una conexión específica.
    """
    try:
        item = db_manager.get_item(
            collection_key=COLLECTION_KEY,
            id=connection_id,
            tenant_id=principal.tenant_id
        )
        
        if not item:
            raise HTTPException(status_code=404, detail=f"Conexión con ID '{connection_id}' no encontrada")
        
        return item
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener la conexión: {str(e)}")

@router.delete("/{connection_id}")
async def delete_connection(
    connection_id: str = Path(..., description="ID de la conexión a eliminar"),
    principal: Principal = Depends(require_scope("write"))
):
    """
    Elimina una conexión.
    """
    try:
        result = db_manager.delete_item(
            collection_key=COLLECTION_KEY,
            id=connection_id,
            tenant_id=principal.tenant_id
        )
        
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al eliminar la conexión: {str(e)}") 