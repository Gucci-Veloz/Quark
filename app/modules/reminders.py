from fastapi import APIRouter, HTTPException, Query, Path, Depends
from typing import List, Dict, Optional, Any
from datetime import datetime

from app.database import db_manager
from app.utils.auth import Principal, require_scope
from app.models.schemas import (
    Item, ReminderItemCreate, ReminderItemUpdate, 
    ItemList, QueryResult, generate_id
)

router = APIRouter(
    prefix="/reminders",
    tags=["reminders"],
    responses={404: {"description": "No encontrado"}},
)

COLLECTION_KEY = "reminders"

@router.post("/", response_model=Item, status_code=201)
async def create_reminder_item(item: ReminderItemCreate, principal: Principal = Depends(require_scope("write"))):
    """
    Crea un nuevo recordatorio o URL en el módulo de Recordatorios y URLs.
    """
    item_id = generate_id()
    
    try:
        result = db_manager.add_item(
            collection_key=COLLECTION_KEY,
            id=item_id,
            text=item.text,
            metadata=item.metadata,
            tenant_id=principal.tenant_id
        )
        
        return {
            "id": result["id"],
            "text": result["text"],
            "metadata": result["metadata"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al crear el recordatorio: {str(e)}")

@router.get("/", response_model=ItemList)
async def list_reminder_items(
    limit: int = Query(100, ge=1, le=1000, description="Número máximo de items a retornar"),
    offset: int = Query(0, ge=0, description="Número de items a saltar"),
    type: Optional[str] = Query(None, description="Filtrar por tipo (reminder, url)"),
    priority: Optional[str] = Query(None, description="Filtrar por prioridad"),
    status: Optional[str] = Query(None, description="Filtrar por estado"),
    principal: Principal = Depends(require_scope("read"))
):
    """
    Lista todos los recordatorios y URLs.
    """
    try:
        # Obtener todos los items
        all_items = db_manager.list_items(collection_key=COLLECTION_KEY, limit=None, tenant_id=principal.tenant_id)
        
        # Aplicar filtros si se proporcionan
        filtered_items = all_items
        
        if type:
            filtered_items = [item for item in filtered_items if item["metadata"].get("type") == type]
        
        if priority:
            filtered_items = [item for item in filtered_items if item["metadata"].get("priority") == priority]
        
        if status:
            filtered_items = [item for item in filtered_items if item["metadata"].get("status") == status]
        
        # Aplicar paginación
        start_idx = min(offset, len(filtered_items))
        end_idx = min(start_idx + limit, len(filtered_items))
        
        paginated_items = filtered_items[start_idx:end_idx]
        
        return {
            "items": paginated_items,
            "total": len(filtered_items)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al listar los recordatorios: {str(e)}")

@router.get("/search", response_model=QueryResult)
async def search_reminder_items(
    query: str = Query(..., min_length=1, description="Texto a buscar"),
    n_results: int = Query(5, ge=1, le=100, description="Número de resultados a retornar"),
    type: Optional[str] = Query(None, description="Filtrar por tipo (reminder, url)"),
    priority: Optional[str] = Query(None, description="Filtrar por prioridad"),
    status: Optional[str] = Query(None, description="Filtrar por estado"),
    principal: Principal = Depends(require_scope("read"))
):
    """
    Busca recordatorios y URLs por similitud semántica.
    """
    try:
        # Construir el filtro si se proporcionan parámetros
        filter_dict = {}
        
        if type:
            filter_dict["type"] = type
        
        if priority:
            filter_dict["priority"] = priority
        
        if status:
            filter_dict["status"] = status
        
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
        raise HTTPException(status_code=500, detail=f"Error al buscar recordatorios: {str(e)}")

@router.get("/{item_id}", response_model=Item)
async def get_reminder_item(
    item_id: str = Path(..., description="ID del recordatorio a obtener"),
    principal: Principal = Depends(require_scope("read"))
):
    """
    Obtiene un recordatorio o URL específico.
    """
    try:
        item = db_manager.get_item(
            collection_key=COLLECTION_KEY,
            id=item_id,
            tenant_id=principal.tenant_id
        )
        
        if not item:
            raise HTTPException(status_code=404, detail=f"Recordatorio con ID '{item_id}' no encontrado")
        
        return item
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener el recordatorio: {str(e)}")

@router.put("/{item_id}", response_model=Item)
async def update_reminder_item(
    item_id: str = Path(..., description="ID del recordatorio a actualizar"),
    item_update: ReminderItemUpdate = Depends(),
    principal: Principal = Depends(require_scope("write"))
):
    """
    Actualiza un recordatorio o URL existente.
    """
    try:
        # Verificar que el item existe
        existing_item = db_manager.get_item(
            collection_key=COLLECTION_KEY,
            id=item_id,
            tenant_id=principal.tenant_id
        )
        
        if not existing_item:
            raise HTTPException(status_code=404, detail=f"Recordatorio con ID '{item_id}' no encontrado")
        
        # Actualizar los metadatos si se proporcionan
        metadata = None
        if item_update.metadata is not None:
            metadata = existing_item["metadata"].copy()
            metadata.update(item_update.metadata)
            metadata["updated_at"] = datetime.now().isoformat()
        
        # Actualizar el item
        updated_item = db_manager.update_item(
            collection_key=COLLECTION_KEY,
            id=item_id,
            text=item_update.text,
            metadata=metadata,
            tenant_id=principal.tenant_id
        )
        
        return updated_item
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al actualizar el recordatorio: {str(e)}")

@router.delete("/{item_id}")
async def delete_reminder_item(
    item_id: str = Path(..., description="ID del recordatorio a eliminar"),
    principal: Principal = Depends(require_scope("write"))
):
    """
    Elimina un recordatorio o URL.
    """
    try:
        result = db_manager.delete_item(
            collection_key=COLLECTION_KEY,
            id=item_id,
            tenant_id=principal.tenant_id
        )
        
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al eliminar el recordatorio: {str(e)}") 